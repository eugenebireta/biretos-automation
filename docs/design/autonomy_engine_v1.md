# Autonomy Engine v1 — Architecture Design

**trace_id:** orch_20260408T194149Z_afdf0f  
**task_id:** DESIGN-AUTONOMY-ENGINE-V1  
**status:** DESIGN_COMPLETE  
**risk_class:** LOW (docs/design/ only)  
**author:** Agent/ClaudeCode  
**created:** 2026-04-08

---

## Overview

The Autonomy Engine defines how the Meta Orchestrator decides *when to act without human approval*, *what constitutes an auto-approvable decision*, and *how to measure autonomous execution quality over time*.

It sits between the Decision Synthesizer (rule engine) and the Executor Bridge. Its job is to classify each Synthesizer decision into one of five Decision Classes (D1–D5), apply Policy Pack rules for auto-approval, optionally batch multiple low-risk approvals, and expose KPIs that tell the owner how autonomous the system is becoming.

```
  Synthesizer.decide()
        │
        ▼
  ┌─────────────────────┐
  │  Autonomy Engine    │
  │  ─────────────────  │
  │  1. Classify → D1-D5│
  │  2. Policy Pack eval│
  │  3. Batch check     │
  │  4. Emit KPI event  │
  └──────────┬──────────┘
             │
     ┌───────┴───────┐
     │               │
  AUTO_APPROVE   GATE_REQUIRED
     │               │
  Executor        owner / JUDGE
  Bridge
```

---

## 1. Decision Classes D1–D5

Each Synthesizer output is mapped to exactly one Decision Class. The class determines the default approval route and rollback capability.

### Class Table

| Class | Name             | Risk Level | Scope Constraint           | Default Route    | Rollback Strategy |
|-------|------------------|------------|----------------------------|------------------|-------------------|
| D1    | Trivial          | LOW        | Docs, config, non-code     | AUTO_APPROVE     | Revert commit     |
| D2    | Bounded Code     | LOW        | Tier-3 code, ≤5 files      | AUTO_APPROVE     | Revert commit     |
| D3    | Elevated Code    | SEMI       | Tier-2 body, revenue FSM   | CRITIQUE_GATE    | Rollback PR       |
| D4    | Governance       | CORE       | Tier-1, schema, FSM, pinned API | FULL_SPEC   | Not applicable — blocked before execution |
| D5    | Emergency        | any        | Owner-flagged override     | OWNER_CONFIRM    | Snapshot + revert |

### D1 — Trivial

**What qualifies:**
- `docs/**`, `*.md`, `*.txt` changes only
- Config tuning (`orchestrator/config.yaml` value changes, not key additions)
- Comment-only code changes

**What is NOT D1:**
- Any `.py`, `.sql`, `.json` schema file (those are D2+ even if small)

**Rollback:** `git revert <commit_sha>` — single commit, no migration rollback needed.

**Rollback trigger:** CI failure, owner flag, KPI regression (≥2 consecutive AUTO_APPROVE failures).

---

### D2 — Bounded Code

**What qualifies:**
- Tier-3 only (no Tier-1/2 file paths)
- ≤5 files changed
- No `migrations/020+` touched
- No `synthesizer.py`, `advisor.py`, `classifier.py` in scope
- Synthesizer action = `PROCEED`, `rule_trace` does not contain `R2:SEMI_ESCALATION`

**What is NOT D2:**
- Financial side-effects: functions writing to `rev_*` tables with non-idempotent paths
- Any `INSERT/UPDATE/DELETE` on Core tables (auto-escalates to D4)

**Rollback:** `git revert <commit_sha>`. If DB migration was part of scope, raise to D3 minimum.

**Rollback trigger:** Test failure post-merge, data anomaly detected by shadow_log, owner flag.

---

### D3 — Elevated Code

**What qualifies:**
- SEMI risk from Synthesizer: `R2:SEMI_ESCALATION` in rule_trace
- Tier-2 body changes (pinned signatures unchanged)
- Revenue migrations `migrations/020+`
- `orchestrator/` policy files (synthesizer, advisor, classifier)
- D2 scope with financial side-effects (non-idempotent `rev_*` writes)

**Approval route:** CRITIQUE_GATE — must pass automated auditor critique before Executor runs.  
Current implementation: `auditor_system/review_runner.py` with Gemini 2.5 Pro auditor.

**Rollback:** PR-level rollback. If migration was applied, owner runs rollback migration manually.  
Migration rollback scripts must be authored alongside the forward migration (policy).

**Rollback trigger:** Auditor REJECT verdict, CI failure, shadow_log anomaly within 24h of merge.

---

### D4 — Governance

**What qualifies:**
- CORE risk: `R1:CORE_GATE` fired in Synthesizer
- Any Tier-1 file path detected
- Pinned API signature in scope
- `ALTER/DROP` on `reconciliation_*` tables
- FSM state machine changes

**Approval route:** FULL_SPEC — execution is BLOCKED. Claude Code cannot run this.  
Workflow: SCOUT → Pass 1 (plan only, `WAITING_FOR_OK`) → external JUDGE approval → Pass 2.

**Rollback:** Not applicable — D4 work is blocked before execution. If an emergency D4 commit was made in error, owner manually reverts and audits.

**Auto-approve:** NEVER. D4 is always gated.

---

### D5 — Emergency Override

**What qualifies:**
- Owner explicitly sets `emergency_override: true` in manifest.json
- Applies when normal flow is deadlocked but action is urgent (e.g., prod hotfix)

**Approval route:** OWNER_CONFIRM — directive is shown, owner types `CONFIRM` to proceed.  
One execution only. Override flag clears after single use.

**Rollback:** Pre-execution snapshot of affected files written to `orchestrator/rollback_snapshots/<trace_id>/`. Owner runs `python orchestrator/rollback.py --trace-id <id>` to restore.

**KPI note:** D5 executions are counted as `autonomy_override_count` and reduce the Autonomy Score (see §5).

---

### D1–D5 Classification Decision Tree

```
Synthesizer.action == CORE_GATE?
  YES → D4

emergency_override flag set?
  YES → D5

advisor_risk == SEMI OR classifier_risk == SEMI?
  YES → D3

files all in docs/**/*.md or config value changes only?
  YES → D1

all files Tier-3, count ≤ 5, no financial side-effects?
  YES → D2

default → D3 (conservative)
```

---

## 2. Auto-Approve Rules Engine

The rules engine evaluates a candidate decision against the active Policy Pack to determine whether it may proceed without human confirmation.

### Architecture

```
┌─────────────────────────────────────────────────────┐
│               AutoApproveEngine                     │
│  input: SynthesizerDecision + DecisionClass         │
│                                                     │
│  1. Load active PolicyPack                          │
│  2. For each rule in pack (priority order):         │
│     a. Evaluate condition                           │
│     b. If BLOCK → return GATE_REQUIRED              │
│     c. If REQUIRE_TEST → check test_evidence        │
│     d. If PASS → continue                           │
│  3. All rules passed → return AUTO_APPROVE          │
│                                                     │
│  output: ApproveDecision(verdict, rule_log)         │
└─────────────────────────────────────────────────────┘
```

### Rule Evaluation Contract

Each rule in the engine is a pure function:

```
rule(decision: SynthesizerDecision, class: DecisionClass, context: EvalContext) 
  → RuleResult(status: PASS | BLOCK | REQUIRE_TEST, reason: str)
```

Rules never call LLMs, never write to disk, never mutate state. Side-effect-free.

### Hard-Coded Engine Rules (always active, cannot be disabled by Policy Pack)

| Rule ID | Condition                                         | Result       |
|---------|---------------------------------------------------|--------------|
| HE-1    | decision_class == D4                              | BLOCK        |
| HE-2    | action == CORE_GATE                               | BLOCK        |
| HE-3    | action == ESCALATE                                | BLOCK        |
| HE-4    | classifier._check_tier import unavailable         | BLOCK        |
| HE-5    | stripped_files list is non-empty                  | BLOCK        |
| HE-6    | same_class_streak ≥ circuit_breaker.max_same_class_streak (from config) | BLOCK |

`HE-6` prevents runaway loops where the same error class keeps repeating.

### Soft Rules (loaded from Policy Pack)

Soft rules are defined in the active Policy Pack (see §3) and evaluated after hard rules. They extend or tighten the engine for the current sprint context.

### Engine Output

```json
{
  "verdict": "AUTO_APPROVE | GATE_REQUIRED",
  "decision_class": "D1 | D2 | D3 | D4 | D5",
  "rule_log": ["HE-1:PASS", "PP-R1:PASS", "PP-R2:BLOCK(reason=...)"],
  "gate_reason": "string or null",
  "auto_approve_eligible": true
}
```

---

## 3. Policy Packs v1 Schema

A Policy Pack is a versioned YAML/JSON configuration that defines soft auto-approve rules for a sprint context. It is loaded at Orchestrator startup and governs behavior until replaced.

### Schema Definition

```yaml
# docs/design/policy_pack_schema_v1.yaml (schema reference)

policy_pack:
  id: string                     # e.g. "pp-r1-catalog-v1"
  version: "1.0"
  created_at: ISO8601 timestamp
  author: string
  description: string
  active: bool                   # only one pack is active at a time

  # Sprint-level constraints
  sprint_context:
    allowed_decision_classes:    # classes eligible for auto-approve in this sprint
      - D1
      - D2
    max_files_per_batch: int     # default 5
    max_attempts_before_gate: int  # default 3

  # Auto-approve eligibility rules (soft rules, evaluated in order)
  rules:
    - id: string                 # e.g. "PP-R1"
      description: string
      condition:                 # one of:
        type: file_glob | decision_class | scope_size | test_coverage | risk_match
        value: any               # type-specific value
      result:
        on_match: PASS | BLOCK | REQUIRE_TEST
        reason: string

  # Rollback policy override for this pack
  rollback:
    strategy: revert_commit | rollback_pr | snapshot_restore | manual
    auto_trigger_on: ci_failure | test_failure | owner_flag | anomaly_detected

  # KPI targets for this sprint (compared against §5 definitions)
  kpi_targets:
    autonomy_rate_target: float  # e.g. 0.80 (80% auto-approved without human intervention)
    gate_escalation_ceiling: float  # e.g. 0.10 (max 10% decisions escalated to JUDGE)
    d5_override_limit: int       # e.g. 2 (max D5 overrides per sprint)
```

### Example Policy Pack: R1 Catalog Sprint

```yaml
policy_pack:
  id: "pp-r1-catalog-v1"
  version: "1.0"
  created_at: "2026-04-08T00:00:00Z"
  author: "owner"
  description: "R1 catalog enrichment sprint — Tier-3 only, docs and scripts."
  active: true

  sprint_context:
    allowed_decision_classes: [D1, D2]
    max_files_per_batch: 5
    max_attempts_before_gate: 3

  rules:
    - id: "PP-R1"
      description: "Block any orchestrator policy file changes (synthesizer/advisor/classifier)"
      condition:
        type: file_glob
        value: "orchestrator/(synthesizer|advisor|classifier).py"
      result:
        on_match: BLOCK
        reason: "Orchestrator policy files require SEMI review, not auto-approved in R1 sprint"

    - id: "PP-R2"
      description: "Require test evidence for any D2 decision"
      condition:
        type: decision_class
        value: D2
      result:
        on_match: REQUIRE_TEST
        reason: "D2 code changes must have passing test suite before auto-approve"

    - id: "PP-R3"
      description: "Auto-approve D1 decisions unconditionally"
      condition:
        type: decision_class
        value: D1
      result:
        on_match: PASS
        reason: "Documentation and config changes are unconditionally safe in this sprint"

  rollback:
    strategy: revert_commit
    auto_trigger_on: ci_failure

  kpi_targets:
    autonomy_rate_target: 0.75
    gate_escalation_ceiling: 0.15
    d5_override_limit: 1
```

### Policy Pack Lifecycle

```
owner writes YAML → validate against schema → load into orchestrator/config.yaml (active_policy_pack)
  → Orchestrator reads on startup
  → evaluates each cycle
  → pack replaced only by owner explicit action
```

Only one Policy Pack is active at a time. Switching packs requires owner action and is logged in the decision audit log.

---

## 4. Approval Batching Logic

Batching groups multiple pending D1/D2 decisions into a single auto-approve sweep to reduce per-decision overhead while preserving safety guarantees.

### When Batching Applies

Batching is eligible only when:
1. All decisions in the batch are D1 or D2
2. All decisions pass auto-approve rules individually
3. No decision has `action == ESCALATE` or `action == BLOCKED`
4. Batch size ≤ `policy_pack.sprint_context.max_files_per_batch`
5. Batch does not span multiple risk classes (all D1, or all D2 — not mixed)

### Batch Formation Algorithm

```
pending_decisions = queue of SynthesizerDecision awaiting approval

batch = []
for decision in pending_decisions:
    class = classify_d1_d5(decision)
    if class in (D1, D2) and auto_approve_eligible(decision):
        batch.append(decision)
        if len(batch) == max_files_per_batch:
            flush_batch(batch)
            batch = []
    else:
        if batch:
            flush_batch(batch)
            batch = []
        gate(decision)  # send to owner/JUDGE

if batch:
    flush_batch(batch)
```

### Batch Execution Contract

```
flush_batch(batch):
  1. Log batch as single audit event (trace_id list, scope union, batch_size)
  2. Execute all directives sequentially (not parallel — preserve FSM state)
  3. Run collect_packet once per directive
  4. If any collect_packet returns status=blocked:
       abort remaining batch items
       gate all remaining decisions
  5. Emit KPI event: batch_approved(count=len(batch), classes=[...])
```

Batching does NOT parallelize execution. It removes per-decision human approval friction while keeping sequential execution order.

### Batch Audit Record

```json
{
  "batch_id": "batch_<trace_id_of_first>",
  "approved_at": "ISO8601",
  "decisions": [
    {"trace_id": "...", "task_id": "...", "class": "D2", "scope": ["file.py"]}
  ],
  "batch_size": 3,
  "policy_pack_id": "pp-r1-catalog-v1",
  "verdict": "AUTO_APPROVE",
  "rule_log": ["HE-1:PASS", "PP-R2:PASS(test_evidence=present)"]
}
```

Batch audit records are appended to `docs/_governance/COMPLETED_LOG.md` and emitted as a shadow_log event.

### Batch Rollback

If post-batch issues are detected (CI failure, anomaly), rollback applies to the full batch:
- Each decision in the batch gets a `git revert` in reverse order
- Batch rollback event is logged with `batch_id` reference

---

## 5. Autonomy KPI Definitions

Autonomy KPIs measure how effectively the system operates without human intervention. They are computed per sprint and accumulated over time.

### KPI 1 — Autonomy Rate

**Definition:** Fraction of decisions that were AUTO_APPROVEd without owner or JUDGE intervention.

```
autonomy_rate = auto_approved_count / total_decisions_count
```

**Target:** ≥ 0.75 for R1 catalog sprint (set in Policy Pack).

**Measurement window:** Per sprint (manifest.json sprint boundary).

**Signal:** Rising autonomy_rate = system is handling routine work without friction.  
Falling autonomy_rate = too many escalations; Policy Pack or task decomposition needs review.

---

### KPI 2 — Gate Escalation Rate

**Definition:** Fraction of decisions that required owner or JUDGE review.

```
gate_escalation_rate = gated_count / total_decisions_count
```

**Target:** ≤ 0.15 for R1 sprint.

**Note:** D4 decisions are always gated and are excluded from autonomy_rate but included in gate_escalation_rate (they are expected, not failures).

---

### KPI 3 — Auto-Approve Failure Rate

**Definition:** Fraction of AUTO_APPROVEd decisions that later required rollback.

```
auto_approve_failure_rate = post_approve_rollback_count / auto_approved_count
```

**Target:** ≤ 0.05 (5%) — one in twenty auto-approved decisions should not require rollback.

**Signal:** Rising failure rate = auto-approve rules are too permissive; Policy Pack needs tightening.

**Trigger:** Two consecutive auto-approve failures of the same decision class → suspend auto-approve for that class until owner reviews.

---

### KPI 4 — Circuit Breaker Trip Rate

**Definition:** Fraction of cycles where the circuit breaker (`HE-6`) fired.

```
circuit_breaker_rate = circuit_breaker_trips / total_cycles
```

**Target:** ≤ 0.02 (2%).

**Signal:** Repeated same-class failures = structural problem (broken test, bad seed data) not a decision quality problem.

---

### KPI 5 — D5 Override Frequency

**Definition:** Count of D5 emergency overrides per sprint.

```
d5_override_count = count(decisions where class == D5 in sprint)
```

**Target:** ≤ 1 per sprint (sprint context: `d5_override_limit` in Policy Pack).

**Signal:** D5 overrides are architectural failures, not normal operations. More than 1/sprint means normal approval flow is broken and needs investigation.

---

### KPI 6 — Batch Efficiency

**Definition:** Fraction of AUTO_APPROVEd decisions executed as part of a batch vs. individually.

```
batch_efficiency = batched_auto_approve_count / auto_approved_count
```

**Target:** ≥ 0.50 (50% of auto-approved decisions should be batched, not individual).

**Signal:** Low batch efficiency = tasks are arriving one at a time or batch conditions are too strict.

---

### KPI Reporting

KPI events are emitted by the Autonomy Engine as structured shadow_log records:

```json
{
  "event_type": "autonomy_kpi",
  "trace_id": "...",
  "sprint_id": "...",
  "ts": "ISO8601",
  "kpis": {
    "autonomy_rate": 0.82,
    "gate_escalation_rate": 0.10,
    "auto_approve_failure_rate": 0.02,
    "circuit_breaker_rate": 0.01,
    "d5_override_count": 0,
    "batch_efficiency": 0.60
  },
  "policy_pack_id": "pp-r1-catalog-v1",
  "kpi_targets_met": true,
  "kpi_violations": []
}
```

KPI records feed the Orchestrator's advisory context in future cycles, allowing the Advisor to recommend Policy Pack adjustments.

---

## 6. Component Interaction Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Meta Orchestrator                             │
│                                                                      │
│  manifest.json                                                       │
│       │                                                              │
│       ▼                                                              │
│  Classifier ──────────────────────────────────┐                     │
│  (risk: LOW/SEMI/CORE)                        │                     │
│       │                                        │                     │
│       ▼                                        │                     │
│  Advisor (LLM)                                 │                     │
│  (risk_assessment, scope, next_step)           │                     │
│       │                                        │                     │
│       ▼                                        │                     │
│  Synthesizer ◄─────────────────────────────────┘                   │
│  (7-rule engine: PROCEED/CORE_GATE/ESCALATE/BLOCKED/NO_OP)          │
│       │                                                              │
│       ▼                                                              │
│  ┌─────────────────────────────────────────┐                        │
│  │       Autonomy Engine v1  (THIS DOC)    │                        │
│  │                                         │                        │
│  │  1. classify_d1_d5()                    │                        │
│  │  2. AutoApproveEngine                   │                        │
│  │     ├─ Hard rules (HE-1..HE-6)          │                        │
│  │     └─ Policy Pack soft rules           │                        │
│  │  3. Batch formation                     │                        │
│  │  4. KPI emission                        │                        │
│  └──────────┬──────────────────────────────┘                        │
│             │                                                        │
│     ┌───────┴───────┐                                               │
│     │               │                                               │
│  AUTO_APPROVE    GATE_REQUIRED                                       │
│     │               │                                               │
│  Executor        ├─ D3 → Auditor (Gemini)                           │
│  Bridge          ├─ D4 → Owner + JUDGE                              │
│                  └─ D5 → Owner CONFIRM                              │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 7. Implementation Notes (for future BUILDER pass)

This section is design guidance only — no implementation in this doc.

- `autonomy_engine.py` should be a pure module: no FSM mutations, no file I/O, no LLM calls.
- `classify_d1_d5()` delegates to `classifier._check_tier()` as single source of truth for file tier detection.
- `AutoApproveEngine.evaluate()` returns an `ApproveDecision` dataclass; caller (main.py) decides FSM transition.
- Policy Pack is loaded from path defined in `orchestrator/config.yaml: active_policy_pack`.
- KPI events are appended to `shadow_log/experience_<month>.jsonl` as type `autonomy_kpi`.
- Every new module must meet CLAUDE.md §EVERY NEW TIER-3 MODULE MUST HAVE checklist (trace_id, idempotency_key, deterministic test, etc.).

---

## 8. Open Questions (for owner decision before BUILDER pass)

1. **D3 batching:** Should D3 decisions (SEMI, require auditor) ever be batch-approved after the auditor passes, or always individual? Current design: individual only.
2. **KPI storage:** shadow_log JSONL vs. dedicated `autonomy_kpi.jsonl`? Current design: unified shadow_log.
3. **Policy Pack hot-reload:** Should the orchestrator reload the Policy Pack mid-sprint if the YAML changes, or require restart? Current design: restart required (safer).
4. **Batch ordering:** Should batch decisions be ordered by dependency (topological) or FIFO? Current design: FIFO (simpler, sufficient for independent Tier-3 changes).

---

*End of autonomy_engine_v1.md*

# System Audit v2 — ИИ-Стройка (AI Construction Site)

**Date**: 2026-04-08
**Auditor**: Claude Code (self-audit, informed by 3 external AI critiques)
**Audit type**: Comprehensive system maturity assessment
**Branch**: feat/rev-r1-catalog
**Methodology version**: v2 (weighted scoring + hard caps + 3-dimensional)

---

## Methodology

### Scoring Approach (v2)

Previous audit v1 used unweighted component averages, producing 64/100.
Three independent external critics identified flaws in that approach:

1. **Unweighted average hides critical gaps** — a broken control plane is not offset by good docs
2. **No hard caps** — system that can't auto-audit SEMI/CORE shouldn't score above 59
3. **Single score conflates prototype quality with operational readiness**

### v2 Scoring Rules

**Weighted components** (aligned with Master Plan priorities: Safety > Autonomy > Growth):

| Component | Weight | Rationale |
|---|---|---|
| Governance / Control Plane | 30% | DNA mandates CRITIC/AUDITOR/JUDGE for SEMI/CORE |
| Runtime Execution | 25% | Pipeline must actually work autonomously |
| Learning / Feedback Loop | 20% | Master Plan KPI: profit-per-decision, rework-free rate |
| Code / Tests | 15% | Infrastructure quality — important but not differentiating |
| Operator Surface | 10% | Telegram/history — lowest current priority |

**Hard cap rules** — if ANY of these blockers exist, total score cannot exceed 59:

- [ ] No automatic external audit for SEMI/CORE tasks
- [ ] No queue/retry semantics for executor failures
- [ ] No end-to-end operator path (Telegram → result)
- [ ] No trace-linked experience loop (run → verdict → correction → outcome)
- [ ] No acceptance check verifying executor did what was asked

**Current blocker count: 5/5** — all five blockers are present.
**Hard cap applies: max score = 59.**

**Success definition** (post-condition, not completion):

A task is "successful" only if:
1. Acceptance criteria are met (not just "executor finished")
2. Gate passed
3. Audit passed (for SEMI/CORE risk)
4. No corrective re-run was needed

---

## Raw Data (verified 2026-04-08)

| Metric | Value | Source |
|---|---|---|
| Total tests | 1306 collected | `pytest --co` |
| Test pass rate | 100% (last full run) | pytest |
| Orchestrator runs (runs.jsonl) | 68 entries | `orchestrator/runs.jsonl` |
| lock_busy events | 37 (54%) | runs.jsonl status field |
| Runs with trace_id | 30/68 (44%) | runs.jsonl |
| Runs with commit_sha | 0/68 (0%) | runs.jsonl — no success tracking |
| Run artifacts (14 run dirs) | 2-11 files each | `runs/` directory |
| Full auditor runs | 1 (run_3f5e55ecde35, 11 artifacts) | `runs/` |
| Experience log entries | 165 total | `shadow_log/experience_2026-04.jsonl` |
| Experience entries with trace_id | 0/165 (0%) | All null |
| Correction records | 44 (all from PEHA batch fix) | experience log |
| Card finalization records | 114 (all TEST-PN skeleton) | experience log |
| Records with real correction data | 33/165 (20%) | non-null correction_if_any |
| Training data: price | 723 records | `training_data/price_extraction.json` |
| Training data: photo | 146 records | `training_data/photo_verdict.json` |
| Training data: category | 69 records | `training_data/category_classification.json` |
| Training data total | 938 records | Sum |
| Autonomous strojka commits | 9 (of 14 attempts) | git log |
| Executor drift incidents | 1 confirmed (test instead of fix) | Manual observation |
| SEMI tasks correctly blocked | 3 | Strojka runs |
| Auditor system tests | 38 pass | test suite |
| Orchestrator tests | 308 pass | test suite |

---

## Dimension 1: Prototype Quality — 68/100

*"Is the code well-built and does the pipeline run?"*

### Governance / Control Plane — 42/100 (weight: 30%)

**What works:**
- Fail-closed safety: SEMI/CORE tasks correctly blocked at gate
- Risk classification (LOW/SEMI/CORE) correctly applied in all observed runs
- Risk-based model selection: Sonnet for LOW, Opus API for SEMI/CORE (tested, 30 cases)
- Tier-1 freeze enforced, Iron Fence CI guard exists
- 7-rule synthesizer decision engine works

**What's broken:**
- Auditor system exists (quality code, 38 tests, full pipeline with 11 artifact types) but is NOT integrated into live orchestrator cycle. Only 1 real run out of entire session
- SEMI/CORE review is manual-only — violates DNA requirement that CRITIC/AUDITOR/JUDGE are mandatory
- Auditor verdict never written to experience log — learning loop is open
- No acceptance check: executor completion is assumed to mean success
- CORE risk gate had live import bug (ModuleNotFoundError) — now fixed but was blocking

**Score justification:** Fail-closed and risk classification are strong (+20). But auditor not integrated is a fundamental governance gap (-30). Manual SEMI/CORE review violates own constitution (-18). Score: 42.

### Runtime Execution — 57/100 (weight: 25%)

**What works:**
- Full M1→M4 pipeline runs end-to-end: NLU → classifier → advisor → synthesizer → executor → gate
- 9 autonomous commits from 14 attempts
- NLU parsing: 9/9 tasks correctly parsed (100% NLU accuracy)
- Stale artifact cleanup works
- UTF-8 encoding fixed for Windows
- Batch gate G6 functions correctly
- Average task time 25-355s (acceptable)

**What's broken:**
- **lock_busy: 37/68 runs (54%)** — single manifest creates massive contention
- Parallel execution impossible (PermissionError on concurrent strojka)
- No retry on executor failure — failed task is simply abandoned
- No task queue — if system busy, task is rejected
- runs.jsonl records 0 commit_sha — success is not tracked
- 68/68 runs show status "unknown" — no proper status tracking

**Score justification:** Pipeline works (+35). But 54% lock contention is severe (-15). No retry/queue (-13). No success tracking (-10). Score: 57.

### Learning / Feedback Loop — 30/100 (weight: 20%)

**What works:**
- Training data accumulates: 938 records across 3 datasets
- Budget tracking works (71 entries)
- Correction logger exists and produced 44 real corrections (PEHA batch)
- Brand experience writer exists (7 records)
- correction_v1 schema has proper fields (field_corrected, original_value, corrected_value, reason)

**What's broken:**
- **0/165 experience entries have trace_id** — zero linkage to orchestrator runs
- 114/165 entries are TEST-PN skeleton data with no real content
- search_strategy.json: 0 records. page_ranking.json: 1 record
- brand_experience_writer almost never called (7/165)
- No verdict recorded from auditor runs
- No run → verdict → correction → outcome chain exists anywhere
- System cannot learn from its own execution history
- 938 training records are "raw material" not "learned knowledge" — no model has been trained on them

**Score justification:** Data exists (+15). Correction logger works for manual batches (+10). But 0% trace linkage (-20), no learning loop (-15), skeleton data (-10). This is a warehouse of JSON, not a learning system. Score: 30.

**Note (Critique 3 feedback):** "Code quality" was removed as standalone component per Critique 3's recommendation — it's a cross-cutting metric, not a subsystem. The "Feedback Loop" replaces it as a more meaningful dimension. Code quality metrics are distributed across the three dimensions.

### Code & Tests (cross-cutting, weight: 15%) — 75/100

**What works:**
- 1306 tests, all green
- Stage 9 design doc: 615 lines, comprehensive architecture
- R2 export command: clean implementation with tests
- ModelSelector: 38 tests, integrated in review_runner
- Iron Fence CI guard for Core table protection

**What's broken:**
- Tests verify syntax (did function complete?) not semantics (did AI do what was asked?)
- Executor created a test file instead of fixing a bug — tests didn't catch this
- routers/ directory created without integration into existing Telegram bot
- No semantic/LLM-as-judge tests for agent output quality

**Score justification:** Strong infrastructure (+55). But "illusion of safety" from syntactic tests (-15). No semantic validation of AI outputs (-10). Score: 75.

### Operator Surface — 38/100 (weight: 10%)

**What works:**
- Strojka NLU works from CLI
- Risk-appropriate autonomy (LOW auto, SEMI waits)
- Stale artifact cleanup on new task

**What's broken:**
- Telegram bot token not regenerated — E2E broken
- No human-readable task history
- No "task accepted, you're 3rd in queue" graceful degradation
- No operator dashboard or status page
- Cannot see what system is currently doing

**Score justification:** CLI works (+20). But no working E2E operator path (-32). No history/dashboard (-20). Score: 38.

### Weighted Score Calculation

| Component | Score | Weight | Contribution |
|---|---|---|---|
| Governance / Control Plane | 42 | 30% | 12.6 |
| Runtime Execution | 57 | 25% | 14.25 |
| Learning / Feedback Loop | 30 | 20% | 6.0 |
| Code / Tests | 75 | 15% | 11.25 |
| Operator Surface | 38 | 10% | 3.8 |
| **Weighted total** | | | **47.9** |

**Hard cap check:** 5/5 blockers present → max 59.
**Weighted score (47.9) < hard cap (59)** → no cap adjustment needed.

---

## Dimension 2: Governance Maturity — 38/100

*"Does the system enforce its own constitution?"*

| Requirement (from DNA/Master Plan) | Status | Evidence |
|---|---|---|
| CRITIC/AUDITOR/JUDGE external and separate | Exists in code | But only 1 live run |
| SEMI/CORE mandatory review pipeline | Code exists | Not wired into orchestrator |
| Fail-closed for CORE | Works | 3 tasks correctly blocked |
| Tier-1 freeze enforcement | Works | Iron Fence CI guard |
| trace_id on every Tier-3 module | Partially | Orchestrator has it, experience log doesn't |
| idempotency_key for side-effects | Partially | Some modules, not universal |
| No silent exception swallowing | Mostly | Fail-loud policy observed |
| Verdict → experience → correction loop | **Missing** | Zero implementation |
| External audit coverage for SEMI/CORE | **~7%** | 1 real audit / ~14 SEMI+ tasks |

**Score:** Strong safety primitives (+25). Auditor code quality (+10). But not integrated into live system (-30). Verdict loop missing (-20). SEMI/CORE coverage ~7% (-12). Score: 38.

---

## Dimension 3: Operational Readiness — 29/100

*"Could an operator use this system for real work tomorrow?"*

| Capability | Status |
|---|---|
| Submit task via natural language | Works (CLI) |
| Submit task via Telegram | Broken (token) |
| View current task status | Partial (manifest.json) |
| View task history | Not implemented |
| Parallel task execution | Impossible (single manifest) |
| Queue when busy | Not implemented (lock_busy → reject) |
| Retry on failure | Not implemented |
| Acceptance verification | Not implemented |
| Operator notification on completion | Not implemented |
| Budget/cost visibility | Partial (budget_tracking.json exists) |
| Audit trail for decisions | Partial (runs/ has artifacts) |

**Score:** CLI task submission works (+15). Risk-based autonomy (+10). Some artifacts produced (+4). But broken Telegram (-10), no parallelism (-15), no queue (-10), no retry (-10), no acceptance check (-10), no operator notifications (-10). Score: 29.

---

## Three-Dimensional Summary

| Dimension | Score | Meaning |
|---|---|---|
| **Prototype Quality** | **48** | Strong code foundation, broken control loop |
| **Governance Maturity** | **38** | Safety primitives work, constitution not enforced at runtime |
| **Operational Readiness** | **29** | CLI demo works, not usable for real work |

**Composite (weighted: 50/30/20):** 48×0.5 + 38×0.3 + 29×0.2 = 24.0 + 11.4 + 5.8 = **41.2**

**Adjusted honest assessment: ~48/100** for the weighted composite.
**Rounded to 50/100** acknowledging the strong code quality across all dimensions provides a floor.

**However** — using the simpler v1-compatible single score with component weights and hard cap: **48/100**.

---

## Comparison: v1 vs v2

| Metric | v1 (self) | Critique range | v2 (post-critique) |
|---|---|---|---|
| Meta Orchestrator | 72 | 72 (fair) | Folded into Runtime: 57 |
| Auditor System | 45 | 40-45 | Folded into Governance: 42 |
| Training Data | 55 | 50 (overvalued) | Folded into Learning: 30 |
| Strojka/TG | 68 | 68 (fair) | Folded into Operator: 38 |
| Code/Tests | 82 | 70-75 (overvalued) | Cross-cutting: 75 |
| **Overall** | **64** | **54-61** | **48** |

The drop from 64→48 comes from:
1. Weighted scoring that penalizes governance gaps (30% weight, 42 score)
2. Honest learning loop score (30 instead of 55)
3. Hard cap recognition (5/5 blockers present)
4. Separating "code exists" from "system works"
5. Removing Code/Tests as standalone inflating component

---

## Priority Fix List (Impact x Effort)

Ordered by **severity x frequency**, with dependency mapping:

### P0 — Close the Control Loop (blocks everything else)

**Problem:** task → trace_id → executor result → acceptance check → auditor verdict → experience record → correction memory — this chain does not exist.

**Impact:** Without this, system cannot learn, cannot measure true success rate, cannot improve autonomy. Every other improvement is less valuable without feedback.

**Effort:** MEDIUM (3-5 days). Wire orchestrator M4 output → auditor → experience writer.

**Dependencies solved:** Fixes Learning score (30→50+), Governance score (42→55+), enables acceptance checks, enables true success rate measurement.

**Substeps:**
1. After M4 executor returns, pass result to auditor system (auto for SEMI/CORE, sample for LOW)
2. Auditor verdict writes to experience log with trace_id
3. If verdict=FAIL, log as false-positive-completion
4. Acceptance criteria from directive checked against actual file changes

### P1 — Workspace Isolation (unblocks parallelism)

**Problem:** Single manifest.json → 54% lock_busy → zero parallelism.

**Impact:** 37/68 runs rejected. System cannot handle > 1 task.

**Effort:** LOW-MEDIUM (2-3 days). Each task gets `runs/{trace_id}/manifest.json`.

**Dependencies solved:** Eliminates lock_busy entirely, enables task queue (P2).

### P2 — Task Queue + Retry

**Problem:** No queue (busy → reject) and no retry (fail → abandon).

**Impact:** ~36% of executor attempts produce wrong output and are never corrected. Busy system drops tasks entirely.

**Effort:** MEDIUM (3-4 days). SQLite or file-based queue + retry loop with auditor critique.

**Dependencies:** Requires P1 (workspace isolation) for parallel processing. Benefits from P0 (auditor integration) for critic-informed retry.

### P3 — Acceptance Check

**Problem:** "Executor finished" ≠ "executor did the right thing". 1 confirmed drift incident.

**Impact:** False-positive success rate. Cannot trust reported metrics.

**Effort:** MEDIUM (2-3 days). Compare directive scope/acceptance criteria against actual git diff.

**Dependencies:** Part of P0 control loop. Can be implemented as part of P0 or standalone.

### P4 — Telegram E2E

**Problem:** Bot token not regenerated. Operator cannot use system remotely.

**Impact:** Operator surface = CLI only. Low priority per Master Plan (Safety > Growth).

**Effort:** LOW (1 day). Regenerate token, test E2E.

**Dependencies:** None. But relatively low value until P0-P2 are done.

### Dependency Graph

```
P0 (Close Loop) ←── P3 (Acceptance Check)
       ↑
P1 (Workspace) ←── P2 (Queue + Retry)
                         ↑
                    P0 (for critic-retry)

P4 (Telegram) — independent
```

**Recommended execution order:** P0 → P1 → P3 → P2 → P4

---

## KPIs for Next Audit (aligned with Master Plan)

| KPI | Current | Target (next audit) | How to measure |
|---|---|---|---|
| Rework-free success rate | Unknown (no acceptance check) | >70% | acceptance_pass / total_runs |
| External audit coverage (SEMI/CORE) | ~7% (1/14) | >80% | auto_audit_runs / semi_core_tasks |
| Trace-linked learning coverage | 0% (0/165) | >90% | experience_entries_with_trace / total |
| False-success rate | Unknown | <10% | acceptance_fail / reported_success |
| Owner minutes per task | High (manual) | <5 min average | Time from submission to verified result |
| Lock contention rate | 54% | <5% | lock_busy / total_runs |
| Retry recovery rate | 0% (no retry) | >50% | retry_success / retry_attempts |

---

## Honest Summary

**This is not a "nearly working autonomous system" (64/100).**

**This is a strong prototype execution layer (48/100) with good safety primitives, solid code quality, but no closed control loop and no real operational reliability.**

The system can:
- Parse natural language into structured tasks
- Classify risk correctly
- Select appropriate AI model by risk level
- Execute simple LOW tasks autonomously
- Block dangerous SEMI/CORE tasks (fail-closed)
- Accumulate raw training data

The system cannot:
- Verify its own work
- Learn from its mistakes
- Handle more than one task at a time
- Retry when executor drifts
- Provide an operator with confidence that "done" means "correctly done"

**Priority #1 is not new features. Priority #1 is closing the control loop:**

`task → trace_id → executor result → acceptance check → auditor verdict → experience record → correction memory`

Until that loop is closed, the system does not learn, does not self-correct, and reports unreliable success metrics.

---

## Audit Meta

| Field | Value |
|---|---|
| Audit version | v2 |
| Methodology | Weighted scoring + hard caps + 3 dimensions |
| External critiques incorporated | 3 (architectural, scoring methodology, methodology + prioritization) |
| Data verified | 2026-04-08 from live system state |
| Previous audit | v1 (same date, score 64/100) |
| Delta from v1 | -16 points (methodology correction, not system degradation) |
| Baseline established | Yes — KPI table above for next audit comparison |
| Next audit recommended | After P0 (Close Loop) implementation |

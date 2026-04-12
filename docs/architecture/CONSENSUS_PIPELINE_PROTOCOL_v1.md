# Consensus Pipeline Protocol v1

**Status:** IMPLEMENTED — audit remediation in progress
**Date:** 2026-04-13
**Origin:** Architecture research session (Opus), 5 proposals synthesized

## Problem Statement

Current AI-стройка pipeline has an open loop: Builder writes code, Critics audit it,
but critique findings are never fed back into a repair cycle. The system produces
a verdict and stops. Additionally, LLM critics only review code text — they never
verify that code actually runs. This leads to multiple manual owner intervention
cycles, contradicting autonomy goals.

## Formula

```
ARCHITECT → CRITIC → PLANNER → BUILDER →
  L2 Loop (max 3): [execute → assert → fix if fail] →
  L1 Loop (max 2): [critics review code+output → defect register → repair → re-execute] →
  L3: bounded pipeline run on golden dataset →
  JUDGE → MERGE
```

### Three Verification Levels

| Level | Who | What | Cost |
|-------|-----|------|------|
| **L2: Execution** | Real run (CPU) | Code works, output correct | Free (CPU) |
| **L1: Static+Output** | AI critics (API) | Code logical, output reviewed, defects tracked | ~$0.30/round |
| **L3: Integration** | Pipeline run (CPU) | End-to-end on golden dataset vs reference | Free (CPU) |

Key insight: L2 runs BEFORE L1. Critics receive execution results, not just code.
This eliminates hallucinations about "how code might work" and saves API budget
by not sending broken code to critics.

---

## 1. Data Structures

### 1.1 Defect Register

Central artifact. Stored in `run_store` as `defect_register.json`.

```python
class DefectEntry:
    defect_id: str          # "D-001"
    source: str             # "gemini" | "claude" | "l2_execution" | "l3_integration"
    severity: str           # "blocker" | "major" | "minor" | "nit"
    scope: str              # "correctness" | "architecture" | "invariants" | "tests" | "safety" | "style"
    description: str
    evidence: str           # concrete line/file/traceback
    required_fix: str
    status: str             # "OPEN" | "FIXED_PENDING" | "CLOSED" | "WAIVED" | "HALTED"
    validated_by: str | None  # "l2_rerun" | "gemini" | "claude" | "judge"
    iteration_opened: int
    iteration_closed: int | None
```

Status rules:
- `WAIVED` — only for `minor`/`nit`, only JUDGE can waive
- `blocker`/`major` — cannot be WAIVED, only CLOSED or HALTED
- Register assembly is **deterministic** (union + dedup by file+description_hash), not LLM

### 1.2 Repair Manifest

Builder generates after each repair pass:

```python
class RepairEntry:
    defect_id: str          # "D-001"
    action: str             # "FIXED" | "CANNOT_FIX"
    changes: list[str]      # ["file.py:42-55 — replaced X with Y"]
    reason: str | None      # mandatory for CANNOT_FIX
    test_evidence: str | None  # "pytest test_x::test_y PASSED"
```

`CANNOT_FIX` — builder does NOT reject the issue (executor ≠ judge), but explains
why it cannot fix (frozen file, out of scope). Decision is made by critic or owner.

### 1.3 L2 Validation Evidence Pack

Bridge between L2 and L1. Generated automatically, not by LLM:

```python
class L2Report:
    exit_code: int
    duration_seconds: float
    assertions: list[AssertionResult]  # machine asserts
    diff_stat: str           # git diff --stat
    traceback_tail: str | None  # last 50 lines stderr if exit_code != 0
    output_sample: str       # first 2KB stdout (not all)
```

**Max size: 8KB.** If larger — trim. Critics must not drown in logs.

Each assertion:
```python
class AssertionResult:
    name: str       # "coverage_not_regressed"
    expected: str   # ">= 365"
    actual: str     # "367"
    status: str     # "PASS" | "FAIL"
```

### 1.4 Golden Dataset (for L3)

Fixed sample of 25-30 evidence files:
- 5 Honeywell (different suffixes: .10, -RU, -L3, N_U)
- 3 PEHA (electrical accessories, problematic category)
- 3 DKC
- 3 Dell/NVIDIA (non-Honeywell brands)
- 3 with empty fields (no price, no photo)
- 3 with weak identity
- 5 edge cases from `KNOW_HOW.md`

Reference results fixed in `tests/golden/expected/`. L3 compares output with
reference deterministically.

---

## 2. Exit Criteria

### L2 Exit (execution)

```
PASS when ALL satisfied:
  - exit_code == 0
  - all assertions PASS
  - no uncaught exceptions in stderr
  - coverage_after >= coverage_before (if applicable)

FAIL → builder fix → retry (max 3)
HALT after 3 FAIL → task marked HALTED, does NOT go to critics
```

### L1 Exit (critics)

```
PASS when ALL satisfied:
  - 0 defects with status OPEN and severity blocker/major
  - both critics: all blocker/major = CLOSED
  - DISAGREE between critics resolved (via structured cross-review)

FAIL → builder repair → L2 re-run → L1 re-review (max 2 iterations)
HALT after 2 L1 iterations with open blockers → JUDGE or owner
```

### L3 Exit (integration)

```
PASS when:
  - golden dataset run: 0 regressions vs reference
  - no new assertion failures
  - output parseable (valid JSON, required fields present)

FAIL → return to L2 (new defect in register from source "l3_integration")
```

---

## 3. Critics Interaction Protocol

### Round 1 — Blind pass
- Gemini and Claude receive: diff + L2Report + task description
- Each works in isolation
- Output: structured `AuditVerdict` with `DefectEntry[]`

### Cross-validation
Each critic receives the other's defect list and responds **per-issue**:

```
AGREE — confirmed, real problem
DISAGREE(reason: "false_positive" | "wrong_severity" | "out_of_scope") — with explanation
ESCALATE — cannot evaluate
```

`DISAGREE` without reason = invalid response, retry with strict prompt.

### Consolidation (deterministic, not LLM)
- AGREE from both → issue in register
- AGREE + DISAGREE → issue in register (conservative)
- DISAGREE from both → issue dropped
- Any ESCALATE → issue in register + flag for JUDGE

### Debate optimization
Debate (cross-validation) runs ONLY when critics disagree. If both say PASS —
fast path to merge (preserves existing `should_debate()` logic from `debate.py`).
If both say FAIL with overlapping issues — straight to rework, no debate needed.
Debate only fires on actual verdict conflict. This halves LLM calls in the common case.

### Round 2+ (after repair)
Critic receives:
- Repair manifest (per-issue)
- New L2Report
- Current defect register with statuses (ALL issues, not just "own")
- Original diff (anchor — critic needs it to check regressions)
- Checklist:
  1. Issue X — fixed completely / partially / not fixed?
  2. Any new defects introduced by repair?
  3. Safe to merge?

Each critic reviews ALL consolidated issues (not just issues they originally found),
because a fix for issue #1 may regress the area covered by issue #2.

### Translation layer: issues → builder prompt
Builder (Claude Code) is a conversation agent, not an API consumer. Raw
`DefectEntry[]` is written for critics, not for builder. The orchestrator
(`review_runner.py`) must include a deterministic `build_repair_prompt()` that
converts OPEN defects into an actionable builder prompt:

```
Fix these defects:
1. [D-001] blocker in file.py:42 — description. Required: required_fix.
2. [D-003] major in utils.py:15 — description. Required: required_fix.

Rules:
- Generate repair_manifest with per-defect response (FIXED or CANNOT_FIX)
- Do NOT modify validation scripts (frozen_for_task)
- If you cannot fix, mark CANNOT_FIX with reason (constraint, not rejection)
```

This is a string template, not an LLM call.

### Partial fix protocol
When builder fixes some issues but marks others as CANNOT_FIX:

1. ALL issues go to re-review (not just FIXED ones)
2. Critic confirms each FIXED issue is actually resolved
3. For each CANNOT_FIX, critic decides:
   - If minor/nit: can recommend WAIVED (JUDGE confirms)
   - If blocker/major: ESCALATE to owner (cannot be waived)
   - If constraint is wrong (builder misidentified frozen file): reopen as OPEN
4. Register is only clean when: 0 OPEN blocker/major remaining

---

## 4. Safety Mechanisms

### Frozen validation scripts
L2/L3 gate scripts are marked `frozen_for_task` in `TaskPack`. Builder cannot
modify them. If builder touches validation script → A6 warning escalates to
**hard block** (not just warning).

### Budget control
```
L2 loop: free (CPU only)
L1 round: ~$0.15-0.30 (2 critics x review + cross-validation)
L1 max 2 rounds: ~$0.60 max
L3: free (CPU only)
JUDGE (if needed): ~$0.10
Total max per task: ~$0.70-0.80
```
Soft warning at $0.50. Hard stop at $1.00 per task → escalate to owner.

### Circuit breaker
- L2 x 3 FAIL → HALTED (does not go to critics)
- L1 x 2 FAIL → JUDGE or owner
- L3 FAIL → return to L2 (max 1 time, then HALTED)
- Total max iterations across all levels: **8** (3 L2 + 2 L1 + 2 L2-from-L3 + 1 final L3)

---

## 5. Integration with Existing Code

### Extend (do not rewrite)

| File | Change |
|------|--------|
| `contracts.py` | + `DefectEntry`, `RepairManifest`, `L2Report`, `DefectRegister` |
| `review_runner.py` | Wrap steps 4-9 in repair loop; add L2 gate before critics |
| `run_store.py` | + `save_defect_register()`, `save_l2_report()`, `save_repair_manifest()` |
| `quality_gate.py` | Check defect register statuses instead of raw verdicts |
| `debate.py` | Replace free debate with structured cross-validation |
| `providers/base.py` | + `re_review(defect_register, repair_manifest, l2_report)` in `AuditorProvider` |

### Create new

| File | Purpose |
|------|---------|
| `auditor_system/execution_gate.py` | L2 runner: pytest + dry-run + assertions + L2Report |
| `auditor_system/integration_gate.py` | L3 runner: golden dataset run + comparison with reference |
| `tests/golden/` | Golden dataset + expected outputs |

### Do not touch (protected governance surface)

- `approval_router.py` — routing logic stays
- `experience_sink.py` — DPO logging stays as-is
- Everything from DNA §3 frozen files

---

## 6. Sequence Diagram

```
Owner assigns task
        │
   ARCHITECT → CRITIC → PLANNER
        │
      BUILDER writes code
        │
   ┌────▼─────────────────────┐
   │  L2 LOOP (max 3)        │
   │  execute → assert        │
   │  FAIL? → fix → retry    │
   │  3x FAIL? → HALTED      │
   └────┬─────────────────────┘
        │ L2 PASS
   ┌────▼─────────────────────┐
   │  L1 LOOP (max 2)        │
   │  blind critique          │
   │  cross-validation        │
   │  consolidate register    │
   │  OPEN blockers?          │
   │  → repair → L2 re-run   │
   │  → L1 re-review          │
   │  2x FAIL? → JUDGE/owner │
   └────┬─────────────────────┘
        │ L1 PASS
   ┌────▼─────────────────────┐
   │  L3 (golden dataset)    │
   │  FAIL? → new defect     │
   │  → back to L2            │
   │  PASS? → continue       │
   └────┬─────────────────────┘
        │ L3 PASS
      JUDGE → MERGE
```

---

## Origin & Research Notes

This protocol was synthesized from 5 proposals discussed in an architecture
research session on 2026-04-13. Key insights:

1. **Proposals 1-2** correctly identified the open loop problem but designed
   from scratch, ignoring existing `review_runner.py` infrastructure.
2. **Proposal 3** was closest to repo reality — introduced Defect Register
   concept and distinguished CRITIC/AUDITOR/JUDGE roles properly.
3. **Owner's critical insight:** LLM consensus alone is insufficient.
   Real execution (L2/L3) must precede and inform critic review.
4. **External critique 1:** Builder must not modify validation scripts
   (frozen_for_task). Context bloat between L2→L1 needs trimming.
5. **External critique 2:** Confirmed formula maturity, identified 4
   remaining formalization needs (exit criteria, formats, statuses, budget).
6. **Proposal 2 self-critique:** Admitted "only own issues" was a bug,
   accepted CANNOT_FIX over REJECTED (executor ≠ judge), confirmed
   need for translation layer (issues → builder prompt) and partial fix protocol.

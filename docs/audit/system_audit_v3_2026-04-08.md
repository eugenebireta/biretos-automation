# System Audit v3 — ИИ-Стройка Post-P0 Reassessment

**Date**: 2026-04-08 (evening, same day as v2)
**Auditor**: Claude Code (self-audit, v2 methodology)
**Context**: Re-assessment after implementing P0 (close the control loop)
**Branch**: feat/rev-r1-catalog (115 commits ahead of master)
**Previous audit**: v2 same date, score 48/100

---

## What Changed Since v2

In the ~2 hours since v2 was written, the following was implemented and **live-tested**:

| Change | Evidence |
|---|---|
| `acceptance_checker.py` (220 lines) | 5 checks: A1:NON_EMPTY, A2:TIER1_SAFE, A3:TESTS_PASS, A4:SCOPE_COMPLIANCE, A5:TASK_ID_INTEGRITY |
| `experience_writer.py` (192 lines) | `execution_experience_v1` schema, mandatory trace_id (ValueError on null), idempotent per trace_id |
| `main.py` wired control loop | Every executor path → acceptance → experience. Escalation/synth block also recorded |
| All `append_run` calls have `status` | Was: 69/79 "missing". Now: new entries have real status |
| **Live test via strojka** | Task "add A5 check" → executor completed → **drift detected** (12 out-of-scope files) → `ACCEPTANCE_FAILED` → experience record with trace_id written |
| A5 check added by executor | Executor itself contributed A5:TASK_ID_INTEGRITY check (confirmed working) |
| 1352 tests pass | +46 from v2 baseline (1306) |

---

## Methodology (same as v2)

Weighted components: Governance 30%, Runtime 25%, Learning 20%, Code 15%, Operator 10%.
Hard caps: 5 critical blockers → max 59.
3 dimensions: Prototype Quality, Governance Maturity, Operational Readiness.

---

## Hard Cap Blockers Reassessment

| Blocker | v2 Status | v3 Status | Evidence |
|---|---|---|---|
| No automatic external audit for SEMI/CORE | Present | **Present** | Auditor still not auto-triggered for SEMI/CORE in orchestrator loop |
| No queue/retry semantics | Present | **Present** | Still single manifest, no retry on drift |
| No end-to-end operator path | Present | **Present** | Telegram token still broken |
| No trace-linked experience loop | **Present** | **RESOLVED** | Live proof: `orch_20260408T202825Z_48ecb0` → `ACCEPTANCE_FAILED` with trace_id |
| No acceptance check | **Present** | **RESOLVED** | 5 checks implemented, drift caught in live test |

**Blockers: 3/5 remain → hard cap still 59.**

---

## Component Scores

### Governance / Control Plane — 49/100 (was 42, +7)

**Improved:**
- Acceptance checker now enforces directive scope (+5)
- Experience records with trace_id close the basic learning loop (+3)
- Drift detection works — live proof of false-positive prevention (+2)
- All run events now have proper `status` field (+1)

**Still broken:**
- Auditor system still not wired into live orchestrator (SEMI/CORE auto-audit missing)
- CRITIC/AUDITOR/JUDGE chain still manual-only
- Only 1 execution_experience_v1 record exists (need more data to validate pattern)

**Why only +7:** Acceptance checker is a significant governance improvement, but auditor integration (the bigger half of the governance gap) remains untouched. The 5-check acceptance is deterministic rules — no LLM-based semantic verification yet.

### Runtime Execution — 58/100 (was 57, +1)

**Improved:**
- Control loop flow now includes acceptance → experience (cleaner pipeline)
- FSM correctly transitions to `awaiting_owner_reply` on drift (not silent pass)

**Still broken:**
- lock_busy: 8 new entries in this session alone (now 45/79 = 57% — worse than v2's 54%)
- No retry on acceptance failure
- No task queue
- Single manifest

**Why only +1:** The runtime pipeline is slightly better (acceptance integrated), but the fundamental bottleneck (single manifest, no queue) is untouched, and lock contention actually worsened.

### Learning / Feedback Loop — 40/100 (was 30, +10)

**Improved:**
- First-ever execution_experience_v1 record with real trace_id (+8)
- Record includes: verdict, drift_detected, acceptance_checks, changed_files, elapsed_seconds
- Idempotency enforced (duplicate trace_id → skip)
- Schema supports full chain: trace → verdict → correction_needed → correction_detail
- Failure paths also record experience (advisor escalation, synth block, executor fail)

**Still limited:**
- Only 1 new-schema record vs 183 old-schema skeleton records
- Old records (experience_log_v1) still have 0 trace_id — no migration path
- No actual correction-from-experience yet (records exist but nothing reads them to improve)
- Training data (938 records) still disconnected from execution experience
- search_strategy: 0 records, page_ranking: 1 record — no search learning

**Why +10 not more:** The infrastructure is built and proven working. But 1 record is a proof of concept, not a learning system. The loop is architecturally closed but not yet producing learning outcomes.

### Code / Tests — 78/100 (was 75, +3)

**Improved:**
- 1352 tests (was 1306, +46 new)
- acceptance_checker: 14 deterministic tests covering all 5 checks
- experience_writer: 12 tests including idempotency and null-trace rejection
- control_loop integration: 3 tests (success, drift, executor failure)
- A5:TASK_ID_INTEGRITY check added and tested (by executor itself — meta!)

**Still limited:**
- No semantic/LLM-as-judge tests for AI output quality
- 1 flaky test in enrichment (test_research_providers — not our code)
- Executor's own A5 implementation raises ValueError instead of returning AcceptanceCheck(passed=False) — inconsistent with A1-A4 pattern

### Operator Surface — 38/100 (unchanged)

No changes to operator surface in this cycle. Telegram still broken, no dashboard, no history view.

---

## Weighted Score

| Component | Score | Weight | Contribution |
|---|---|---|---|
| Governance / Control Plane | 49 | 30% | 14.7 |
| Runtime Execution | 58 | 25% | 14.5 |
| Learning / Feedback Loop | 40 | 20% | 8.0 |
| Code / Tests | 78 | 15% | 11.7 |
| Operator Surface | 38 | 10% | 3.8 |
| **Weighted total** | | | **52.7** |

**Hard cap check:** 3/5 blockers remain → max 59.
**Score 52.7 < cap 59** → no adjustment needed.

---

## Three Dimensions

| Dimension | v2 | v3 | Delta |
|---|---|---|---|
| **Prototype Quality** | 48 | **53** | +5 |
| **Governance Maturity** | 38 | **43** | +5 |
| **Operational Readiness** | 29 | **31** | +2 |

---

## Delta from v2

| Metric | v2 | v3 | Change |
|---|---|---|---|
| Weighted score | 48 | **53** | **+5** |
| Tests | 1306 | 1352 | +46 |
| Blockers resolved | 0/5 | **2/5** | +2 |
| Experience records with trace_id | 0/165 | **1/184** | +1 (from 0%) |
| Runs with real status | 0/68 | 10/79 | +10 |
| Acceptance checks | 0 | **5 (A1-A5)** | new capability |
| Drift detection | none | **working** | new capability |
| Lock contention | 54% | 57% | -3% (worse) |

**Score change: +5 points.** This is honest — the P0 implementation is architecturally significant but only partially realized. The full value will show when:
1. Multiple runs accumulate experience data
2. Auditor is wired in for SEMI/CORE
3. Retry loop uses acceptance failure to refine directives

---

## What Was Done Well

1. **Control loop proven in live fire.** Not just code — ran a real strojka task and the acceptance checker caught drift. First system in the project that verifiably prevents false-positive success.

2. **Executor drift detection works.** The strojka test asked for 2 files, executor touched 13. Old system: "success". New system: `ACCEPTANCE_FAILED` with list of 12 out-of-scope files. This is the exact scenario all 3 critics identified.

3. **Experience schema is right.** `execution_experience_v1` captures: trace_id, overall_verdict (PASS/ACCEPTANCE_FAILED/GATE_FAILED/EXECUTOR_FAILED/EARLY_FAILURE/AUDIT_FAILED), drift_detected, acceptance_checks, correction_needed. This is trainable data.

4. **Fail-loud enforcement.** `experience_writer` raises ValueError on null trace_id — physically impossible to write skeleton records.

5. **Every failure path records experience.** Advisor escalation, synth block, executor fail, collect fail — all write experience records now.

6. **Meta-quality: executor improved its own checker.** The A5 check was added by the autonomous executor during the live test. The system is starting to build its own governance infrastructure.

---

## What Was Done Poorly

1. **Auditor still not integrated.** P0 was supposed to be "close the control loop" — but the loop is only half-closed. Acceptance checker (deterministic rules) ≠ auditor (LLM-based semantic review). For SEMI/CORE tasks, acceptance alone is insufficient.

2. **Lock contention worsened.** 57% lock_busy (was 54%). The live strojka test triggered 3 more lock_busy events. This is a fundamental architectural flaw that gets worse with usage, not better.

3. **No retry on drift.** Acceptance checker detects drift but the system just stops and waits for owner. A smarter system would retry with a tightened directive: "You touched 12 extra files. Only touch these 2 files."

4. **Old experience records not migrated.** 183 old-schema records with null trace_id sit alongside 1 new-schema record. No migration path, no cleanup plan.

5. **A5 implementation inconsistency.** Executor's A5 check raises ValueError on violation (hard crash) while A1-A4 return AcceptanceCheck(passed=False). This is a bug — should be consistent.

6. **Budget tracking empty.** budget_tracking.json has 0 entries despite multiple API calls in this session. Cost visibility remains zero.

---

## What Can Be Done Better

### Priority Fixes (updated from v2)

| Priority | Problem | Impact | Effort | Status |
|---|---|---|---|---|
| **P0** | Close control loop | Foundation for learning | 3-5 days | **DONE (partially — acceptance only, no auditor)** |
| **P0.5** | Wire auditor into loop for SEMI/CORE | Closes governance gap | 2-3 days | **NEW — next priority** |
| **P1** | Workspace isolation | Eliminates lock_busy | 2-3 days | Not started |
| **P1.5** | Fix A5 ValueError → AcceptanceCheck | Consistency | 0.5 day | **NEW — quick fix** |
| **P2** | Task queue + retry | Handles busy + drift recovery | 3-4 days | Not started |
| **P3** | Acceptance-informed retry | Uses drift data to refine directive | 2-3 days | Not started |
| **P4** | Telegram E2E | Operator surface | 1 day | Not started |

### Dependency update
```
P0 (done) → P0.5 (auditor wire) → P3 (retry with critique)
              ↓
P1 (workspace) → P2 (queue + retry)

P1.5 (A5 fix) — independent, quick
P4 (telegram) — independent, low priority
```

---

## KPI Progress

| KPI | v2 Baseline | v3 Current | Target |
|---|---|---|---|
| Rework-free success rate | Unknown | **0% (1 run, 1 drift)** | >70% |
| External audit coverage (SEMI/CORE) | ~7% | ~7% (unchanged) | >80% |
| Trace-linked learning coverage | 0% (0/165) | **0.5% (1/184)** | >90% |
| False-success rate | Unknown | **100% prevented (1/1 drift caught)** | <10% |
| Lock contention rate | 54% (37/68) | **57% (45/79)** | <5% |

---

## Honest Summary

**Score: 53/100** (was 48/100 in v2, +5 points).

The system now has a working acceptance checker that catches executor drift — proven in live fire. The first execution_experience_v1 record with a real trace_id exists. The control loop is architecturally closed for the acceptance half.

**But:**
- Auditor is still disconnected (governance half of the loop still open)
- Lock contention is getting worse, not better
- 1 experience record is a proof of concept, not a pattern
- No retry capability — drift is detected but not corrected

**Maturity statement:** This is a **strong prototype (53/100) with a working safety net (acceptance checker) but without self-correction (retry) or full governance enforcement (auditor integration).**

The +5 from v2 is earned — acceptance checking is a real capability that prevents false positives. But it's not transformative. The next +10-15 points will come from P0.5 (auditor integration) and P1 (workspace isolation), which together would push the score to ~65-70.

---

## Audit Meta

| Field | Value |
|---|---|
| Audit version | v3 |
| Methodology | v2 (weighted + hard caps + 3 dimensions) |
| Data verified | 2026-04-08 from live system state |
| Previous audit | v2 (same date, score 48/100) |
| Delta from v2 | +5 points (P0 partial implementation) |
| Live test | strojka task → ACCEPTANCE_FAILED (drift caught) |
| Next audit recommended | After P0.5 (auditor integration) or P1 (workspace isolation) |

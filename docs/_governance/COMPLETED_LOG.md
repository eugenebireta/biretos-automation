---
DATE: 2026-03-22
TITLE: Governance Doc Closeout — DNA v2.1 + docs/ reorg + MIGRATION_POLICY NLU checks
RISK_LEVEL: LOW
SCOPE:
  - docs/PROJECT_DNA.md (MERGED from PROJECT_DNA_v2_0.md + PROJECT_DNA.md — v2.1, §1b, §6 R4, §7 items 6-9, §10 4 new checklist items)
  - docs/MASTER_PLAN_v1_9_1.md (MOVED from root, TD header fix v1.9.0→v1.9.1)
  - docs/EXECUTION_ROADMAP_v2_3.md (MOVED from root)
  - _archive/ (6 old docs from "old md/": ROADMAP v1.0/v2.0/v2.3-old, MASTER_PLAN v1.4.3/v1.7.2/v1_9_0)
  - CLAUDE.md (all doc path references updated)
  - docs/claude/MIGRATION_POLICY_v1_0.md (CRITIC items 6-9, AUDITOR items 8-10 added)
  - PROJECT_DNA.md, PROJECT_DNA_v2_0.md (DELETED from root)
BRANCH: feat/task-7
COMMITS: 52372fc, a5a9767, 20bbbab, ba15982
SUMMARY: >
  Documentation governance session: merged two DNA files into docs/PROJECT_DNA.md v2.1
  (added §1b hierarchy, R4 Anchor Buyer Liquidation scope, §7 patterns 6-9, §10 4 new
  checklist items). Moved MASTER_PLAN and ROADMAP to docs/. Archived 6 old versions.
  Updated CLAUDE.md paths. Added NLU-specific CRITIC/AUDITOR review checks to
  MIGRATION_POLICY (INV-MBC, shadow isolation, no nested FSM, NLU wrapper check,
  degradation safety). PR #9 still open, awaiting external CRITIC/AUDITOR/JUDGE.
STATUS: CLOSED (doc tasks complete; PR #9 remains open for code review)
---
DATE: 2026-03-22
TITLE: Phase 7 — AI Executive Assistant NLU (Pass 2 complete, PR open)
RISK_LEVEL: CORE
SCOPE:
  - migrations/029_assistant_nlu.sql (NEW)
  - domain/nlu_models.py (NEW)
  - domain/assistant_models.py (NEW)
  - domain/intent_parser.py (NEW)
  - domain/prompt_injection_guard.py (NEW)
  - domain/guardian.py (MODIFIED — guard_nlu_confirmation + whitelist)
  - config/schema.py (MODIFIED — 7 NLU env vars)
  - config/validator.py (MODIFIED — NLU parsing)
  - ru_worker/nlu_confirmation_store.py (NEW)
  - ru_worker/nlu_shadow_log.py (NEW)
  - ru_worker/nlu_sla_tracker.py (NEW)
  - ru_worker/assistant_router.py (NEW)
  - ru_worker/telegram_router.py (MODIFIED — free-text + nlu callbacks)
  - ru_worker/dispatch_action.py (MODIFIED — nlu_parse/nlu_confirm routing)
  - tests/test_intent_parser.py (NEW, 21 tests)
  - tests/test_prompt_injection_guard.py (NEW, 15 tests)
  - tests/test_nlu_confirmation_store.py (NEW, 9 tests)
  - tests/test_nlu_sla_tracker.py (NEW, 7 tests)
  - tests/test_assistant_router.py (NEW, 8 tests)
BRANCH: feat/task-7
COMMIT: df21f3d
PR: https://github.com/eugenebireta/biretos-automation/pull/9
TESTS: 321 passed, 0 failed
SUMMARY: >
  Full Phase 7 implementation: regex-only NLU for 4 intents with
  INV-MBC mandatory button confirmation, graceful degradation L0/L1/L2,
  shadow mode (manual exit), prompt injection guard, SLA tracking,
  5-minute confirmation TTL with atomic consume.
  Awaiting CRITIC/AUDITOR/JUDGE. NO auto-merge.
STATUS: PR_OPEN — awaiting external review
---
DATE: 2026-03-20
TITLE: Task 5.1 — TaskIntent + ActionSnapshot Pydantic v2 Models (CLOSEOUT)
RISK_LEVEL: CORE
SCOPE:
  - .cursor/windmill-core-v1/domain/cdm_models.py (NEW, Tier-2)
  - .cursor/windmill-core-v1/tests/test_cdm_models.py (NEW, 6 tests)
BRANCH: feat/task-5.1
COMMIT: ee54864e2e5eeafe8d502d8e48b64d19676613ae
SUMMARY:
  Added Pydantic v2 BaseModel definitions for TaskIntent and ActionSnapshot
  (domain/cdm_models.py). TaskIntent enforces trace_id min_length=1 (Fail Loud).
  ActionSnapshot enforces Literal[1] schema_version and Literal["cdek_shipment"]
  leaf_worker_type (Fail Loud). 6 deterministic unit tests, no DB, no live API.
  No Tier-1 frozen files touched. No pinned API signatures changed.
  Full suite: 124/124 PASS. Prerequisite for Task 5.2 (Validation на 3 границах).
AUDITOR_VERDICT: PASS
TEST_EVIDENCE: 6/6 PASS (test_cdm_models.py); 124/124 PASS (full suite)
NOTES:
  Bookkeeping recovered after PC migration gap (STATE.md was BUILDER/ACTIVE with
  null evidence; CAPSULE.md was empty). Closed out at seq 25. Task 5.2 SCOUT open.
---
DATE: 2026-03-13
TITLE: R2 Naming Alignment + Write-Prep (NOT MERGED)
RISK_LEVEL: LOW
SCOPE:
  - PROJECT_DNA.md
  - MASTER_PLAN_v1_8_0.md
  - EXECUTION_ROADMAP_v2_2.md
  - docs/howto/R2_EXPORT_PREP.md
  - feat/rev-r2-export branch (migrations/027, test_rev_export_logs_schema, telegram_router /export stub)
SUMMARY:
  A) DONE: DNA sync to v2.0; docs naming alignment to rev_export_logs in all 4 files.
  B) WRITE-PREP DONE, NOT MERGED: feat/rev-r2-export has migration 027, schema test, /export stub.
  C) BLOCKED: Revenue gate not open, merge R2 batch forbidden until Track A blockers closed.
  D) BLOCKERS: Tier-1 Hash (CRLF-only, infra follow-up pending); governance pytest (approve_case_with_correction); CI green not confirmed.
NOTES:
  R2 is NOT fully complete. Merge prohibited. Track A must close first.
---
DATE: 2026-03-02
TITLE: Image Tool Ban — Permanent Enforcement
RISK_LEVEL: LOW
SCOPE:
  - .cursorrules
  - .cursor/rules/risk_router.mdc
  - ai_engineering/agent_behavior_rules.txt
  - .cursor/rules/autopilot_ux.mdc
SUMMARY:
  Implemented 4-layer tool governance to permanently disable image/diagram generation tools in Cursor.
  Tools are framed as DISABLED/mocked. Self-abort logic added. Mermaid fallback enforced.
ARCH_VERDICT: APPROVE
SMOKE_TEST: PASS (Mermaid, no image tool call)
NOTES:
  MULTIMODEL_TRACE explicitly disambiguated from multimodal capabilities.
---

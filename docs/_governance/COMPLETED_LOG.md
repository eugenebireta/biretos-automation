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

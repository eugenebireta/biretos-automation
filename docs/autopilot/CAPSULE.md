# Task Capsule

Task_ID: 5.1
Risk: CORE

## Facts (SCOUT)
- Etap 5 requires Pydantic v2 models for CDM: TaskIntent and ActionSnapshot.
- dispatch_action() currently takes untyped Dict; governance_executor._execute_live()
  manually checks schema_version, leaf_worker_type, leaf_payload, external_idempotency_key.
- Task 5.1 scope: model definitions only. Per-action payload schemas are Task 5.2 scope.

## Constraints (ARCHITECT)
- Files must be Tier-2 (NOT Tier-1 frozen). No imports from Tier-1 modules.
- trace_id must enforce min_length=1 (Fail Loud per DNA §7).
- schema_version must be Literal[1]; leaf_worker_type Literal["cdek_shipment"] (Fail Loud).
- Pure models: no DB, no side-effects, no live dependencies.
- At least one deterministic test per DNA §7 mandatory patterns rule 8.

## Decisions (ARCHITECT_V2)
- domain/cdm_models.py: two Pydantic v2 BaseModel classes (TaskIntent, ActionSnapshot).
- tests/test_cdm_models.py: 6 deterministic unit tests, no DB, no live API.
- No changes to any Tier-1 frozen files (19-file list per DNA §3).
- No changes to pinned API signatures (DNA §4).

## Plan_Final (ARCHITECT/PLANNER)
- Create .cursor/windmill-core-v1/domain/cdm_models.py with TaskIntent + ActionSnapshot.
- Create .cursor/windmill-core-v1/tests/test_cdm_models.py with 6 tests.
- Prerequisite for Task 5.2 (Validation на 3 границах).

## Result (POST_AUDIT_LOGGER)
- branch: feat/task-5.1
- commit: ee54864e2e5eeafe8d502d8e48b64d19676613ae
- changed_files:
    - .cursor/windmill-core-v1/domain/cdm_models.py (+65 lines)
    - .cursor/windmill-core-v1/tests/test_cdm_models.py (+93 lines)
- test_evidence: 6/6 PASS (test_cdm_models.py), full suite 124/124 PASS
- auditor_verdict: PASS
- notes:
    - No Tier-1 frozen files touched (verified against DNA §3 list).
    - No pinned API signatures changed (DNA §4 list unaffected).
    - No prohibited imports (domain.reconciliation_* etc.) introduced.
    - No DML on reconciliation or Core business tables.
    - trace_id Fail Loud enforced at model boundary.
    - ActionSnapshot Fail Loud on wrong schema_version and wrong leaf_worker_type.
    - Capsule filed during PC-migration gap recovery (2026-03-20).

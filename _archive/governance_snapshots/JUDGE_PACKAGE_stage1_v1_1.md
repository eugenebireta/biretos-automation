# JUDGE PACKAGE вЂ” Stage 1 v1.1

## Canonical references (paths only)
- PROJECT_DNA.md
- MASTER_PLAN_v1_8_0.md
- EXECUTION_ROADMAP_v2_2.md

## PRECHECK snapshot (short)
- repo_root: C:\cursor_project\biretos-automation
- branch: master
- last_commit: 4d81d4c docs: complete Tier-3 worker system with enhanced logging, error handling, and tests.
- full snapshot artifact: docs/_governance/run_state_pre.md

## Diff bundle (Tier-1 target files)
- docs/_governance/diff_reconciliation_service.txt
- docs/_governance/diff_maintenance_sweeper.txt
- docs/_governance/diff_tier1_hashes.txt
- docs/_governance/diff_reconciliation_service.txt: HAS_DIFF
- docs/_governance/diff_maintenance_sweeper.txt: HAS_DIFF
- docs/_governance/diff_tier1_hashes.txt: EMPTY_DIFF

## Pytest summary
- status: PASS
- exit_code: 0
- output artifact: docs/_governance/pytest_output.txt

### Last ~30 pytest lines
```
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    @app.on_event("startup")

tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fail_closed
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fail_closed
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fails_when_secrets_unset
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fails_when_secrets_unset
  C:\Users\Eugene\AppData\Local\Programs\Python\Python312\Lib\site-packages\fastapi\applications.py:4547: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    return self.router.on_event(event_type)

tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fail_closed
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fails_when_secrets_unset
  C:\cursor_project\biretos-automation\.cursor\windmill-core-v1\webhook_service\main.py:263: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    @app.on_event("shutdown")

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 128 passed, 8 warnings in 0.82s =======================

PYTEST_EXIT_CODE=0
```

## Hash proof summary
- total_entries: 19
- match_count: 19
- mismatch_count: 0
- hash artifact: docs/_governance/hash_proof.txt

### MISMATCH/MISSING paths
- none

## Untracked files referenced by manifest
- artifact: docs/_governance/untracked_referenced_by_manifest.txt
- .cursor/windmill-core-v1/retention_policy.py
- .cursor/windmill-core-v1/domain/reconciliation_verify.py
- .cursor/windmill-core-v1/domain/reconciliation_alerts.py
- .cursor/windmill-core-v1/domain/structural_checks.py
- .cursor/windmill-core-v1/migrations/016_create_reconciliation_audit_log.sql
- .cursor/windmill-core-v1/migrations/017_create_reconciliation_suppressions.sql
- .cursor/windmill-core-v1/migrations/018_create_reconciliation_alerts.sql
- .cursor/windmill-core-v1/migrations/019_add_retention_indexes.sql
- .cursor/windmill-core-v1/docs/RETENTION_INVARIANT.md
- .cursor/windmill-core-v1/tests/validation/test_phase3_alert_emission.py
- .cursor/windmill-core-v1/tests/validation/test_phase3_cache_read_model_contract.py
- .cursor/windmill-core-v1/tests/validation/test_phase3_l3_structural_checks.py
- .cursor/windmill-core-v1/tests/validation/test_phase3_replay_verify.py
- .cursor/windmill-core-v1/tests/validation/test_phase3_structural_safety_contract.py

## SCOPE LOCK
### IN
- .cursor/windmill-core-v1/domain/reconciliation_service.py
- .cursor/windmill-core-v1/maintenance_sweeper.py
- .cursor/windmill-core-v1/.tier1-hashes.sha256
- .cursor/windmill-core-v1/CREDENTIALS_FOUND.md (index removal only)
- .env (index removal only)
- price-checker/.env (index removal only)
- .gitignore
- docs/_governance/*
### OUT
- .cursor/windmill-core-v1/migrations/020_create_stg_catalog_jobs.sql
- .cursor/windmill-core-v1/migrations/021_create_stg_catalog_imports.sql
- .cursor/windmill-core-v1/workers/catalog_worker.py
- .cursor/windmill-core-v1/tests/validation/test_r1_catalog_pipeline.py
- .cursor/rules/lot-structure-analysis.mdc
- scripts/lot_scoring/**
- tmp/runtime_smoke_runner_v3.py
- MASTER_PLAN_v1_8_0.md
- EXECUTION_ROADMAP_v2_2.md
- PROJECT_DNA.md
- BP-Verification-Checklist.md

## Decision request
- APPROVE / REJECT / MODIFY

## STOP-POINT 1
РќР• РєРѕРјРјРёС‚РёС‚СЊ/РќР• РїСѓС€РёС‚СЊ/РќР• РїРµСЂРµСЃС‡РёС‚С‹РІР°С‚СЊ С…СЌС€Рё РґРѕ РІРµСЂРґРёРєС‚Р° JUDGE.

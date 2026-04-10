# JUDGE_SUBMISSION_FULL_stage1_executing_only_r2

## A) Header
- timestamp_utc: 2026-02-28T20:06:11.128330+00:00
- repo_root: C:\cursor_project\biretos-automation
- branch: master
- last_commit: 4d81d4c docs: complete Tier-3 worker system with enhanced logging, error handling, and tests.

## B) Executing-only analysis
- Executing status is implemented in Tier-3 governance workflow/executor and migration 015.
- Tier-1 working tree was hard-reverted to HEAD for reconciliation_service.py and maintenance_sweeper.py.
- Therefore executing-only Tier-1 diff is expected to be empty for both files.
- No new Tier-1 functions/imports/dependencies are introduced in r2.
- No Tier-1 -> Tier-3 runtime imports are added in r2.
- Phase 2.5/3 additions (RC-4b/audit/L3/retention) were removed by HEAD revert.
- Manifest file was not recomputed in this phase, per STOP-POINT rules.

## C) Evidence blocks
### run_state_pre_r2.md
```markdown
# Run State Pre r2

- repo_root: C:\cursor_project\biretos-automation
- branch: master
- last_commit: 4d81d4c docs: complete Tier-3 worker system with enhanced logging, error handling, and tests.

## git status (full)

```text
On branch master
Your branch is ahead of 'origin/master' by 4 commits.
  (use "git push" to publish your local commits)

Changes to be committed:
  (use "git restore --staged <file>..." to unstage)
	deleted:    .cursor/windmill-core-v1/CREDENTIALS_FOUND.md
	deleted:    .env
	deleted:    price-checker/.env

Changes not staged for commit:
  (use "git add/rm <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   .cursor/windmill-core-v1/.tier1-hashes.sha256
	modified:   .cursor/windmill-core-v1/domain/reconciliation_service.py
	modified:   .cursor/windmill-core-v1/maintenance_sweeper.py
	modified:   .cursor/windmill-core-v1/migrations/015_add_review_cases_executing_status.sql
	modified:   .cursor/windmill-core-v1/pytest.ini
	modified:   .cursor/windmill-core-v1/ru_worker/dispatch_action.py
	modified:   .cursor/windmill-core-v1/ru_worker/idempotency.py
	modified:   .cursor/windmill-core-v1/tests/test_idempotency.py
	modified:   .gitignore
	modified:   BP-Verification-Checklist.md
	deleted:    EXECUTION_ROADMAP_v1.0.md
	deleted:    EXECUTION_ROADMAP_v2.0.md
	deleted:    MASTER_PLAN_v1.4.3.md
	deleted:    MASTER_PLAN_v1.7.2.md
	modified:   scripts/lot_scoring/run_full_ranking_v341.py
	modified:   scripts/lot_scoring/tests/test_explain_v4.py

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	.cursor/rules/lot-structure-analysis.mdc
	.cursor/windmill-core-v1/docs/PHASE2_BOUNDARY.md
	.cursor/windmill-core-v1/docs/RETENTION_INVARIANT.md
	.cursor/windmill-core-v1/domain/reconciliation_alerts.py
	.cursor/windmill-core-v1/domain/reconciliation_verify.py
	.cursor/windmill-core-v1/domain/structural_checks.py
	.cursor/windmill-core-v1/migrations/016_create_reconciliation_audit_log.sql
	.cursor/windmill-core-v1/migrations/017_create_reconciliation_suppressions.sql
	.cursor/windmill-core-v1/migrations/018_create_reconciliation_alerts.sql
	.cursor/windmill-core-v1/migrations/019_add_retention_indexes.sql
	.cursor/windmill-core-v1/migrations/020_create_stg_catalog_jobs.sql
	.cursor/windmill-core-v1/migrations/021_create_stg_catalog_imports.sql
	.cursor/windmill-core-v1/retention_policy.py
	.cursor/windmill-core-v1/tests/validation/test_phase3_alert_emission.py
	.cursor/windmill-core-v1/tests/validation/test_phase3_cache_read_model_contract.py
	.cursor/windmill-core-v1/tests/validation/test_phase3_l3_structural_checks.py
	.cursor/windmill-core-v1/tests/validation/test_phase3_replay_verify.py
	.cursor/windmill-core-v1/tests/validation/test_phase3_structural_safety_contract.py
	.cursor/windmill-core-v1/tests/validation/test_r1_catalog_pipeline.py
	.cursor/windmill-core-v1/workers/
	.env.example
	EXECUTION_ROADMAP_v2_2.md
	MASTER_PLAN_v1_8_0.md
	_archive/
	audits/
	data/
	docs/_governance/
	downloads/
	scripts/lot_scoring/__init__.py
	scripts/lot_scoring/audits/
	scripts/lot_scoring/capital_map.py
	scripts/lot_scoring/category_engine.py
	scripts/lot_scoring/cdm.py
	scripts/lot_scoring/cqr.py
	scripts/lot_scoring/data/
	scripts/lot_scoring/etl/
	scripts/lot_scoring/extract_lot_core.py
	scripts/lot_scoring/filters/
	scripts/lot_scoring/governance_config.py
	scripts/lot_scoring/io/
	scripts/lot_scoring/llm_auditor.py
	scripts/lot_scoring/merge_quarantine.py
	scripts/lot_scoring/pipeline/
	scripts/lot_scoring/run_batch_lot_processing.py
	scripts/lot_scoring/run_commit4_sanity_check.py
	scripts/lot_scoring/run_config.py
	scripts/lot_scoring/run_filters_pipeline.py
	scripts/lot_scoring/run_hybrid_audit.py
	scripts/lot_scoring/run_llm_classify_v2.py
	scripts/lot_scoring/run_llm_quarantine_pipeline.py
	scripts/lot_scoring/run_lot_analysis.py
	scripts/lot_scoring/run_quarantine_console.py
	scripts/lot_scoring/run_series_pipeline.py
	scripts/lot_scoring/run_stage3_automation.py
	scripts/lot_scoring/run_top50_unknown_recon.py
	scripts/lot_scoring/run_web_enriched_llm_pipeline.py
	scripts/lot_scoring/simulation/
	scripts/lot_scoring/tests/__init__.py
	scripts/lot_scoring/tests/test_abs_score.py
	scripts/lot_scoring/tests/test_brand_integration.py
	scripts/lot_scoring/tests/test_brand_intelligence.py
	scripts/lot_scoring/tests/test_brand_regression.py
	scripts/lot_scoring/tests/test_category_engine.py
	scripts/lot_scoring/tests/test_commit4_intelligence_baseline.py
	scripts/lot_scoring/tests/test_determinism_score.py
	scripts/lot_scoring/tests/test_hybrid_audit_llm_only.py
	scripts/lot_scoring/tests/test_llm_classify_v2.py
	scripts/lot_scoring/tests/test_multipliers.py
	scripts/lot_scoring/tests/test_pn_liquidity.py
	scripts/lot_scoring/tests/test_protocol_filters.py
	scripts/lot_scoring/tests/test_score10.py
	scripts/lot_scoring/tests/test_simulation.py
	scripts/lot_scoring/tests/test_stage3_automation.py
	scripts/lot_scoring/tests/test_stage4_guardrails.py
	scripts/lot_scoring/tests/test_unknown_exposure.py
	scripts/lot_scoring/tests/test_v35_value_slice.py
	scripts/lot_scoring/tools/
	scripts/lot_scoring/volume_profile.py

```

## git diff --cached --name-status

```text
D	.cursor/windmill-core-v1/CREDENTIALS_FOUND.md
D	.env
D	price-checker/.env
```

## git diff --cached --name-only

```text
.cursor/windmill-core-v1/CREDENTIALS_FOUND.md
.env
price-checker/.env
```
```

### diff_reconciliation_service_r2.txt
```diff

```

### diff_maintenance_sweeper_r2.txt
```diff

```

### diff_tier1_hashes_r2.txt
```diff

```

### pytest_output_r2.txt
- pytest_status: PASS
- PYTEST_EXIT_CODE: 0
```text
============================= test session starts =============================
platform win32 -- Python 3.12.8, pytest-9.0.2, pluggy-1.6.0 -- C:\Users\Eugene\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: C:\cursor_project\biretos-automation\.cursor\windmill-core-v1
configfile: pytest.ini
plugins: anyio-3.7.1
collecting ... collected 113 items

tests/test_governance_decisions.py::test_record_human_approve_inserts_correctly PASSED [  0%]
tests/test_governance_decisions.py::test_decision_seq_increments_with_mixed_gates PASSED [  1%]
tests/test_governance_decisions.py::test_decision_seq_increments_for_same_gate PASSED [  2%]
tests/test_governance_decisions.py::test_trace_id_none_raises PASSED     [  3%]
tests/test_governance_decisions.py::test_replay_mode_raises PASSED       [  4%]
tests/test_governance_decisions.py::test_corrections_content_in_decision_context PASSED [  5%]
tests/test_governance_decisions.py::test_override_ref_in_decision_context PASSED [  6%]
tests/test_governance_executor.py::test_executor_happy_path PASSED       [  7%]
tests/test_governance_executor.py::test_executor_replay_verified PASSED  [  7%]
tests/test_governance_executor.py::test_executor_replay_divergence_executing PASSED [  8%]
tests/test_governance_executor.py::test_executor_replay_divergence_approved PASSED [  9%]
tests/test_governance_executor.py::test_executor_replay_divergence_cancelled PASSED [ 10%]
tests/test_governance_executor.py::test_executor_claim_race_loses PASSED [ 11%]
tests/test_governance_executor.py::test_executor_resume_no_idempotency_row PASSED [ 12%]
tests/test_governance_executor.py::test_executor_resume_sweeper_failed_lock PASSED [ 13%]
tests/test_governance_executor.py::test_executor_genuine_failure_no_retry PASSED [ 14%]
tests/test_governance_executor.py::test_executor_duplicate_succeeded PASSED [ 15%]
tests/test_governance_executor.py::test_executor_duplicate_processing PASSED [ 15%]
tests/test_governance_executor.py::test_executor_leaf_failure_marks_cancelled PASSED [ 16%]
tests/test_governance_executor.py::test_executor_snapshot_validation_failure PASSED [ 17%]
tests/test_governance_executor.py::test_executor_external_key_injected PASSED [ 18%]
tests/test_governance_executor.py::test_executor_cdek_409_treated_as_success PASSED [ 19%]
tests/test_governance_executor.py::test_executor_step3b_retry_limit PASSED [ 20%]
tests/test_governance_trigger.py::test_trigger_happy_path PASSED         [ 21%]
tests/test_governance_trigger.py::test_trigger_snapshot_has_required_fields PASSED [ 22%]
tests/test_governance_trigger.py::test_trigger_external_key_is_uuid PASSED [ 23%]
tests/test_governance_trigger.py::test_trigger_unsupported_action_type PASSED [ 23%]
tests/test_governance_trigger.py::test_trigger_resolution_failure_tbank PASSED [ 24%]
tests/test_governance_trigger.py::test_trigger_resolution_failure_mapping PASSED [ 25%]
tests/test_governance_trigger.py::test_trigger_idempotent_enqueue_key_format PASSED [ 26%]
tests/test_governance_workflow.py::test_create_review_case_inserts_correctly PASSED [ 27%]
tests/test_governance_workflow.py::test_create_review_case_idempotent PASSED [ 28%]
tests/test_governance_workflow.py::test_create_review_case_idempotency_key_format PASSED [ 29%]
tests/test_governance_workflow.py::test_assign_case PASSED               [ 30%]
tests/test_governance_workflow.py::test_resolve_case PASSED              [ 30%]
tests/test_governance_workflow.py::test_case_creator_replay_skips PASSED [ 31%]
tests/test_governance_workflow.py::test_case_creator_creates_case PASSED [ 32%]
tests/test_governance_workflow.py::test_resolve_order_id_excluded PASSED [ 33%]
tests/test_governance_workflow.py::test_approve_case_from_open PASSED    [ 34%]
tests/test_governance_workflow.py::test_approve_case_from_assigned PASSED [ 35%]
tests/test_governance_workflow.py::test_approve_case_already_approved PASSED [ 36%]
tests/test_governance_workflow.py::test_claim_for_execution_success PASSED [ 37%]
tests/test_governance_workflow.py::test_claim_for_execution_not_approved PASSED [ 38%]
tests/test_governance_workflow.py::test_claim_concurrent_race PASSED     [ 38%]
tests/test_governance_workflow.py::test_mark_executed_from_executing PASSED [ 39%]
tests/test_governance_workflow.py::test_mark_executed_wrong_status PASSED [ 40%]
tests/test_governance_workflow.py::test_read_case_for_resume_executing PASSED [ 41%]
tests/test_governance_workflow.py::test_resolve_case_from_executing PASSED [ 42%]
tests/test_idempotency.py::test_t1_generate_key_ship_paid PASSED         [ 43%]
tests/test_idempotency.py::test_t2_generate_key_ship_paid_missing_invoice PASSED [ 44%]
tests/test_idempotency.py::test_t3_read_only_action_has_no_key PASSED    [ 45%]
tests/test_idempotency.py::test_t4_auto_ship_all_paid_has_no_key PASSED  [ 46%]
tests/test_idempotency.py::test_t5_tbank_payment_key_coarse_is_supported PASSED [ 46%]
tests/test_idempotency.py::test_t6_hash_stable_for_same_payload PASSED   [ 47%]
tests/test_idempotency.py::test_t7_hash_excludes_non_business_fields PASSED [ 48%]
tests/test_idempotency.py::test_t8_hash_is_sha256_shape PASSED           [ 49%]
tests/test_idempotency.py::test_t9_real_without_db_conn_raises PASSED    [ 50%]
tests/test_idempotency.py::test_t9b_idempotency_ttl_default_used_when_env_missing_or_invalid PASSED [ 51%]
tests/test_idempotency.py::test_t9c_idempotency_ttl_env_override_used PASSED [ 52%]
tests/test_idempotency.py::test_t10_acquire_new_lock PASSED              [ 53%]
tests/test_idempotency.py::test_t11_duplicate_succeeded_returns_cached_result PASSED [ 53%]
tests/test_idempotency.py::test_t12_duplicate_processing_detected PASSED [ 54%]
tests/test_idempotency.py::test_t13_stale_takeover PASSED                [ 55%]
tests/test_idempotency.py::test_t14_complete_with_correct_token PASSED   [ 56%]
tests/test_idempotency.py::test_t15_complete_with_wrong_token_rejected PASSED [ 57%]
tests/test_idempotency.py::test_t16_complete_after_sweeper_rejected PASSED [ 58%]
tests/test_idempotency.py::test_t17_sweeper_marks_expired_as_failed PASSED [ 59%]
tests/test_idempotency.py::test_t18_sweeper_is_idempotent PASSED         [ 60%]
tests/test_idempotency.py::test_t19_double_ship_paid_single_side_effect PASSED [ 61%]
tests/test_idempotency.py::test_t20_auto_ship_all_paid_fan_out PASSED    [ 61%]
tests/test_idempotency.py::test_t21_dry_run_real_actions_work_without_db PASSED [ 62%]
tests/test_idempotency.py::test_t22_dry_run_does_not_write_idempotency_rows PASSED [ 63%]
tests/validation/test_idempotency_migration_trace_id_index.py::test_action_idempotency_trace_id_index_migration_exists_and_mentions_index PASSED [ 64%]
tests/validation/test_phase25_contract_guards.py::test_observability_service_is_read_only PASSED [ 65%]
tests/validation/test_phase25_contract_guards.py::test_rc3_lock_order_for_update_before_ledger_sum PASSED [ 66%]
tests/validation/test_phase25_contract_guards.py::test_maintenance_sweeper_does_not_import_ru_worker_runtime_module PASSED [ 67%]
tests/validation/test_phase25_observability.py::test_ic1_payment_cache_integrity_pass_and_fail PASSED [ 68%]
tests/validation/test_phase25_observability.py::test_health_classifier_priority PASSED [ 69%]
tests/validation/test_phase25_reconciliation.py::test_rc1_reconcile_payment_cache_is_idempotent PASSED [ 69%]
tests/validation/test_phase25_reconciliation.py::test_rc4_allocated_line_guard_prevents_release PASSED [ 70%]
tests/validation/test_phase25_reconciliation.py::test_rc4_prevents_double_release_via_idempotency_key PASSED [ 71%]
tests/validation/test_phase25_replay_gate.py::test_replay_gate_pre_rebuild_inconsistent PASSED [ 72%]
tests/validation/test_phase25_replay_gate.py::test_replay_gate_deterministic_rebuild PASSED [ 73%]
tests/validation/test_phase25_replay_gate.py::test_replay_gate_rebuild_is_idempotent PASSED [ 74%]
tests/validation/test_phase2_contract_guards.py::test_availability_service_enforces_row_lock_and_atomic_snapshot_mutation PASSED [ 75%]
tests/validation/test_phase2_contract_guards.py::test_payment_service_keeps_insert_and_cache_recompute_in_single_service_path PASSED [ 76%]
tests/validation/test_phase2_contract_guards.py::test_shipment_cache_semantics_latest_non_cancelled PASSED [ 76%]
tests/validation/test_phase2_contract_guards.py::test_unwrap_flow_exists_in_cancel_transition PASSED [ 77%]
tests/validation/test_phase2_contract_guards.py::test_invoice_worker_uses_content_hash_document_contract_not_total_amount_key PASSED [ 78%]
tests/validation/test_phase2_contract_guards.py::test_fsm_contains_phase2_partial_states PASSED [ 79%]
tests/validation/test_phase2_document_contracts.py::test_document_generation_key_is_deterministic_for_equivalent_content PASSED [ 80%]
tests/validation/test_phase2_document_contracts.py::test_document_generation_key_changes_when_business_content_changes PASSED [ 81%]
tests/validation/test_phase2_document_contracts.py::test_reservation_chunk_keys_are_event_scoped_and_replay_safe PASSED [ 82%]
tests/validation/test_phase2_payment_service_runtime.py::test_payment_transaction_update_is_atomic_service_step_without_commit_side_effect PASSED [ 83%]
tests/validation/test_phase2_shipment_cache_runtime.py::test_recompute_order_cdek_cache_uses_latest_non_cancelled PASSED [ 84%]
tests/validation/test_phase2_unwrap_runtime.py::test_cancel_shipment_triggers_unpack_allocated_to_reserved PASSED [ 84%]
tests/validation/test_phase3_alert_emission.py::test_emit_alert_created_then_duplicate PASSED [ 85%]
tests/validation/test_phase3_alert_emission.py::test_emit_batch_alert_uses_unique_key PASSED [ 86%]
tests/validation/test_phase3_alert_emission.py::test_ack_alert_updates_state PASSED [ 87%]
tests/validation/test_phase3_cache_read_model_contract.py::test_cache_read_model_only_contract PASSED [ 88%]
tests/validation/test_phase3_cache_read_model_contract.py::test_detector_catches_synthetic_violation_strings PASSED [ 89%]
tests/validation/test_phase3_l3_structural_checks.py::test_check_stock_ledger_non_negative_pass_and_fail PASSED [ 90%]
tests/validation/test_phase3_l3_structural_checks.py::test_check_reservations_for_terminal_orders_pass_and_fail PASSED [ 91%]
tests/validation/test_phase3_replay_verify.py::test_verify_module_is_read_only_by_static_scan PASSED [ 92%]
tests/validation/test_phase3_replay_verify.py::test_verify_payment_cache_match_and_divergence PASSED [ 92%]
tests/validation/test_phase3_replay_verify.py::test_verify_shipment_cache_match_and_divergence PASSED [ 93%]
tests/validation/test_phase3_replay_verify.py::test_verify_document_key_match_and_divergence PASSED [ 94%]
tests/validation/test_phase3_replay_verify.py::test_verify_stock_snapshot_match_and_divergence PASSED [ 95%]
tests/validation/test_phase3_structural_safety_contract.py::test_structural_safety_contract_static_scan PASSED [ 96%]
tests/validation/test_phase3_structural_safety_contract.py::test_structural_safety_detector_catches_synthetic_forbidden_insert PASSED [ 97%]
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fail_closed PASSED [ 98%]
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fails_when_secrets_unset PASSED [ 99%]
tests/validation/test_tier1_stability_guards.py::test_sweeper_uses_safe_interval_parameterization PASSED [100%]

============================== warnings summary ===============================
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fail_closed
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fails_when_secrets_unset
  C:\cursor_project\biretos-automation\.cursor\windmill-core-v1\webhook_service\main.py:258: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
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
======================= 113 passed, 8 warnings in 0.77s =======================

PYTEST_EXIT_CODE=0
```

### hash_proof_r2.txt
```text
# Tier-1 Hash Proof r2
total_entries: 19
match_count: 17
mismatch_count: 2

MISMATCH | maintenance_sweeper.py | expected=f4d31b85adc195f4386c5e3ab67cd10d85977a5842db356612e2c217dec50153 | actual=a603100bcb86d0827aeb1272a87e4109229c893c5afbc80e51db17e421574807
MATCH    | retention_policy.py | cefd11faad3d0eb459511fc45c4dd36f6be65220d839510779542081e1cb5f04
MISMATCH | domain/reconciliation_service.py | expected=eb0ccddd72a25f22e84e06b2e0de5c8092dca0056318b1ba9b315b38538934b1 | actual=12d6b44a5cc331a0cf7ba0aa3b088514c7d797ed98905b42212a9022ca85f14d
MATCH    | domain/reconciliation_verify.py | c021d151efb3ecd873fbd58edf17925911bb55735ff43884f9cc7ad41b2e96b5
MATCH    | domain/reconciliation_alerts.py | 966c8a19f5c23ba1a52214c9597f6c4d2e9268223c7dd60d7411a9b50b9c1926
MATCH    | domain/structural_checks.py | 8e76de8bd1fa4919f827c24cd3c8a9c1d69975349824e8002511a0a711656e09
MATCH    | domain/observability_service.py | 3d11d417e447edeb214fd0f34f0c97fc9275bb15b518787d29c8c20215cab6fd
MATCH    | migrations/016_create_reconciliation_audit_log.sql | 390e5fcabfd66b468c680bc90af50efe8c1165a8753a019700979c3672471b83
MATCH    | migrations/017_create_reconciliation_suppressions.sql | de85fe23677c29fab8d113a6607096a64be6666b9a9b579b2444366c46dbddd6
MATCH    | migrations/018_create_reconciliation_alerts.sql | 509ab70dc86a114d3e7f7c7dc75ecffe57157ac3e6c78125d8889251cb162695
MATCH    | migrations/019_add_retention_indexes.sql | 57e285c662abfcb88024551a754a1b3418728e02c4d7d891e0d7a0f2828f34ea
MATCH    | docs/RETENTION_INVARIANT.md | 51c365994769a1be88be95c0b1be5f0f9fe286ad9415583c79dc7fd78b698ebe
MATCH    | tests/validation/test_phase3_alert_emission.py | 7c79790cf37b73288d6ea159aca626c6adfe79dcaf21ad5018d2bacad3f9c62c
MATCH    | tests/validation/test_phase3_cache_read_model_contract.py | 7caefdd44d905bff3742d1e5e6c0acc945d01cf7ff7d9024baffaeb055d1cb4b
MATCH    | tests/validation/test_phase3_l3_structural_checks.py | 9a2043f2d0148f2b0f0525236da05f614369c4a174aec03eb6bb89c695e0aeab
MATCH    | tests/validation/test_phase3_replay_verify.py | a54ae1717d34b813c52c133071d689afb75a8f6c2ce09442728c5da705f90b93
MATCH    | tests/validation/test_phase3_structural_safety_contract.py | 52cdc50831ecb19bbe56a8516d1660d54a05693396a7b0192202a3f7ee037b64
MATCH    | tests/validation/test_phase25_contract_guards.py | a2e63ed77be1f32b5b022ba85bfe6cef59bf5ffa6d6bd1d0a1bb3684db64e338
MATCH    | tests/validation/test_phase25_replay_gate.py | fc3458a75d0c55361fe81a6982b89c111bc8792dbfabb3bc05438efb70365609
```

### untracked_referenced_by_manifest_r2.txt
```text
.cursor/windmill-core-v1/retention_policy.py
.cursor/windmill-core-v1/domain/reconciliation_verify.py
.cursor/windmill-core-v1/domain/reconciliation_alerts.py
.cursor/windmill-core-v1/domain/structural_checks.py
.cursor/windmill-core-v1/migrations/016_create_reconciliation_audit_log.sql
.cursor/windmill-core-v1/migrations/017_create_reconciliation_suppressions.sql
.cursor/windmill-core-v1/migrations/018_create_reconciliation_alerts.sql
.cursor/windmill-core-v1/migrations/019_add_retention_indexes.sql
.cursor/windmill-core-v1/docs/RETENTION_INVARIANT.md
.cursor/windmill-core-v1/tests/validation/test_phase3_alert_emission.py
.cursor/windmill-core-v1/tests/validation/test_phase3_cache_read_model_contract.py
.cursor/windmill-core-v1/tests/validation/test_phase3_l3_structural_checks.py
.cursor/windmill-core-v1/tests/validation/test_phase3_replay_verify.py
.cursor/windmill-core-v1/tests/validation/test_phase3_structural_safety_contract.py
```

### manifest_head_vs_working_r2.txt
```text
HEAD_vs_working: DIFF
head_entries: 19
working_entries: 19
```

### SECURITY_GATE.md
```markdown
# SECURITY GATE (Phase P0)

Status: PENDING

- [ ] Credential rotation complete (owner)
- [x] Sensitive files removed from git index (no secret content disclosed)
- [x] Ignore patterns updated in `.gitignore`

Notes:
- No secret values are recorded in this artifact.
- Do not proceed to commit/push until owner confirms rotation.
```

## D) Index snapshot AFTER hygiene
### git diff --cached --name-status
```text
D	.cursor/windmill-core-v1/CREDENTIALS_FOUND.md
D	.env
M	.gitignore
D	price-checker/.env
```

### git diff --cached --name-only
```text
.cursor/windmill-core-v1/CREDENTIALS_FOUND.md
.env
.gitignore
price-checker/.env
```

## E) OUT/REVENUE staged check
- OUT/REVENUE staged? NO

## F) Decision request
- APPROVE / REJECT / MODIFY

## G) STOP-POINT 1
- Do NOT commit / push / gh.
- Do NOT recompute .tier1-hashes.sha256 in this phase.

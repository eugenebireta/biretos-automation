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

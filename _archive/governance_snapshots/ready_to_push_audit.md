# Ready To Push Audit

timestamp: 2026-03-01T01:36:28.050515+05:00

## git branch --show-current
`
master
`

## git log -1 --oneline
`
5363ed7 CORE-CRITICAL-APPROVED: Tier-1 manifest perimeter fix + tracking fix + security sanitize
`

## git status
`
On branch master
Your branch is ahead of 'origin/master' by 5 commits.
  (use "git push" to publish your local commits)

Changes not staged for commit:
  (use "git add/rm <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   .cursor/windmill-core-v1/migrations/015_add_review_cases_executing_status.sql
	modified:   .cursor/windmill-core-v1/pytest.ini
	modified:   .cursor/windmill-core-v1/ru_worker/dispatch_action.py
	modified:   .cursor/windmill-core-v1/ru_worker/idempotency.py
	modified:   .cursor/windmill-core-v1/tests/test_idempotency.py
	modified:   .cursorrules
	modified:   BP-Verification-Checklist.md
	deleted:    EXECUTION_ROADMAP_v1.0.md
	deleted:    EXECUTION_ROADMAP_v2.0.md
	deleted:    MASTER_PLAN_v1.4.3.md
	deleted:    MASTER_PLAN_v1.7.2.md
	modified:   docs/_governance/SECURITY_GATE.md
	modified:   scripts/lot_scoring/run_full_ranking_v341.py
	modified:   scripts/lot_scoring/tests/test_explain_v4.py

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	.cursor/rules/lot-structure-analysis.mdc
	.cursor/rules/risk_router.mdc
	.cursor/rules/roles/
	.cursor/rules/tier1_frozen.mdc
	.cursor/windmill-core-v1/docs/PHASE2_BOUNDARY.md
	.cursor/windmill-core-v1/migrations/020_create_stg_catalog_jobs.sql
	.cursor/windmill-core-v1/migrations/021_create_stg_catalog_imports.sql
	.cursor/windmill-core-v1/tests/validation/test_r1_catalog_pipeline.py
	.cursor/windmill-core-v1/workers/
	.env.example
	EXECUTION_ROADMAP_v2_2.md
	MASTER_PLAN_v1_8_0.md
	_archive/
	audits/
	data/
	docs/_governance/JUDGE_PACKAGE_stage1_v1_1.md
	docs/_governance/JUDGE_SUBMISSION_FULL_stage1_v1_1.md
	docs/_governance/diff_maintenance_sweeper.txt
	docs/_governance/diff_maintenance_sweeper_r2.txt
	docs/_governance/diff_reconciliation_service.txt
	docs/_governance/diff_reconciliation_service_r2.txt
	docs/_governance/diff_tier1_hashes.txt
	docs/_governance/diff_tier1_hashes_r2.txt
	docs/_governance/hash_proof.txt
	docs/_governance/hash_proof_r2.txt
	docs/_governance/index_snapshot_before.txt
	docs/_governance/manifest_head_vs_working_r2.txt
	docs/_governance/post_commit_verify.md
	docs/_governance/pre_push_audit.md
	docs/_governance/pytest_output.txt
	docs/_governance/pytest_output_r2.txt
	docs/_governance/run_state_pre.md
	docs/_governance/run_state_pre_r2.md
	docs/_governance/security_gate_close_audit.md
	docs/_governance/staged_files_final.txt
	docs/_governance/untracked_referenced_by_manifest.txt
	docs/_governance/untracked_referenced_by_manifest_r2.txt
	docs/howto/
	docs/promptpacks/
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

no changes added to commit (use "git add" and/or "git commit -a")
`

Security Gate COMPLETE

Next step: run separate push prompt for pre-push snapshot + push + post-push local audit.

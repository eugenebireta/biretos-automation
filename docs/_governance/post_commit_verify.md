# Post-Commit Verify

timestamp: 2026-03-01T01:27:33.600048+05:00

## git log -1 --stat
`
commit 5363ed784e8a2e147491847dff7b10c860733f61
Author: eugenebireta <eugene.bireta@gmail.com>
Date:   Sun Mar 1 01:27:13 2026 +0500

    CORE-CRITICAL-APPROVED: Tier-1 manifest perimeter fix + tracking fix + security sanitize
    
    Governance: JUDGE APPROVE r2 (docs/_governance/JUDGE_SUBMISSION_FULL_stage1_executing_only_r2.md)
    
    Changes:
    - Recomputed .cursor/windmill-core-v1/.tier1-hashes.sha256 to match HEAD file content (CI-compatible CRLF->LF hashing)
    - Added 14 manifest-referenced files to git tracking (missing tracking bug fix)
    - Removed from tracking: .cursor/windmill-core-v1/CREDENTIALS_FOUND.md, .env, price-checker/.env
    - Kept security ignore patterns in .gitignore
    
    No Tier-1 logic changes; reconciliation_service.py and maintenance_sweeper.py remain at HEAD (empty diffs).
    
    PUSH BLOCKED until credential rotation confirmed in docs/_governance/SECURITY_GATE.md.
    
    Made-with: Cursor

 .cursor/windmill-core-v1/.tier1-hashes.sha256      |   4 +-
 .cursor/windmill-core-v1/CREDENTIALS_FOUND.md      | 211 ----------
 .../windmill-core-v1/docs/RETENTION_INVARIANT.md   |  75 ++++
 .../domain/reconciliation_alerts.py                |  99 +++++
 .../domain/reconciliation_verify.py                | 291 ++++++++++++++
 .../windmill-core-v1/domain/structural_checks.py   | 106 +++++
 .../016_create_reconciliation_audit_log.sql        |  27 ++
 .../017_create_reconciliation_suppressions.sql     |  24 ++
 .../018_create_reconciliation_alerts.sql           |  22 ++
 .../migrations/019_add_retention_indexes.sql       |  16 +
 .cursor/windmill-core-v1/retention_policy.py       | 171 ++++++++
 .../tests/validation/test_phase3_alert_emission.py | 142 +++++++
 .../test_phase3_cache_read_model_contract.py       | 219 +++++++++++
 .../validation/test_phase3_l3_structural_checks.py |  89 +++++
 .../tests/validation/test_phase3_replay_verify.py  | 274 +++++++++++++
 .../test_phase3_structural_safety_contract.py      | 189 +++++++++
 .env                                               |  51 ---
 .gitignore                                         |  36 +-
 ...DGE_SUBMISSION_FULL_stage1_executing_only_r2.md | 433 +++++++++++++++++++++
 docs/_governance/SECURITY_GATE.md                  |  11 +
 docs/_governance/hash_proof_post_approve.txt       |  24 ++
 docs/_governance/post_approve_run.md               | 149 +++++++
 docs/_governance/pytest_output_post_approve.txt    |  69 ++++
 price-checker/.env                                 |  35 --
 24 files changed, 2467 insertions(+), 300 deletions(-)
`

## git diff HEAD~1 --stat
`
 .cursor/windmill-core-v1/.tier1-hashes.sha256      |   4 +-
 .cursor/windmill-core-v1/CREDENTIALS_FOUND.md      | 211 -----
 .../windmill-core-v1/docs/RETENTION_INVARIANT.md   |  75 ++
 .../domain/reconciliation_alerts.py                |  99 +++
 .../domain/reconciliation_verify.py                | 291 +++++++
 .../windmill-core-v1/domain/structural_checks.py   | 106 +++
 .../016_create_reconciliation_audit_log.sql        |  27 +
 .../017_create_reconciliation_suppressions.sql     |  24 +
 .../018_create_reconciliation_alerts.sql           |  22 +
 .../migrations/019_add_retention_indexes.sql       |  16 +
 .cursor/windmill-core-v1/retention_policy.py       | 171 ++++
 .../tests/validation/test_phase3_alert_emission.py | 142 ++++
 .../test_phase3_cache_read_model_contract.py       | 219 ++++++
 .../validation/test_phase3_l3_structural_checks.py |  89 +++
 .../tests/validation/test_phase3_replay_verify.py  | 274 +++++++
 .../test_phase3_structural_safety_contract.py      | 189 +++++
 .cursorrules                                       |  11 +
 .env                                               |  51 --
 .gitignore                                         |  36 +-
 EXECUTION_ROADMAP_v1.0.md                          | 360 ---------
 EXECUTION_ROADMAP_v2.0.md                          | 566 -------------
 MASTER_PLAN_v1.4.3.md                              | 874 ---------------------
 MASTER_PLAN_v1.7.2.md                              | 653 ---------------
 ...DGE_SUBMISSION_FULL_stage1_executing_only_r2.md | 433 ++++++++++
 docs/_governance/SECURITY_GATE.md                  |  11 +
 docs/_governance/hash_proof_post_approve.txt       |  24 +
 docs/_governance/post_approve_run.md               | 149 ++++
 docs/_governance/pytest_output_post_approve.txt    |  69 ++
 price-checker/.env                                 |  35 -
 scripts/lot_scoring/run_full_ranking_v341.py       | 210 +++--
 scripts/lot_scoring/tests/test_explain_v4.py       |  48 ++
 31 files changed, 2679 insertions(+), 2810 deletions(-)

warning: in the working copy of '.cursor/windmill-core-v1/ru_worker/dispatch_action.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of '.cursor/windmill-core-v1/ru_worker/idempotency.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of '.cursor/windmill-core-v1/tests/test_idempotency.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of '.cursorrules', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'scripts/lot_scoring/run_full_ranking_v341.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'scripts/lot_scoring/tests/test_explain_v4.py', LF will be replaced by CRLF the next time Git touches it
`

## git ls-files | findstr /i CREDENTIALS_FOUND.md
exit_code: 1
`

`

## git ls-files | findstr /i .env
exit_code: 0
`
.cursor/windmill-core-v1/.env
.cursor/windmill-core-v1/env.example
_scratchpad/.env.shopware
_scratchpad/Read-EnvKeys.ps1
_scratchpad/env_keys_report.txt
_scratchpad/env_shopware.txt
_tools/python312.DEPRECATED/Lib/site-packages/invoke/env.py
_tools/python312.DEPRECATED/Lib/site-packages/pip/_internal/build_env.py
_tools/python312.DEPRECATED/Lib/site-packages/pip/_internal/metadata/importlib/_envs.py
_tools/python312.DEPRECATED/Lib/site-packages/pip/_internal/utils/virtualenv.py
_tools/python312.DEPRECATED/Lib/site-packages/pip/_vendor/urllib3/contrib/_appengine_environ.py
auto-heal/autoheal.env.template
brand-catalog-automation/.env
brand-catalog-automation/.env.backup
brand-catalog-automation/.env.backup.20251117_093736
brand-catalog-automation/.env.backup.diag
brand-catalog-automation/.env.backup.google
brand-catalog-automation/.env.clean
brand-catalog-automation/.env.fixed
brand-catalog-automation/diagnostics/list_tbank_env.py
brand-catalog-automation/diagnostics/tbank_env_keys.txt
control-panel/config.env.template
deploy/deploy.env.template
docker-compose.env.template
infrastructure/config/env_config.json
insales_to_shopware_migration/.env
manual-launch/config.env.template
marketplace-category-updater/updater.env.template
net_diag_chatgpt/.env.example
perplexity/.env
perplexity/.env.example
price-checker/.env.template
product-optimization/optimizer.env.template
tbank-webhook-gateway/config/gateway.env.template
tmp_tbank_env_info.txt
`

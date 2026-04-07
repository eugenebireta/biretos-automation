# Task Capsule

Task_ID: R1-revenue-price-evidence-integrator
Risk: SEMI
Date: 2026-04-07
Branch: feat/rev-r1-catalog
PR: https://github.com/eugenebireta/biretos-automation/pull/38
Status: COMPLETED — committed, pushed to feat/rev-r1-catalog

## What was built

`price_evidence_integrator.py` closes the gap between `price_manual_scout.py` output
(manifests) and the canonical evidence bundles read by `local_catalog_refresh.py`.

Key components:
- `scripts/price_evidence_integrator.py` — reads price manifest JSONL, applies
  `price_admissibility.materialize_price_admissibility()` per row; for rows classified
  `offer_admissibility_status == "admissible_public_price"` writes the price section
  into `evidence_<pn>.json`, sets `field_statuses_v2["price_status"] = "ACCEPTED"` and
  `policy_decision_v2["price_status"] = "ACCEPTED"`, records integration trace in
  `refresh_trace["price_integration"]`. Does NOT touch `card_status`.
- `tests/enrichment/test_price_evidence_integrator.py` — 32 deterministic tests covering
  build_price_section, evidence_path lookup, success, skips, dry_run, idempotency.

DNA compliance:
- trace_id generated per run (pi_<ts>_<hex>), injectable _now_fn for deterministic tests
- idempotent: overwriting price section + trace with same trace_id is safe
- error_class/severity/retriable on all error paths
- no Core DML, no domain.reconciliation_* imports
- explicit field allowlist (_PRICE_FIELD_MAP) to prevent schema drift

## Real integration result

Run against `downloads/scout_cache/price_manual_manifest.jsonl` (20 rows):
- 5 rows classified `admissible_public_price` → integrated
- 15 rows skipped (offer_status != admissible_public_price)
- Evidence bundles updated: 027913.10 (EUR 467→44365 RUB), 1000106 (AED 68.25→1638 RUB),
  1006186 (TWD 1794, rub_price=None — FX gap), 1003012, 1030000000

Post-integration `local_catalog_refresh.py` result:
- review_required=15 (up from 9), draft_only=10, auto_publish=0, promote_canonical=false

Post-integration `build_catalog_followup_queues.py`:
- price_followup_count=14, photo_recovery_count=14

## Governance

SEMI risk. Two-round audit via auditor_system API (Gemini 3.1 Pro CRITIC + Opus 4.6 JUDGE).
Result: **BATCH_APPROVAL** (quality gate passed).
Post-audit fixes: sys.path.insert moved to module level; trace_id timestamp sourced from now_fn().

## Coverage

798/798 tests PASS (zero regression). 32/32 integrator tests PASS.

## Previous Capsule (M4 Executor Bridge — seq 60)

M4 Executor Bridge closes the automation loop for the Meta Orchestrator.
When `auto_execute: true` in config.yaml, `python orchestrator/main.py` now
runs end-to-end: intake → classify → advisor → synthesizer → directive → claude --print → collect_packet.
New: `orchestrator/executor_bridge.py` (run()+run_with_collect()), 43 tests.
SEMI BATCH_APPROVAL. 308/308 orchestrator tests PASS.

## Next

Revenue R1 track: photo pipeline recovery (14 SKU) or next price scout batch (14 SKU).

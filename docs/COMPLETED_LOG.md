# Completed Tasks Log

Format: Date | Task ID | Risk | Summary

---

2026-03-01 | Task 1.1 | CORE | governance_execute_approved (Early Return in dispatch_action, full FSM/idem in governance_executor)
2026-03-02 | Task 1.2 | CORE | Corrections apply: added governance_resolver for HUMAN_APPROVE/HUMAN_REJECT/HUMAN_APPROVE_WITH_CORRECTION with governance_resolve job wiring and tests
2026-03-02 | Task 1.3 | CORE | External idempotency keys: switched governance_trigger external_idempotency_key from random UUID to deterministic key and updated deterministic test
2026-03-02 | Task 1.4 | CORE | Split TX (executing state) verified as already implemented (claim->commit, resume path, mark_executed->commit), no code changes required
2026-03-02 | Task 1.5 | CORE | Replay verify-only validated: _verify_replay is read-only (SELECT-only), returns replay_verified/replay_divergence, and replay branches are covered by tests
2026-03-02 | Task 1.6 | CORE | Smoke test S6 added: real-DB governance loop (create review_case -> resolve with correction -> execute), C9/C10 critical checks integrated into runtime smoke report
2026-03-02 | Task 2.1 | SEMI | GitHub Actions pytest on push already configured in `.github/workflows/ci.yml`; closed via Scout-Validator no-code closeout
2026-03-02 | Task 2.2 | SEMI | Branch protection on `master` confirmed by user as configured and verified via checklist sections B/D (manual GitHub UI task)
2026-03-02 | Task 2.3 | SEMI | Governance executor tests already included in CI via existing `pytest` run in `.github/workflows/ci.yml`; closed via Scout-Validator no-code closeout
2026-03-02 | Task 3.1 | CORE | RC-2 (CDEK shipment) already implemented in reconciliation_service + maintenance_sweeper routing; closed via Scout-Validator no-code closeout
2026-03-02 | Task 3.2 | CORE | RC-5 (Document) already implemented via reconcile_document_key + IC-5 routing in maintenance_sweeper; closed via Scout-Validator no-code closeout
2026-03-02 | Task 3.3 | CORE | RC-6 (Order lifecycle) already implemented via resolve_pending_payment + IC-9 stale pending payment routing in maintenance_sweeper; closed via Scout-Validator no-code closeout
2026-03-02 | Task 3.4 | CORE | RC-7 (End-to-end transaction) already implemented via sync_shipment_status + IC-7 stale FSM routing in maintenance_sweeper; closed via Scout-Validator no-code closeout
2026-03-02 | Task 3.5 | CORE | Path B complete: added explicit RC-6/RC-7 entrypoint tests in new validation files; CI includes them via existing pytest workflow without frozen-file edits
2026-03-02 | Task 4.1 | SEMI | Implemented Tier-3 Telegram alerting for IC/RC violations via alert_notifier + migration 022 + config wiring + deterministic tests; reserve-before-send dedupe with delete-on-failure retry semantics validated (5/5 tests passed)
2026-03-02 | Task 4.2 | SEMI | No-code closeout: existing alert_notifier pipeline already covers IC-7 (FSM staleness) and IC-8 (zombie reservations) alerts via IC* FAIL/STALE filter, global/order verdict collection, and Telegram delivery path
2026-03-03 | Task 4.3 | SEMI | No-code closeout via POST_AUDIT_LOGGER: severity-based alert routing already implemented (critical/warning/default chat resolution, min severity threshold, emoji formatting) with deterministic test coverage
2026-03-03 | Task 4.4 | SEMI | NO-CODE CLOSEOUT: separate Telegram alert chat already supported via existing config keys (`ALERT_TELEGRAM_CHAT_ID`, `ALERT_CHAT_ID_CRITICAL`, `ALERT_CHAT_ID_WARNING`); no code changes required. Infra setup remains outside-of-code (create group, add bot, fetch chat_id, set env, restart notifier).
2026-03-03 | Task 5.1 | CORE | Implemented CDM v2 runtime contracts: added Pydantic models under `domain/cdm`, moved FSM conversion into Tier-3 `ru_worker/cdm_adapters.py`, integrated mapper/worker validation boundaries, and added deterministic `tests/test_cdm_models.py` coverage
2026-03-13 | R2-docs | LOW | PROJECT_DNA.md synced to authoritative DNA v2.0; R2 naming alignment: PROJECT_DNA, MASTER_PLAN_v1_8_0, EXECUTION_ROADMAP_v2_2, docs/howto/R2_EXPORT_PREP — all use rev_export_logs
2026-03-13 | R2-prep | LOW | R2 write-prep DONE on feat/rev-r2-export: migration 027, schema test, /export stub (Coming soon). NOT MERGED — merge blocked until Revenue gate open

2026-04-02 | 8.1 | SEMI | Wire NLU intent parser to execute_telegram_update — approved via auditor_system (run_9b2fc417617f)
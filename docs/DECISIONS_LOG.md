# Architectural Decisions Log

Format: Date | Task ID | Task Name

---

## 2026-03-01 | Task 1.1 | governance_execute_approved
**Decision:** Early Return in dispatch_action.py for governance_execute_approved
**Why:** governance_executor already has its own idempotency and FSM, so duplicating outer idem-lock and CSG checks adds unnecessary complexity
**Alternatives rejected:**
- Flag approach (verify_only) -- pollutes dispatch_action signature
- Separate dispatcher function -- unnecessary abstraction for a single action_type

## 2026-03-02 | Task 1.2 | corrections_apply_resolver
**Decision:** Introduce dedicated `governance_resolver.py` orchestration job instead of embedding correction flow into existing executor/case creator handlers
**Why:** keep separation of concerns (decision recording, review_case mutation, execute enqueue), preserve transaction ownership in `ru_worker`, and enforce deterministic enqueue idempotency key (`gov_exec_enqueue:{case_id}`)
**Alternatives rejected:**
- Extend `governance_case_creator.py` to also resolve cases -- mixes creation and resolution responsibilities
- Trigger execution directly from `governance_executor.py` for correction flow -- bypasses explicit human-decision application boundary

## 2026-03-02 | Task 1.3 | external_idempotency_keys
**Decision:** Use deterministic `external_idempotency_key` in `governance_trigger` instead of random UUID
**Why:** provider idempotency requires stable request identity across retries; random UUID breaks duplicate suppression and can trigger repeated external side-effects
**Alternatives rejected:**
- Keep random UUID and rely only on local idempotency -- does not protect external provider from duplicate calls
- Generate key later in executor -- too late to preserve immutable snapshot contract from trigger

## 2026-03-02 | Task 1.4 | split_tx_executing_state
**Decision:** Accept no-code closeout; keep existing Split TX implementation as canonical
**Why:** architecture already satisfies requirements (TX1 claim+commit, crash-safe resume from `executing`, TX2 complete+mark+commit) with dedicated tests validating transaction boundaries
**Alternatives rejected:**
- Refactor executor flow for stylistic changes -- introduces unnecessary risk without functional gain
- Add redundant transaction wrappers -- duplicates existing guarantees and increases complexity

## 2026-03-02 | Task 1.5 | replay_verify_only
**Decision:** Accept no-code closeout; keep existing REPLAY verify-only path in `governance_executor` as canonical
**Why:** current `_verify_replay` implementation is SELECT-only, avoids writes/external side-effects, and test coverage validates `replay_verified` plus key divergence reasons
**Alternatives rejected:**
- Add extra replay mutation flags in executor -- would violate verify-only boundary
- Move replay verification to separate worker -- unnecessary complexity for already isolated branch

## 2026-03-02 | Task 1.6 | smoke_test_s6_real_db
**Decision:** Keep smoke test integration real-DB and stub only the external CDEK API call inside S6
**Why:** smoke scope must validate real SQL/transaction paths end-to-end while avoiding nondeterministic network side-effects; this preserves integration confidence for governance lifecycle states and idempotency log checks
**Alternatives rejected:**
- Mock-only unit scenario for S6 -- misses DB integration regressions and SQL contract issues
- Full live external call in smoke -- brittle and environment-dependent for CI

## 2026-03-02 | Task 2.1 | ci_pytest_on_push
**Decision:** Accept no-code closeout for CI pytest-on-push requirement
**Why:** `.github/workflows/ci.yml` already contains `push` trigger for `master` and an explicit `Run tests` step executing `pytest`, so implementation is already in place
**Alternatives rejected:**
- Rebuild workflow from scratch -- redundant and risky without functional gain
- Add duplicate pytest job -- increases CI time without adding coverage

## 2026-03-02 | Task 2.2 | branch_protection_master
**Decision:** Accept manual closeout based on user-confirmed completion of checklist-driven GitHub settings and verification tests
**Why:** branch protection is a repository UI policy (not code artifact in repo); closure depends on owner/admin execution of checklist B/D and confirmation
**Alternatives rejected:**
- Try to encode branch protection in runtime code -- not applicable to GitHub repository policy layer
- Keep task open until automated API audit is added -- unnecessary blocker for current roadmap sequence

## 2026-03-02 | Task 2.3 | governance_executor_tests_in_ci
**Decision:** Accept no-code closeout for governance executor tests in CI
**Why:** current CI workflow already executes repository test suite via `pytest` in `.cursor/windmill-core-v1`, which includes governance executor/resolver/workflow tests
**Alternatives rejected:**
- Add dedicated duplicate CI job for governance tests -- increases runtime without functional gain
- Introduce selective pytest filtering now -- unnecessary complexity for current task scope

## 2026-03-02 | Task 3.1 | rc2_cdek_shipment
**Decision:** Accept no-code closeout for RC-2 (CDEK shipment reconciliation)
**Why:** required RC-2 artifacts already exist: `reconcile_shipment_cache` implemented in reconciliation service and invoked from maintenance sweeper on `IC-2` FAIL path, which satisfies roadmap intent without additional runtime changes
**Alternatives rejected:**
- Re-implement RC-2 flow in new modules -- duplicates existing behavior and adds regression risk
- Add extra wrappers around existing RC-2 call chain -- increases complexity without functional gain

## 2026-03-02 | Task 3.2 | rc5_document_reconciliation
**Decision:** Accept no-code closeout for RC-5 (Document reconciliation)
**Why:** RC-5 path is already implemented and wired end-to-end: `reconcile_document_key` exists in reconciliation service, `IC-5` consistency check exists in observability, and maintenance sweeper routes `IC-5=FAIL` into `phase25_rc5_reconcile_document_key`
**Alternatives rejected:**
- Rebuild RC-5 as a new dedicated worker path -- duplicates established reconciliation flow
- Add additional mutation layers around existing RC-5 function -- increases complexity without adding guarantees

## 2026-03-02 | Task 3.3 | rc6_order_lifecycle_reconciliation
**Decision:** Accept no-code closeout for RC-6 (Order lifecycle reconciliation)
**Why:** RC-6 chain is already implemented: stale pending transaction detector `IC-9` exists in observability, sweeper routes `IC-9=STALE` into `phase25_rc6_resolve_pending_payment`, and reconciliation service resolves provider status then re-syncs order payment cache
**Alternatives rejected:**
- Rebuild RC-6 in separate lifecycle worker -- duplicates existing maintenance loop behavior
- Add extra reconciliation indirection around `resolve_pending_payment` -- adds complexity without stronger guarantees

## 2026-03-02 | Task 3.4 | rc7_end_to_end_transaction_reconciliation
**Decision:** Accept no-code closeout for RC-7 (End-to-end transaction reconciliation)
**Why:** RC-7 flow is already in place: `IC-7` stale FSM detection exists in observability, sweeper routes `IC-7=STALE` into `phase25_rc7_sync_shipment_status`, and reconciliation updates shipment status atomically via `update_shipment_status_atomic`
**Alternatives rejected:**
- Build a second RC-7 orchestration path outside sweeper -- duplicates existing control loop
- Wrap `sync_shipment_status` with additional abstraction now -- raises complexity without extra safety value

## 2026-03-02 | Task 3.5 | rc_entrypoint_tests_in_ci_path_b
**Decision:** Execute Path B and add explicit RC-6/RC-7 entrypoint tests as new validation files
**Why:** external JUDGE approved only the route that avoids edits to all Tier-1 frozen files (including `test_phase25_replay_gate.py`) while strengthening DoD evidence for \"All RC in CI\" through explicit tests
**Alternatives rejected:**
- No-code closeout based only on broad pytest inclusion -- leaves strict DoD interpretation ambiguous
- Editing frozen validation files to extend coverage -- boundary violation against authoritative 19-file freeze list

## 2026-03-02 | Task 4.1 | icrc_telegram_alerting_tier3
**Decision:** Implement alert delivery as dedicated Tier-3 `alert_notifier` with reserve-before-send deduplication in `alert_telegram_log`
**Why:** keeps Tier-1 frozen boundary intact, guarantees idempotent cooldown suppression via `cooldown_key`, and provides reliable retry by deleting reservation on send failure
**Alternatives rejected:**
- Emitting alerts directly from frozen sweeper/reconciliation modules -- violates frozen boundary
- Keeping failed reservations in place -- blocks immediate retry within same cooldown bucket

## 2026-03-02 | Task 4.2 | fsm_staleness_zombie_alerting
**Decision:** Accept no-code closeout for Task 4.2 based on existing Task 4.1 implementation coverage
**Why:** current `alert_notifier` already consumes `collect_order_invariant_verdicts` (includes IC-7), `check_zombie_reservations` (IC-8), and routes IC/RC `FAIL|STALE` verdicts to Telegram with dedupe/retry semantics
**Alternatives rejected:**
- Add duplicate specialized notifier path for IC-7/IC-8 -- duplicates existing alert flow without added guarantees
- Introduce narrow filter for only IC-7/IC-8 -- reduces flexibility and risks regressing broader IC/RC alerting

## 2026-03-03 | Task 4.4 | separate_alert_chat_for_alerts
**Decision:** Close Task 4.4 as no-code closeout; rely on existing alert routing configuration keys.
**Why:** runtime already supports separate/default severity routes via `ALERT_TELEGRAM_CHAT_ID`, `ALERT_CHAT_ID_CRITICAL`, and `ALERT_CHAT_ID_WARNING`; required work is infrastructure configuration outside repository code.
**Alternatives rejected:**
- Implement redundant runtime changes for chat routing -- unnecessary, function already exists
- Add migration/runtime side-effects for infra-only setup -- violates minimal-change governance

## 2026-03-03 | Task 5.1 | cdm_v2_pydantic_boundary_contracts
**Decision:** Enforce CDM v2 through Tier-2 Pydantic boundary models in `domain/cdm`, while keeping FSM conversion adapters strictly in Tier-3 (`ru_worker/cdm_adapters.py`).
**Why:** preserves boundary discipline (Tier-2 must not import Tier-3), eliminates dual type-truth drift, and keeps frozen FSM contracts unchanged while adding runtime validation at ingestion/hydration boundaries.
**Alternatives rejected:**
- Add `.to_fsm_event()` / `.to_ledger_record()` methods inside Tier-2 models importing `ru_worker` -- violates layer boundaries and increases cyclic import risk
- Introduce a second canonical state enum in CDM -- risks divergence from `domain/fsm_guards.STATES`

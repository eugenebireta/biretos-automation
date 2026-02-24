# Definition of Done — Biretos Automation

Checklist for the PR author before requesting review.
Automated boundary checks (C1-C15) are performed separately by the AI Reviewer.

## Author Checklist

- [ ] **1. Core untouched.** I did not modify any Tier-1 frozen file or Tier-2 pinned signature. (If unsure, check `.cursor/windmill-core-v1/docs/PHASE2_BOUNDARY.md`.)
- [ ] **2. trace_id wired.** My worker/handler extracts `trace_id` from the payload and passes it to every domain call.
- [ ] **3. Idempotency key present.** Every external API call (Shopware, CDEK, TBank, Telegram) uses a deterministic `idempotency_key`.
- [ ] **4. Mutations via domain atomics.** I did not write raw INSERT/UPDATE/DELETE against business or reconciliation tables. All state changes go through Tier-2 domain functions.
- [ ] **5. Commit at boundary.** `conn.commit()` is called in the worker/handler, not inside `domain/` code.
- [ ] **6. Logs are clean.** No secrets, PII, or raw unredacted payloads in logging statements.
- [ ] **7. Migrations safe.** If I added a migration in `020+`, it does not reference `reconciliation_*` tables. (Exception: `-- CORE-CRITICAL-APPROVED:` marker with documented reason.)
- [ ] **8. Tests pass.** `pytest` green locally. No new test failures.
- [ ] **9. CI green.** Full pipeline passes after push.
- [ ] **10. Executability.** Any new or substantially changed Tier-3 worker/module is runnable and verifiable in isolation (entry point or test with stubbed DB/API; no full Core required).
- [ ] **11. Verifiability.** Any new or substantially changed Tier-3 worker/module has at least one deterministic test (unit or with stubbed DB/API) covering its key logic; no reliance on live external APIs, unmocked time, or randomness.
- [ ] **12. Explainability.** Any new or substantially changed Tier-3 worker/module emits structured log entries at the decision/action boundary: trace_id, key input identifiers/state, and outcome or decision taken (no full payload dumps, no PII).
- [ ] **13. Observability.** Any new or substantially changed Tier-3 worker/module logs every failure in a structured way: trace_id, error_class (TRANSIENT/PERMANENT/POLICY_VIOLATION), severity (WARNING/ERROR), retriable (true/false). No silent failure — exceptions must not be swallowed without logging.

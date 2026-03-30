# IDEA-20260324-004 — Synthetic Bot E2E / Integration Validation Layer

> **Status:** DRAFT
> **INBOX entry:** `docs/IDEA_INBOX.md` → IDEA-20260324-004
> **Risk class:** SEMI
> **Created:** 2026-03-25

---

## 1. Problem / Context

The AI Executive Assistant (Этап 7) and Task Engine (Этап 6) are currently tested via:
- Unit tests (pytest, 321 tests passing as of PR #9).
- Manual end-to-end testing via real Telegram messages.

Manual E2E testing has critical gaps:
- **Not repeatable:** Real Telegram messages require a live session, cannot be scripted.
- **Not deterministic:** Real webhooks arrive with real timing; race conditions are untestable.
- **No regression baseline:** There is no transcript snapshot to compare current behavior
  against a known-good session.
- **Callback flows cannot be simulated in CI:** TBank payment callbacks, CDEK tracking
  updates, and similar inbound webhooks require a running external service.
- **Shadow Mode (Этап 8.3) needs a data source:** Shadow Mode requires ≥50 requests to exit.
  Without synthetic input, this gate is slow to clear in development.

The Synthetic Bot E2E layer is a **validation and testing infrastructure** that:
- Produces synthetic inbound events (messages, callbacks, webhooks) without real external services.
- Captures transcript snapshots for regression comparison.
- Enables smoke tests and shadow mode runs in local development and CI.
- Runs on Local PC as analysis/review layer with **zero side-effects on Core**.

This is **NOT** an autoclikker or UI automation tool. It does not simulate human interactions
in Telegram's UI. It sends structured payloads directly to the application's inbound handlers.

---

## 2. Why Now

- Этап 7 (AI Executive Assistant NLU) is nearing completion. The absence of E2E test
  infrastructure means NLU regressions will only be caught by manual testing.
- Этап 8 (Stability Gate, §8.3) requires Shadow Mode with ≥50 requests and ≥90% match rate.
  Synthetic input is the cleanest way to generate controlled volume for this gate.
- TD-031 (Local Debug & Regression Lab, Review: Этап 8.1) is the existing anchor for this
  kind of capability. This proposal gives TD-031 concrete scope.
- PR #9 is in external review. This is the right window to define test infrastructure
  before the next implementation sprint begins.

---

## 3. Relation to Master Plan / Roadmap / DNA

### Direct connections

| Element | Connection |
|---------|-----------|
| **TD-031** — Local Debug & Regression Lab → Review: Этап 8.1 | This proposal is the detailed scope for TD-031 |
| **Этап 8.3** — Shadow Mode → выход при ≥50 запросов, ≥90% совпадение | Synthetic layer is the mechanism to generate controlled shadow input |
| **Этап 8.4** — Owner Cognitive Load tracking | Transcript snapshots provide indirect evidence of session complexity |
| **Этап 7** — AI Executive Assistant NLU | Primary system under test |
| **Этап 6** — Task Engine | Secondary system under test (TaskIntent execution) |
| **COGNITIVE LAYER (Local PC, NO side-effects)** | Synthetic layer runs here; no production mutations |
| **SHADOW LOGGING 8.1.6** — задел teacher-student pipeline | Synthetic transcripts feed this pipeline as controlled training/evaluation data |
| **IDEA-20260324-002** — Max Executive Layer | Future: synthetic layer adapts to Max channel when Telegram is replaced |

### What this does NOT touch

- Core tables (order_ledger, shipments, payment_transactions, etc.) — Synthetic layer
  does NOT write to these. If synthetic input triggers a business action, that action
  is either mocked or recorded as a dry-run artifact.
- Frozen Files (DNA §3) — not in scope.
- Pinned API (DNA §4) — not in scope.
- Production Telegram webhooks — synthetic layer intercepts at the application handler level,
  not at the Telegram API level.
- Master Plan and Roadmap — **not modified** at DRAFT stage.

---

## 4. Goals

1. Enable **synthetic message injection** into the NLU pipeline without a live Telegram session.
2. Enable **webhook simulation** for TBank callbacks, CDEK tracking updates, and similar
   inbound events — without requiring live external services.
3. Enable **callback simulation** for Telegram inline button confirmations (INV-MBC flows).
4. Produce **transcript snapshots**: structured records of input → intent → action → response
   for regression comparison.
5. Support **shadow mode runs** on demand: replay a snapshot set and compare outcomes.
6. Provide **smoke tests** that can run in CI without network calls to external services.

---

## 5. Non-Goals

- Do NOT build a UI automation tool or screenscraper (not an autoclikker).
- Do NOT simulate production load or performance test.
- Do NOT write to Core business tables from the synthetic layer.
- Do NOT replace existing unit tests (pytest) — this is an additional E2E layer.
- Do NOT require a running Telegram instance for CI execution.
- Do NOT build a full test harness for IDEA-002 (Max Executive Layer) yet —
  focus on current Telegram-based Этап 7/8 stack. Max is a future extension point.
- Do NOT generate synthetic financial transactions that affect real ledger state.

---

## 6. Core Thesis

**Synthetic layer = controlled input + captured output + comparison.**

```
Architecture:

  SyntheticDriver
    │
    ├─ MessageInjector       → sends synthetic Update payloads to TelegramRouter handler
    │   payload: {message_id, chat_id, text, from_user}
    │
    ├─ WebhookSimulator      → sends synthetic webhook payloads to webhook handlers
    │   payload: TBank callback, CDEK status update
    │
    ├─ CallbackSimulator     → sends synthetic Telegram callback_query
    │   (simulates button press for INV-MBC confirmation flows)
    │
    ├─ TranscriptCapture     → records input→intent→action→response per session
    │   output: transcript_snapshot.json / .md
    │
    └─ ShadowRunner          → replays a transcript set, compares outcomes
        input: reference_transcript.json
        output: match_rate (%), diff of divergent responses

Side-effects policy:
  - All Core mutations in synthetic runs → intercepted at service boundary → DRY_RUN mode
  - No real payments, no real shipments, no real Telegram messages sent out
  - Local PC analysis layer only

CI integration:
  - Smoke tests: fixed set of synthetic messages → expected intents → pytest assertions
  - Shadow tests: replay snapshot → compare to reference (no hard fail, soft alert on divergence)
```

---

## 7. Consumers

| Consumer | What they use |
|----------|--------------|
| **CI (GitHub Actions)** | Smoke tests: synthetic messages → intent assertions, no external calls |
| **Developer (local)** | Shadow runner: replay session snapshots to detect NLU regressions |
| **Этап 8 Shadow Mode gate** | Synthetic input provides controlled volume to reach ≥50 requests |
| **SHADOW LOGGING 8.1.6** | Synthetic transcripts as seed data for teacher-student pipeline |
| **Future Max adapter** | Same SyntheticDriver with Max channel adapter instead of Telegram |

---

## 8. Data Sources

| Source | What it provides |
|--------|-----------------|
| Existing Telegram sessions (captured manually) | Seed data for initial transcript snapshots |
| MASTER_PLAN intent taxonomy (Этап 6/7) | Ground truth for intent classification in assertions |
| TBank/CDEK webhook schema (existing adapters) | Schema for webhook simulation payloads |
| Owner-defined scenario scripts | Hand-crafted synthetic scenarios for edge case coverage |

---

## 9. Constraints

1. **Zero side-effects on Core.** Synthetic runs must operate in DRY_RUN mode.
   Any service call that would mutate Core (order creation, payment, shipment update)
   must be intercepted and stubbed. This is non-negotiable.
2. **No real Telegram API calls in synthetic mode.** MessageInjector calls the application
   handler directly (bypassing Telegram Bot API). No messages are sent to real users.
3. **No real payment processor calls in synthetic mode.** WebhookSimulator sends
   payload directly to the webhook handler; TBank is never contacted.
4. **Transcript snapshot format must be deterministic.** Timestamps and random IDs must
   be controlled (fixed seed or mocked) for reproducible comparisons.
5. **Runs on Local PC.** Synthetic layer is not a cloud service. No external hosting required.
6. **Does not replace manual testing.** Owner validation via real Telegram remains required
   before Этап 8 Stability Gate closes.

---

## 10. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Synthetic tests pass but real Telegram behavior diverges | Medium | High | Keep real manual smoke test as final gate; synthetic = pre-gate, not replacement |
| DRY_RUN mode not correctly isolated — synthetic run mutates Core | Low | Critical | DRY_RUN flag enforced at service boundary layer; never at handler level |
| Transcript snapshot format becomes stale as NLU evolves | Medium | Medium | Snapshot versioning; accept divergence ≤10% before requiring snapshot refresh |
| Scope creep: "add performance tests, add load tests, add chaos tests" | High | Medium | Explicit non-goals; extensions only through IDEA_INBOX |
| Shadow Mode gate (8.3) achieves ≥50 synthetic requests but bypasses real usage signal | Low | Medium | Shadow Mode requires real usage for *exit* — synthetic only supplements early-stage runs |

---

## 11. Promotion Options

### Option A (recommended) — Expand TD-031 with this proposal as the scope

1. Update TD-031 description in MASTER_PLAN to reference this proposal.
2. Activate TD-031 as part of Этап 8.1 preparation (before Shadow Mode begins).
3. Implementation: LOW/SEMI risk — no Core changes, pure test infra.

### Option B — New TD entry

Create TD-050: Synthetic Bot E2E Validation Layer. Deferred review: Этап 8.1.
More explicit than expanding TD-031, at the cost of adding a new TD entry.

### Option C — Minimal inline addition

Add `tests/synthetic/` directory with MessageInjector and one smoke test scenario
as part of PR #9 post-merge cleanup. No formal TD entry — treat as test infrastructure
maintenance (LOW risk).

---

## 12. Open Questions

1. **DRY_RUN enforcement point:** Where exactly is the DRY_RUN intercept — at the domain
   service layer, at the database layer, or at both? Which existing hook points can be reused?
2. **Snapshot storage:** In-repo under `tests/fixtures/`? Or local-only (not committed)?
   Trade-off: committed = reproducible CI, but snapshots can grow large and contain
   semi-private business intent data.
3. **Shadow Mode integration:** Does Этап 8.3 shadow mode require the *same* infrastructure
   as synthetic E2E, or are they separate? Can ShadowRunner replace the current shadow
   logging mechanism, or does it complement it?
4. **Max future-proofing:** How much channel abstraction does the SyntheticDriver need now
   so that adding a Max adapter later is not a rewrite?
5. **Callback simulation fidelity:** Telegram callback_query includes a hash that is
   validated server-side. How is this handled in synthetic mode — bypass validation,
   or mock the validation step?

---

## What a Critic Should Check

- Is the DRY_RUN isolation model sufficient to prevent any Core side-effects,
  or are there mutation paths that bypass the proposed interception point?
- Is this proposal correctly scoped as test infrastructure, or does it risk becoming
  a shadow production system?
- Is Option C (inline addition) actually sufficient, making a formal TD unnecessary?
- Does the Shadow Mode gate (Этап 8.3) require this infrastructure, or is manual testing
  sufficient to reach ≥50 requests in a real Stability Gate period?
- Is snapshot versioning a real engineering problem at this scale, or is it over-engineered?

---

## Current Recommendation

**Status: DRAFT. Highest-readiness of the four proposals for early implementation.**
TD-031 already reserves this capability in the plan. DRY_RUN isolation is the critical
design decision to resolve before implementation begins. Option A (TD-031 expansion)
is the cleanest path.

---

## Review Log

| Date | Reviewer | Status change | Notes |
|------|----------|---------------|-------|
| 2026-03-25 | Claude Code (SCOUT) | INBOX → DRAFT | Proposal created per owner request. No code. |

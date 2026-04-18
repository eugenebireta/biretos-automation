# Core DML Refactor Backlog

**Status:** Open
**Created:** 2026-04-18
**Source:** AI-Audit `2026-04-18_pr-blocker-iron-fence-m3b.md` — Variant A amended.
**Owner:** Core track
**Trigger rule:** `.github/workflows/ci.yml` M3b (Iron Fence) — `order_ledger` in CORE_BIZ_TABLES regex.

## Purpose

Track the 8 pre-existing Tier-3 raw DML violations against `order_ledger` so that:
1. Each whitelist entry in `ci.yml` references a ticket ID from this backlog.
2. The debt ledger is visible, sortable, shrinkable — not permanent amnesty.
3. When a PR touches a whitelisted line, the referenced ticket is the contract for what refactor must happen.

**Policy:** append-only-shrinking. Closed tickets are removed from whitelist. New whitelist entries require a corresponding ticket here. Ticket created/closed only by owner governance batch.

## Refactor direction (all tickets)

Replace raw `INSERT/UPDATE/DELETE order_ledger` in Tier-3 code with a ports/adapters boundary:

- `domain/order_ledger/ports.py` — abstract `OrderLedgerWriter` interface with typed methods (`append_error_log`, `apply_state_transition`, `create_invoice_row`, etc.)
- `domain/order_ledger/pg_adapter.py` — PG implementation with proper idempotency, atomicity, and observability hooks
- Tier-3 workers inject the port and call typed methods; raw SQL disappears from Tier-3

This lets M3b enforce zero raw DML on Tier-3 without grandfathering after refactor is complete.

---

## CORE-DML-01 — ru_worker.py FSM persistence

**File:** `.cursor/windmill-core-v1/ru_worker/ru_worker.py`
**Violations:** 4 × `UPDATE order_ledger`
**Lines:** 983, 1016, 1790, 1821
**Status:** OPEN

| Line | Operation | Purpose |
|------|-----------|---------|
| 983 | `UPDATE order_ledger SET error_log = error_log || ... WHERE order_id = %s` | FSM error logging (append to error_log jsonb) |
| 1016 | `UPDATE order_ledger SET state = %s, state_history = ... WHERE order_id = %s RETURNING *` | FSM state transition |
| 1790 | `UPDATE order_ledger` | FSM persistence (details TBD — refactor will classify) |
| 1821 | `UPDATE order_ledger` | FSM persistence (details TBD — refactor will classify) |

**Note:** lines 1790/1821 were not in the initial AI-Audit listing (audit saw only 2); discovered during whitelist implementation via grep on actual tree. Refactor should cover all 4.

**Refactor target:**
- Port method: `OrderLedgerWriter.append_error_log(order_id, error_entry, trace_id)`
- Port method: `OrderLedgerWriter.apply_fsm_transition(order_id, to_state, history_entry, metadata_patch, trace_id) -> OrderLedgerRow`
- Additional port methods for 1790/1821 to be defined when refactor classifies their purpose.

**Coupled work:** FSM transition logic itself stays in ru_worker; only persistence moves behind the port.

---

## CORE-DML-02 — cdek_shipment_worker.py

**File:** `.cursor/windmill-core-v1/side_effects/cdek_shipment_worker.py`
**Violations:** 1 × `UPDATE order_ledger`
**Lines:** 231
**Status:** OPEN

| Line | Operation | Purpose |
|------|-----------|---------|
| 231 | `UPDATE order_ledger` | CDEK shipment status sync |

**Refactor target:** `OrderLedgerWriter.update_shipment_fields(order_id, cdek_fields)` — typed subset write.

---

## CORE-DML-03 — insales_paid_worker.py

**File:** `.cursor/windmill-core-v1/side_effects/insales_paid_worker.py`
**Violations:** 1 × `UPDATE order_ledger`
**Lines:** 136
**Status:** OPEN

| Line | Operation | Purpose |
|------|-----------|---------|
| 136 | `UPDATE order_ledger` | `metadata.insales_paid_synced = true` marker |

**Refactor target:** `OrderLedgerWriter.mark_insales_paid_synced(order_id, trace_id)` — single-purpose typed method.

---

## CORE-DML-04 — invoice_worker.py

**File:** `.cursor/windmill-core-v1/side_effects/invoice_worker.py`
**Violations:** 1 × `INSERT` + 2 × `UPDATE` on `order_ledger`
**Lines:** 132, 207, 290
**Status:** OPEN

| Line | Operation | Purpose |
|------|-----------|---------|
| 132 | `INSERT INTO order_ledger (...) ON CONFLICT (insales_order_id) DO UPDATE SET ...` | Invoice creation / upsert from InSales order |
| 207 | `UPDATE order_ledger` | Invoice link + status update |
| 290 | `UPDATE order_ledger` | Invoice payment status update |

**Refactor target:**
- `OrderLedgerWriter.upsert_from_insales_order(insales_order_id, fields, trace_id) -> OrderLedgerRow`
- `OrderLedgerWriter.attach_invoice(order_id, invoice_id, invoice_status)`
- `OrderLedgerWriter.update_payment_status(order_id, status, trace_id)`

**Risk:** this file has the most violations (3) AND contains the only `INSERT` (new row creation). Highest-stakes refactor in the backlog — atomic correctness of invoice/payment state is critical. Recommend prioritizing.

---

## CORE-DML-06 — pii_redactor.py

**File:** `.cursor/windmill-core-v1/ru_worker/pii_redactor.py`
**Violations:** 2 × DML on Core business tables (1 × `order_ledger`, 1 × `shipments`)
**Lines:** 172, 196
**Status:** OPEN

| Line | Operation | Purpose |
|------|-----------|---------|
| 172 | `UPDATE order_ledger` | PII scrubbing in order_ledger rows |
| 196 | `UPDATE shipments` | PII scrubbing in shipments rows |

**Note:** this ticket was not in the initial backlog (AI-Audit missed it); discovered during whitelist implementation via grep on actual tree. PII redaction is a cross-cutting concern and likely deserves its own domain service rather than being inlined in the worker.

**Refactor target:**
- Domain service: `domain/pii/redactor.py` with methods `redact_order_pii(order_id)`, `redact_shipment_pii(shipment_id)` that call the appropriate ports.
- `OrderLedgerWriter.redact_pii_fields(order_id, field_subset)` and `ShipmentsWriter.redact_pii_fields(shipment_id, field_subset)` (shipments writer port does not exist yet — part of this ticket).

**Risk:** PII redaction is a compliance surface. Refactor must preserve idempotency and audit logging (who/when/what was redacted). Treat with same care as CORE-DML-04.

---

## CORE-DML-05 — telegram_command_worker.py

**File:** `.cursor/windmill-core-v1/side_effects/telegram_command_worker.py`
**Violations:** 1 × `UPDATE order_ledger`
**Lines:** 531
**Status:** OPEN

| Line | Operation | Purpose |
|------|-----------|---------|
| 531 | `UPDATE order_ledger` | Manual state override via Telegram admin command |

**Refactor target:** `OrderLedgerWriter.apply_manual_override(order_id, new_state, admin_user, reason, trace_id)` — typed method with mandatory audit fields.

**Note:** manual override path deserves extra scrutiny — it's the intentional bypass of FSM, so the port method must log the override distinctly.

---

## Execution order recommendation

1. **CORE-DML-04 first** — highest risk, owns new-row creation, affects invoice/payment integrity
2. **CORE-DML-01** — FSM logic, central to worker state machine
3. **CORE-DML-06** — PII/compliance surface, needs audit trail preservation
4. **CORE-DML-02, 03, 05** — peripheral, can go in any order after 01 + 04 + 06

After each ticket closes, remove corresponding entries from `ci.yml` whitelist and verify M3b check passes locally before merging the refactor PR.

## Whitelist reference format (for ci.yml)

When the owner adds the whitelist to `ci.yml` per audit REVISE recommendation, each entry should cite this document:

```yaml
# M3b whitelist — pre-existing violations tracked in docs/_governance/CORE_DML_REFACTOR_BACKLOG.md
# Append-only-shrinking policy: entries removed as tickets close, never grown without governance review.
M3B_WHITELIST:
  - file: .cursor/windmill-core-v1/ru_worker/ru_worker.py
    lines: [983, 1016, 1790, 1821]
    ticket: CORE-DML-01
  - file: .cursor/windmill-core-v1/side_effects/cdek_shipment_worker.py
    lines: [231]
    ticket: CORE-DML-02
  - file: .cursor/windmill-core-v1/side_effects/insales_paid_worker.py
    lines: [136]
    ticket: CORE-DML-03
  - file: .cursor/windmill-core-v1/side_effects/invoice_worker.py
    lines: [132, 207, 290]
    ticket: CORE-DML-04
  - file: .cursor/windmill-core-v1/side_effects/telegram_command_worker.py
    lines: [531]
    ticket: CORE-DML-05
  - file: .cursor/windmill-core-v1/ru_worker/pii_redactor.py
    lines: [172, 196]
    ticket: CORE-DML-06
```

Actual CI implementation (grep + line-exclusion) is owner's governance-batch decision.

## Relation to PROJECT_DNA

PROJECT_DNA §5 forbids Tier-3 raw DML on Core business tables. This backlog does NOT weaken that rule — it tracks the debt of bringing existing code into compliance. When all 5 tickets close, the rule enforces cleanly without whitelist exceptions.

If owner ever decides that ports/adapters is the wrong abstraction, the backlog becomes the trigger for a PROJECT_DNA §5 revision discussion — not a hidden bypass.

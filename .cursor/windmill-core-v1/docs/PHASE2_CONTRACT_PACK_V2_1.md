# Phase 2 / Sprint 0+ Contract Pack v2.1

This repository implements Phase 2 architecture under **Contract Pack v2.1** as the governing spec.

## Scope

- Financial Core (payment transactions + invoice documents).
- Logistics Core (1:N shipments + legacy cache compatibility).
- Sprint 0+ Availability / Reservation (atomic stock mutation contract).

## Non-Negotiable Rules

1. Atomic availability mutation: `FOR UPDATE` + stock ledger append + snapshot update in one transaction.
2. Reservation chunk idempotency key: `reservation:{order_id}:{line_item_id}:{fulfillment_event_id}`.
3. Invoice generation key by content hash: `invoice:{order_id}:{content_hash}`.
4. Legacy `order_ledger.cdek_uuid` is cache only (`latest non-cancelled` CDEK shipment).
5. PaymentTransaction insert and `order_ledger.payment_status` cache update happen in one transaction.
6. Shipment cancellation from pre-handover states triggers deterministic unpack flow with traceable result.

## Backward Compatibility

- Existing `order_ledger` columns remain intact.
- New tables are additive (`shipments`, `payment_transactions`, `documents`, `availability_snapshot`, `stock_ledger_entries`, `reservations`, `order_line_items`).
- Existing queue-driven worker orchestration remains active.


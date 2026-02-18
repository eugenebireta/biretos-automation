# Strategy Router

One-page routing index to keep architecture decisions consistent across tasks.

## Core Rule

When touching any feature, preserve:

- deterministic + replay-safe + idempotent core,
- `trace_id` propagation,
- Core vs Adapters boundary,
- correction loop for low-confidence AI outputs (`< 0.9`).

## Governing Spec (Phase 2 / Sprint 0+)

The governing architecture spec for Financial + Logistics Core and Availability/Reservation is:

- **Contract Pack v2.1 (approved)**.

Mandatory implementation constraints from v2.1:

- Availability mutations MUST be atomic (`FOR UPDATE` + stock ledger append + snapshot update in one transaction).
- Reservation idempotency MUST be chunk-based (`reservation:{order_id}:{line_item_id}:{fulfillment_event_id}`).
- Invoice generation key MUST be content-hash based (`invoice:{order_id}:{content_hash}`), not amount-based.
- `order_ledger.cdek_uuid` MUST be treated as legacy cache (`latest non-cancelled` shipment only).
- Payment transaction insert + `order_ledger.payment_status` update MUST be in one transaction.
- Shipment cancellation MUST trigger deterministic unpack flow with traceable `unpack_result`.

## If Working on Marketplaces (Ozon/WB)

Must include:

- `CanonicalProduct` as source of truth,
- `MarketplaceProductMapping` for marketplace-specific state,
- predicted vs approved payload distinction,
- correction path via `CorrectionRecord` for category/attribute fixes,
- moderation errors captured for replay and analysis.

Do not:

- bypass canonical entities with ad-hoc marketplace payloads,
- couple marketplace logic to UCI adapters.

## If Working on Logistics

Must include:

- `CanonicalShipment` lifecycle with status history,
- package snapshot with `line_item_id` linkage,
- order-to-shipment linkage (`order_id`),
- address raw + normalized structure with provenance.

Do not:

- overwrite historical package/address snapshots.

## If Working on Payments

Must include:

- canonical order status + payment status transitions,
- `status_changed_at` and `payment_status_changed_at`,
- payment references in order documents/metadata,
- traceable relation to ledger/events.

Do not:

- mutate historical totals without explicit correction event trail.

## If Working on UCI (Telegram now, Max later)

Must include:

- adapter-only changes in UCI layer,
- unchanged core domain model and business workflows,
- stable command/event contract into core services.

Do not:

- embed channel-specific fields into canonical entities.

## If Working on RFQ / Ingestion / Scoring

Must include:

- canonical normalization before downstream automation,
- traceable client scoring A/B/C decisions,
- replay-safe processing boundaries and idempotent event handling.

Do not:

- allow non-canonical shortcuts directly into shipment/payment logic.

## If Working on AI Enhancements (classification, photos, enrichment)

Must include:

- classifier/model version trace in outputs,
- confidence gating (`< 0.9` -> approve/correct),
- correction capture in `CorrectionRecord`.

Do not:

- treat retrieval-only context as learning; learning requires persisted corrections.

## If Working on Debug Pipelines / CI Auto-Check

Must include:

- checks for idempotency, replay safety, and schema contract drift,
- clear diagnostics for broken adapter/core boundaries,
- verification that critical snapshots remain immutable.

Do not:

- merge changes that reduce observability of state transitions.

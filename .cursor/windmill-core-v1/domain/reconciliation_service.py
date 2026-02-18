from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from domain.availability_service import _ensure_snapshot_row
from domain.ports import InvoiceStatusRequest, ShipmentTrackingStatusRequest
from domain.payment_service import _derive_payment_status, _extract_order_total_minor
from domain.shipment_service import recompute_order_cdek_cache_atomic, update_shipment_status_atomic


def _ensure_tx_connection(db_conn) -> None:
    if getattr(db_conn, "autocommit", False):
        raise RuntimeError("ReconciliationService requires autocommit=False")


def reconcile_payment_cache(
    db_conn,
    *,
    order_id: UUID,
    trace_id: Optional[str],
) -> Dict[str, Any]:
    _ensure_tx_connection(db_conn)
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT order_id, payment_status, metadata, order_total_minor
            FROM order_ledger
            WHERE order_id = %s
            LIMIT 1
            FOR UPDATE
            """,
            (str(order_id),),
        )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError(f"order not found: {order_id}")
        order_row = {"order_id": row[0], "metadata": row[2], "order_total_minor": row[3]}
        prev_status = str(row[1] or "unpaid")

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount_minor), 0)
            FROM payment_transactions
            WHERE order_id = %s
              AND status = 'confirmed'
              AND transaction_type = 'charge'
            """,
            (str(order_id),),
        )
        charges_minor = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount_minor), 0)
            FROM payment_transactions
            WHERE order_id = %s
              AND status = 'confirmed'
              AND transaction_type IN ('refund', 'chargeback')
            """,
            (str(order_id),),
        )
        refunds_minor = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM payment_transactions
                WHERE order_id = %s
                  AND status = 'pending'
                  AND transaction_type = 'refund'
            )
            """,
            (str(order_id),),
        )
        has_pending_refund = bool(cursor.fetchone()[0])

        order_total_minor = _extract_order_total_minor(order_row)
        net_paid_minor = charges_minor - refunds_minor
        next_status = _derive_payment_status(net_paid_minor, order_total_minor, has_pending_refund)

        cursor.execute(
            """
            UPDATE order_ledger
            SET payment_status = %s,
                payment_status_changed_at = NOW(),
                updated_at = NOW(),
                trace_id = COALESCE(trace_id, %s::uuid)
            WHERE order_id = %s
            """,
            (next_status, trace_id, str(order_id)),
        )

        return {
            "action": "updated" if prev_status != next_status else "noop",
            "order_id": str(order_id),
            "previous_payment_status": prev_status,
            "payment_status": next_status,
            "trace_id": trace_id,
        }
    finally:
        cursor.close()


def reconcile_shipment_cache(
    db_conn,
    *,
    order_id: UUID,
    trace_id: Optional[str],
) -> Dict[str, Any]:
    _ensure_tx_connection(db_conn)
    latest_cdek_uuid = recompute_order_cdek_cache_atomic(db_conn, order_id=order_id)
    return {
        "action": "updated",
        "order_id": str(order_id),
        "cdek_uuid": latest_cdek_uuid,
        "trace_id": trace_id,
    }


def rebuild_stock_snapshot(
    db_conn,
    *,
    product_id: UUID,
    warehouse_code: str,
    trace_id: Optional[str],
) -> Dict[str, Any]:
    _ensure_tx_connection(db_conn)
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT quantity_on_hand, quantity_reserved, quantity_available
            FROM availability_snapshot
            WHERE product_id = %s
              AND warehouse_code = %s
            LIMIT 1
            FOR UPDATE
            """,
            (str(product_id), warehouse_code),
        )
        snapshot_row = cursor.fetchone()
        if not snapshot_row:
            return {
                "action": "missing_snapshot",
                "product_id": str(product_id),
                "warehouse_code": warehouse_code,
                "trace_id": trace_id,
            }

        cursor.execute(
            """
            SELECT COALESCE(SUM(quantity_delta), 0)
            FROM stock_ledger_entries
            WHERE product_id = %s
              AND warehouse_code = %s
              AND change_type IN ('receipt', 'return', 'adjustment', 'sale')
            """,
            (str(product_id), warehouse_code),
        )
        expected_on_hand = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT COALESCE(SUM(quantity), 0)
            FROM reservations
            WHERE product_id = %s
              AND warehouse_code = %s
              AND status = 'active'
            """,
            (str(product_id), warehouse_code),
        )
        expected_reserved = int(cursor.fetchone()[0])
        expected_available = expected_on_hand - expected_reserved

        cursor.execute(
            """
            UPDATE availability_snapshot
            SET quantity_on_hand = %s,
                quantity_reserved = %s,
                quantity_available = %s,
                snapshot_at = NOW(),
                updated_at = NOW()
            WHERE product_id = %s
              AND warehouse_code = %s
            """,
            (
                expected_on_hand,
                expected_reserved,
                expected_available,
                str(product_id),
                warehouse_code,
            ),
        )
        return {
            "action": "rebuilt",
            "product_id": str(product_id),
            "warehouse_code": warehouse_code,
            "quantity_on_hand": expected_on_hand,
            "quantity_reserved": expected_reserved,
            "quantity_available": expected_available,
            "trace_id": trace_id,
        }
    finally:
        cursor.close()


def reconcile_document_key(
    db_conn,
    *,
    order_id: UUID,
    trace_id: Optional[str],
) -> Dict[str, Any]:
    _ensure_tx_connection(db_conn)
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT generation_key, revision
            FROM documents
            WHERE order_id = %s
              AND document_type = 'invoice'
              AND status = 'issued'
            ORDER BY revision DESC
            LIMIT 1
            """,
            (str(order_id),),
        )
        doc_row = cursor.fetchone()
        if not doc_row:
            return {
                "action": "noop",
                "reason": "no_issued_invoice",
                "order_id": str(order_id),
                "trace_id": trace_id,
            }
        generation_key = str(doc_row[0])
        revision = int(doc_row[1])

        cursor.execute(
            """
            SELECT invoice_request_key, revision
            FROM order_ledger
            WHERE order_id = %s
            LIMIT 1
            FOR UPDATE
            """,
            (str(order_id),),
        )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError(f"order not found: {order_id}")
        prev_key = row[0]
        prev_revision = int(row[1]) if row[1] is not None else None

        cursor.execute(
            """
            UPDATE order_ledger
            SET invoice_request_key = %s,
                revision = %s,
                updated_at = NOW(),
                trace_id = COALESCE(trace_id, %s::uuid)
            WHERE order_id = %s
            """,
            (generation_key, revision, trace_id, str(order_id)),
        )
        return {
            "action": "updated" if prev_key != generation_key or prev_revision != revision else "noop",
            "order_id": str(order_id),
            "previous_invoice_request_key": prev_key,
            "invoice_request_key": generation_key,
            "previous_revision": prev_revision,
            "revision": revision,
            "trace_id": trace_id,
        }
    finally:
        cursor.close()


def _expire_one_reservation_atomic(
    db_conn,
    *,
    reservation_id: UUID,
    trace_id: Optional[str],
    now_ts: datetime,
) -> Dict[str, Any]:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, order_id, line_item_id, product_id, sku_snapshot, warehouse_code, quantity, status, expires_at
            FROM reservations
            WHERE id = %s
            LIMIT 1
            FOR UPDATE
            """,
            (str(reservation_id),),
        )
        row = cursor.fetchone()
        if not row:
            return {"action": "missing", "reservation_id": str(reservation_id), "trace_id": trace_id}

        order_id = UUID(str(row[1]))
        line_item_id = UUID(str(row[2]))
        product_id = UUID(str(row[3]))
        sku_snapshot = str(row[4])
        warehouse_code = str(row[5])
        quantity = int(row[6])
        status = str(row[7])
        expires_at = row[8]

        if status != "active":
            return {"action": "noop", "reason": "not_active", "reservation_id": str(reservation_id), "trace_id": trace_id}
        if expires_at is None or expires_at >= now_ts:
            return {"action": "noop", "reason": "not_expired", "reservation_id": str(reservation_id), "trace_id": trace_id}

        cursor.execute(
            """
            SELECT line_status
            FROM order_line_items
            WHERE id = %s
              AND order_id = %s
            LIMIT 1
            FOR UPDATE
            """,
            (str(line_item_id), str(order_id)),
        )
        line_row = cursor.fetchone()
        line_status = str(line_row[0]) if line_row else "pending"
        if line_status in {"allocated", "shipped", "delivered", "completed"}:
            return {
                "action": "skipped",
                "reason": "line_status_guard",
                "reservation_id": str(reservation_id),
                "line_status": line_status,
                "trace_id": trace_id,
            }

        cursor.execute(
            """
            UPDATE reservations
            SET status = 'expired',
                released_at = NOW(),
                updated_at = NOW(),
                trace_id = COALESCE(trace_id, %s::uuid)
            WHERE id = %s
            """,
            (trace_id, str(reservation_id)),
        )

        release_idempotency_key = f"reservation_expiry:{reservation_id}"
        cursor.execute(
            """
            INSERT INTO stock_ledger_entries (
                product_id, sku, warehouse_code, change_type, quantity_delta,
                reference_type, reference_id, trace_id, idempotency_key, metadata
            )
            VALUES (%s, %s, %s, 'release', %s, 'reservation', %s, %s::uuid, %s, %s::jsonb)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (
                str(product_id),
                sku_snapshot,
                warehouse_code,
                quantity,
                str(reservation_id),
                trace_id,
                release_idempotency_key,
                json.dumps(
                    {
                        "source": "phase25_rc4",
                        "reservation_id": str(reservation_id),
                        "reason": "reservation_expired",
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        inserted_ledger = cursor.fetchone()

        if inserted_ledger:
            _ensure_snapshot_row(db_conn, product_id, warehouse_code, sku_snapshot)
            cursor.execute(
                """
                SELECT quantity_on_hand, quantity_reserved, quantity_available
                FROM availability_snapshot
                WHERE product_id = %s
                  AND warehouse_code = %s
                LIMIT 1
                FOR UPDATE
                """,
                (str(product_id), warehouse_code),
            )
            snapshot_row = cursor.fetchone()
            if not snapshot_row:
                raise RuntimeError(
                    f"availability_snapshot missing for product={product_id}, warehouse={warehouse_code}"
                )
            next_reserved = max(0, int(snapshot_row[1]) - quantity)
            next_available = int(snapshot_row[2]) + quantity
            cursor.execute(
                """
                UPDATE availability_snapshot
                SET quantity_reserved = %s,
                    quantity_available = %s,
                    snapshot_at = NOW(),
                    updated_at = NOW()
                WHERE product_id = %s
                  AND warehouse_code = %s
                """,
                (next_reserved, next_available, str(product_id), warehouse_code),
            )

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM reservations
            WHERE order_id = %s
              AND line_item_id = %s
              AND status = 'active'
            """,
            (str(order_id), str(line_item_id)),
        )
        remaining_active = int(cursor.fetchone()[0])
        if remaining_active == 0 and line_status not in {"shipped", "delivered", "completed"}:
            cursor.execute(
                """
                UPDATE order_line_items
                SET line_status = 'pending',
                    updated_at = NOW()
                WHERE id = %s
                  AND order_id = %s
                """,
                (str(line_item_id), str(order_id)),
            )

        return {
            "action": "expired" if inserted_ledger else "duplicate_release",
            "reservation_id": str(reservation_id),
            "line_item_id": str(line_item_id),
            "order_id": str(order_id),
            "quantity_released": quantity if inserted_ledger else 0,
            "trace_id": trace_id,
        }
    finally:
        cursor.close()


def expire_reservations(
    db_conn,
    *,
    trace_id: Optional[str],
    batch_limit: int = 100,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    _ensure_tx_connection(db_conn)
    now_ts = now or datetime.now(timezone.utc)
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id
            FROM reservations
            WHERE status = 'active'
              AND expires_at IS NOT NULL
              AND expires_at < %s
            ORDER BY expires_at ASC
            LIMIT %s
            """,
            (now_ts, batch_limit),
        )
        reservation_ids = [UUID(str(row[0])) for row in cursor.fetchall()]
    finally:
        cursor.close()

    results = []
    for reservation_id in reservation_ids:
        try:
            result = _expire_one_reservation_atomic(
                db_conn,
                reservation_id=reservation_id,
                trace_id=trace_id,
                now_ts=now_ts,
            )
            if hasattr(db_conn, "commit"):
                db_conn.commit()
            results.append(result)
        except Exception as exc:
            if hasattr(db_conn, "rollback"):
                db_conn.rollback()
            results.append(
                {
                    "action": "error",
                    "reservation_id": str(reservation_id),
                    "error": str(exc),
                    "trace_id": trace_id,
                }
            )

    released = sum(1 for r in results if r.get("action") == "expired")
    skipped = sum(1 for r in results if r.get("action") in {"skipped", "noop"})
    duplicates = sum(1 for r in results if r.get("action") == "duplicate_release")
    errors = sum(1 for r in results if r.get("action") == "error")
    return {
        "trace_id": trace_id,
        "scanned": len(reservation_ids),
        "released": released,
        "skipped": skipped,
        "duplicates": duplicates,
        "errors": errors,
        "results": results,
    }


def _map_payment_provider_status(provider_status: str) -> Optional[str]:
    status = provider_status.strip().lower()
    if not status:
        return None
    if any(token in status for token in ("paid", "confirmed", "success", "succeeded")):
        return "confirmed"
    if any(token in status for token in ("fail", "failed", "cancel", "reject", "expired", "error")):
        return "failed"
    return None


def resolve_pending_payment(
    db_conn,
    *,
    payment_transaction_id: UUID,
    adapter,
    trace_id: Optional[str],
) -> Dict[str, Any]:
    _ensure_tx_connection(db_conn)
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, order_id, status, provider_code, provider_transaction_id
            FROM payment_transactions
            WHERE id = %s
            LIMIT 1
            FOR UPDATE
            """,
            (str(payment_transaction_id),),
        )
        row = cursor.fetchone()
        if not row:
            return {
                "action": "UNKNOWN",
                "reason": "payment_transaction_not_found",
                "payment_transaction_id": str(payment_transaction_id),
                "trace_id": trace_id,
            }

        order_id = UUID(str(row[1]))
        current_status = str(row[2] or "")
        provider_code = str(row[3] or "")
        provider_transaction_id = str(row[4] or "")

        if current_status != "pending":
            return {
                "action": "noop",
                "reason": "not_pending",
                "payment_transaction_id": str(payment_transaction_id),
                "order_id": str(order_id),
                "status": current_status,
                "trace_id": trace_id,
            }

        try:
            provider_result = adapter.get_invoice_status(
                InvoiceStatusRequest(
                    provider_document_id=provider_transaction_id,
                    trace_id=trace_id,
                )
            )
        except Exception as exc:
            return {
                "action": "UNKNOWN",
                "reason": "adapter_error",
                "payment_transaction_id": str(payment_transaction_id),
                "order_id": str(order_id),
                "provider_code": provider_code,
                "error": str(exc),
                "trace_id": trace_id,
            }

        provider_status = str(getattr(provider_result, "provider_status", "") or "")
        next_status = _map_payment_provider_status(provider_status)
        if not next_status:
            return {
                "action": "UNKNOWN",
                "reason": "unsupported_provider_status",
                "payment_transaction_id": str(payment_transaction_id),
                "order_id": str(order_id),
                "provider_status": provider_status,
                "trace_id": trace_id,
            }

        cursor.execute(
            """
            UPDATE payment_transactions
            SET status = %s,
                status_changed_at = NOW(),
                raw_provider_response = %s::jsonb,
                updated_at = NOW(),
                trace_id = COALESCE(trace_id, %s::uuid)
            WHERE id = %s
              AND status = 'pending'
            """,
            (
                next_status,
                json.dumps(getattr(provider_result, "raw_response", {}) or {}, ensure_ascii=False),
                trace_id,
                str(payment_transaction_id),
            ),
        )

        cache_result = reconcile_payment_cache(
            db_conn,
            order_id=order_id,
            trace_id=trace_id,
        )
        return {
            "action": "updated",
            "payment_transaction_id": str(payment_transaction_id),
            "order_id": str(order_id),
            "provider_status": provider_status,
            "transaction_status": next_status,
            "cache_result": cache_result,
            "trace_id": trace_id,
        }
    finally:
        cursor.close()


def _map_shipment_carrier_status(carrier_status: str) -> Optional[str]:
    status = carrier_status.strip().lower()
    if not status:
        return None
    mapping = {
        "created": "created",
        "new": "created",
        "accepted": "created",
        "label_ready": "label_ready",
        "ready": "label_ready",
        "handed_over": "handed_over",
        "picked_up": "handed_over",
        "in_transit": "in_transit",
        "delivered": "delivered",
        "exception": "exception",
        "returned": "returned",
        "cancelled": "cancelled",
        "canceled": "cancelled",
    }
    return mapping.get(status)


def sync_shipment_status(
    db_conn,
    *,
    shipment_id: UUID,
    adapter,
    trace_id: Optional[str],
    event_id: Optional[str] = None,
    occurred_at: Optional[str] = None,
) -> Dict[str, Any]:
    _ensure_tx_connection(db_conn)
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, order_id, current_status, carrier_external_id
            FROM shipments
            WHERE id = %s
            LIMIT 1
            FOR UPDATE
            """,
            (str(shipment_id),),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()

    if not row:
        return {
            "action": "UNKNOWN",
            "reason": "shipment_not_found",
            "shipment_id": str(shipment_id),
            "trace_id": trace_id,
        }

    order_id = UUID(str(row[1]))
    current_status = str(row[2] or "")
    carrier_external_id = row[3]
    if not carrier_external_id:
        return {
            "action": "UNKNOWN",
            "reason": "carrier_external_id_missing",
            "shipment_id": str(shipment_id),
            "order_id": str(order_id),
            "trace_id": trace_id,
        }

    try:
        provider_result = adapter.get_tracking_status(
            ShipmentTrackingStatusRequest(
                carrier_external_id=str(carrier_external_id),
                trace_id=trace_id,
            )
        )
    except Exception as exc:
        return {
            "action": "UNKNOWN",
            "reason": "adapter_error",
            "shipment_id": str(shipment_id),
            "order_id": str(order_id),
            "error": str(exc),
            "trace_id": trace_id,
        }

    carrier_status = str(getattr(provider_result, "carrier_status", "") or "")
    next_status = _map_shipment_carrier_status(carrier_status)
    if not next_status:
        return {
            "action": "UNKNOWN",
            "reason": "unsupported_carrier_status",
            "shipment_id": str(shipment_id),
            "order_id": str(order_id),
            "carrier_status": carrier_status,
            "trace_id": trace_id,
        }

    if next_status == current_status:
        return {
            "action": "noop",
            "shipment_id": str(shipment_id),
            "order_id": str(order_id),
            "carrier_status": carrier_status,
            "status": current_status,
            "trace_id": trace_id,
        }

    if not occurred_at:
        occurred_at = datetime.now(timezone.utc).isoformat()
    if not event_id:
        event_id = f"rc7:{shipment_id}:{next_status}"

    transition = update_shipment_status_atomic(
        db_conn,
        shipment_id=shipment_id,
        to_status=next_status,
        event_id=event_id,
        occurred_at=occurred_at,
        reason="reconciliation:carrier_status_sync",
        trace_id=trace_id,
        context={"carrier_status": carrier_status, "source": "phase25_rc7"},
    )
    return {
        "action": "updated",
        "shipment_id": str(shipment_id),
        "order_id": str(order_id),
        "from_status": current_status,
        "to_status": next_status,
        "carrier_status": carrier_status,
        "transition": transition,
        "trace_id": trace_id,
    }


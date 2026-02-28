from __future__ import annotations

import json
from typing import Any, Dict, Optional
from uuid import UUID

from domain.payment_service import _derive_payment_status, _extract_order_total_minor


def verify_payment_cache(
    db_conn,
    *,
    order_id: UUID,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT order_id, payment_status, metadata, order_total_minor
            FROM order_ledger
            WHERE order_id = %s
            LIMIT 1
            """,
            (str(order_id),),
        )
        row = cursor.fetchone()
        if not row:
            return {"verdict": "DIVERGENCE", "reason": "order_not_found", "order_id": str(order_id), "trace_id": trace_id}

        order_row = {"order_id": row[0], "metadata": row[2], "order_total_minor": row[3]}
        actual_status = str(row[1] or "unpaid")

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
        expected_status = _derive_payment_status(net_paid_minor, order_total_minor, has_pending_refund)

        is_match = expected_status == actual_status
        return {
            "verdict": "MATCH" if is_match else "DIVERGENCE",
            "order_id": str(order_id),
            "expected": {"payment_status": expected_status},
            "actual": {"payment_status": actual_status},
            "details": {
                "charges_minor": charges_minor,
                "refunds_minor": refunds_minor,
                "net_paid_minor": net_paid_minor,
                "order_total_minor": order_total_minor,
                "has_pending_refund": has_pending_refund,
            },
            "trace_id": trace_id,
        }
    finally:
        cursor.close()


def verify_shipment_cache(
    db_conn,
    *,
    order_id: UUID,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT cdek_uuid
            FROM order_ledger
            WHERE order_id = %s
            LIMIT 1
            """,
            (str(order_id),),
        )
        row = cursor.fetchone()
        if not row:
            return {"verdict": "DIVERGENCE", "reason": "order_not_found", "order_id": str(order_id), "trace_id": trace_id}
        actual_cdek_uuid = row[0]

        cursor.execute(
            """
            SELECT carrier_external_id
            FROM shipments
            WHERE order_id = %s
              AND carrier_code = 'cdek'
              AND current_status <> 'cancelled'
              AND carrier_external_id IS NOT NULL
            ORDER BY shipment_seq DESC
            LIMIT 1
            """,
            (str(order_id),),
        )
        top = cursor.fetchone()
        expected_cdek_uuid = top[0] if top else None

        is_match = actual_cdek_uuid == expected_cdek_uuid
        return {
            "verdict": "MATCH" if is_match else "DIVERGENCE",
            "order_id": str(order_id),
            "expected": {"cdek_uuid": expected_cdek_uuid},
            "actual": {"cdek_uuid": actual_cdek_uuid},
            "trace_id": trace_id,
        }
    finally:
        cursor.close()


def verify_document_key(
    db_conn,
    *,
    order_id: UUID,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT invoice_request_key, revision
            FROM order_ledger
            WHERE order_id = %s
            LIMIT 1
            """,
            (str(order_id),),
        )
        ledger = cursor.fetchone()
        if not ledger:
            return {"verdict": "DIVERGENCE", "reason": "order_not_found", "order_id": str(order_id), "trace_id": trace_id}
        ledger_key = ledger[0]
        ledger_revision = int(ledger[1]) if ledger[1] is not None else None

        cursor.execute(
            """
            SELECT id, generation_key, revision
            FROM documents
            WHERE order_id = %s
              AND document_type = 'invoice'
              AND status = 'issued'
            ORDER BY revision DESC
            LIMIT 1
            """,
            (str(order_id),),
        )
        doc = cursor.fetchone()
        if not doc:
            return {
                "verdict": "MATCH",
                "reason": "no_issued_invoice",
                "order_id": str(order_id),
                "trace_id": trace_id,
            }

        doc_id = str(doc[0])
        doc_key = str(doc[1])
        doc_revision = int(doc[2])

        is_match = (ledger_key == doc_key) and (ledger_revision == doc_revision)
        return {
            "verdict": "MATCH" if is_match else "DIVERGENCE",
            "order_id": str(order_id),
            "expected": {"invoice_request_key": doc_key, "revision": doc_revision},
            "actual": {"invoice_request_key": ledger_key, "revision": ledger_revision},
            "details": {"document_id": doc_id},
            "trace_id": trace_id,
        }
    finally:
        cursor.close()


def verify_stock_snapshot(
    db_conn,
    *,
    product_id: UUID,
    warehouse_code: str,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT quantity_on_hand, quantity_reserved, quantity_available
            FROM availability_snapshot
            WHERE product_id = %s
              AND warehouse_code = %s
            LIMIT 1
            """,
            (str(product_id), warehouse_code),
        )
        snap = cursor.fetchone()
        if not snap:
            return {
                "verdict": "DIVERGENCE",
                "reason": "snapshot_missing",
                "product_id": str(product_id),
                "warehouse_code": str(warehouse_code),
                "trace_id": trace_id,
            }
        snapshot_on_hand = int(snap[0])
        snapshot_reserved = int(snap[1])
        snapshot_available = int(snap[2])

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

        is_match = (
            snapshot_on_hand == expected_on_hand
            and snapshot_reserved == expected_reserved
            and snapshot_available == expected_available
        )
        return {
            "verdict": "MATCH" if is_match else "DIVERGENCE",
            "product_id": str(product_id),
            "warehouse_code": str(warehouse_code),
            "expected": {
                "quantity_on_hand": expected_on_hand,
                "quantity_reserved": expected_reserved,
                "quantity_available": expected_available,
            },
            "actual": {
                "quantity_on_hand": snapshot_on_hand,
                "quantity_reserved": snapshot_reserved,
                "quantity_available": snapshot_available,
            },
            "delta": {
                "on_hand": snapshot_on_hand - expected_on_hand,
                "reserved": snapshot_reserved - expected_reserved,
                "available": snapshot_available - expected_available,
            },
            "trace_id": trace_id,
        }
    finally:
        cursor.close()


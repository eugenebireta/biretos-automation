from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID


def verify_pending_payment_state(
    db_conn,
    *,
    payment_transaction_id: UUID,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    RC-6 verify: confirm payment_transaction is no longer pending after resolve_pending_payment.
    Read-only: SELECT only. No writes to any Core table.
    """
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, order_id, status
            FROM payment_transactions
            WHERE id = %s
            LIMIT 1
            """,
            (str(payment_transaction_id),),
        )
        row = cursor.fetchone()
        if not row:
            return {
                "verdict": "UNKNOWN",
                "reason": "payment_transaction_not_found",
                "payment_transaction_id": str(payment_transaction_id),
                "trace_id": trace_id,
            }
        actual_status = str(row[2] or "")
        is_resolved = actual_status != "pending"
        return {
            "verdict": "MATCH" if is_resolved else "DIVERGENCE",
            "payment_transaction_id": str(payment_transaction_id),
            "order_id": str(row[1]),
            "actual_status": actual_status,
            "expected": "not pending",
            "trace_id": trace_id,
        }
    finally:
        cursor.close()


def verify_shipment_carrier_sync(
    db_conn,
    *,
    shipment_id: UUID,
    expected_status: str,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    RC-7 verify: confirm shipment current_status matches expected after sync_shipment_status.
    Read-only: SELECT only. No writes to any Core table.
    """
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, order_id, current_status
            FROM shipments
            WHERE id = %s
            LIMIT 1
            """,
            (str(shipment_id),),
        )
        row = cursor.fetchone()
        if not row:
            return {
                "verdict": "UNKNOWN",
                "reason": "shipment_not_found",
                "shipment_id": str(shipment_id),
                "trace_id": trace_id,
            }
        actual_status = str(row[2] or "")
        is_match = actual_status == expected_status
        return {
            "verdict": "MATCH" if is_match else "DIVERGENCE",
            "shipment_id": str(shipment_id),
            "order_id": str(row[1]),
            "expected": {"current_status": expected_status},
            "actual": {"current_status": actual_status},
            "trace_id": trace_id,
        }
    finally:
        cursor.close()

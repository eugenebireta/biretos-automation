from __future__ import annotations

import json
from typing import Any, Dict, Optional
from uuid import UUID


def _ensure_tx_connection(db_conn) -> None:
    if getattr(db_conn, "autocommit", False):
        raise RuntimeError("PaymentService requires autocommit=False")


def _extract_order_total_minor(order_row: Dict[str, Any]) -> int:
    # F2 hardening: structural column takes priority.
    col_value = order_row.get("order_total_minor")
    if col_value is not None:
        try:
            return int(col_value)
        except (ValueError, TypeError):
            pass

    # Backward-compatible fallback to metadata.
    metadata = order_row.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    total_amount = metadata.get("totalAmount")
    if total_amount is None:
        return 0
    try:
        return int(round(float(total_amount) * 100))
    except Exception:
        return 0


def _derive_payment_status(net_paid_minor: int, order_total_minor: int, has_pending_refund: bool) -> str:
    if has_pending_refund:
        return "refund_pending"
    if net_paid_minor <= 0:
        return "unpaid"
    if order_total_minor > 0 and net_paid_minor < order_total_minor:
        return "partially_paid"
    if order_total_minor > 0 and net_paid_minor == order_total_minor:
        return "paid"
    if order_total_minor > 0 and net_paid_minor > order_total_minor:
        return "overpaid"
    return "paid"


def record_payment_transaction_atomic(
    db_conn,
    *,
    order_id: UUID,
    trace_id: Optional[str],
    transaction_type: str,
    provider_code: str,
    provider_transaction_id: str,
    amount_minor: int,
    currency: str,
    status: str,
    status_changed_at: str,
    idempotency_key: str,
    raw_provider_response: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    UC-2 (v2.1): PaymentTransaction insert + order_ledger payment cache update
    MUST happen in the same transaction.
    """
    _ensure_tx_connection(db_conn)
    if amount_minor < 0:
        raise ValueError("amount_minor must be >= 0")

    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT order_id, metadata, order_total_minor
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
        order_row = {"order_id": row[0], "metadata": row[1], "order_total_minor": row[2]}

        cursor.execute(
            """
            INSERT INTO payment_transactions (
                order_id, trace_id, transaction_type, provider_code, provider_transaction_id,
                amount_minor, currency, status, status_changed_at, idempotency_key,
                raw_provider_response, metadata, created_at, updated_at
            )
            VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s::timestamptz, %s, %s::jsonb, %s::jsonb, NOW(), NOW())
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (
                str(order_id),
                trace_id,
                transaction_type,
                provider_code,
                provider_transaction_id,
                amount_minor,
                currency,
                status,
                status_changed_at,
                idempotency_key,
                json.dumps(raw_provider_response or {}, ensure_ascii=False),
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        inserted = cursor.fetchone()
        action = "inserted" if inserted else "duplicate"

        # Recompute from persisted ledger for deterministic cache.
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

        net_paid_minor = charges_minor - refunds_minor
        order_total_minor = _extract_order_total_minor(order_row)
        payment_status = _derive_payment_status(net_paid_minor, order_total_minor, has_pending_refund)

        cursor.execute(
            """
            UPDATE order_ledger
            SET payment_status = %s,
                payment_status_changed_at = NOW(),
                updated_at = NOW()
            WHERE order_id = %s
            """,
            (payment_status, str(order_id)),
        )

        return {
            "action": action,
            "payment_status": payment_status,
            "net_paid_minor": net_paid_minor,
            "order_total_minor": order_total_minor,
        }
    finally:
        cursor.close()


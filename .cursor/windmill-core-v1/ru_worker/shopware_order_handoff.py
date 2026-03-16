from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid5, NAMESPACE_URL


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _core_state_from_shopware(payload: Dict[str, Any]) -> str:
    payment_state = str(payload.get("payment_state") or "").lower()
    order_state = str(payload.get("order_state") or "").lower()
    if order_state in {"cancelled", "canceled"}:
        return "cancelled"
    if payment_state in {"paid", "authorized"}:
        return "paid"
    return "pending_payment"


def _guardian_check(payload: Dict[str, Any]) -> Optional[str]:
    order_number = str(payload.get("order_number") or "").strip()
    if not order_number:
        return "order_number is required"
    currency = str(payload.get("currency") or "").strip()
    if not currency:
        return "currency is required"
    total_minor = _as_int(payload.get("total_minor"))
    if total_minor < 0:
        return "total_minor must be >= 0"
    return None


def _mark_inbound_event(
    db_conn,
    *,
    event_id: Optional[str],
    status: str,
    error_text: Optional[str] = None,
) -> None:
    if not event_id:
        return
    cur = db_conn.cursor()
    try:
        if status == "processed":
            cur.execute(
                """
                UPDATE shopware_inbound_events
                SET processing_status = 'processed',
                    processed_at = NOW(),
                    error_text = NULL
                WHERE event_id = %s
                """,
                (event_id,),
            )
        else:
            cur.execute(
                """
                UPDATE shopware_inbound_events
                SET processing_status = 'failed',
                    processed_at = NOW(),
                    error_text = %s
                WHERE event_id = %s
                """,
                (error_text or status, event_id),
            )
    finally:
        cur.close()


def _enqueue_status_sync(
    db_conn,
    *,
    instance: str,
    order_number: str,
    core_state: str,
    trace_id: Optional[str],
) -> bool:
    payload = {"order_number": order_number, "target_core_state": core_state}
    idempotency_key = f"shopware-status:{instance}:{order_number}:{core_state}"
    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO shopware_outbound_queue (
                instance, entity_type, entity_id, payload, status, idempotency_key, trace_id
            )
            VALUES (%s, 'order_status', %s, %s::jsonb, 'pending', %s, %s::uuid)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (
                instance,
                order_number,
                json.dumps(payload, ensure_ascii=False),
                idempotency_key,
                trace_id,
            ),
        )
        return bool(cur.fetchone())
    finally:
        cur.close()


def execute_shopware_order_handoff(
    payload: Dict[str, Any],
    db_conn,
    *,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Hand-off flow (Shopware checkout -> Core order record).
    """
    instance = str(payload.get("instance") or "ru").strip().lower()
    if instance not in {"ru", "int"}:
        raise ValueError("instance must be ru|int")

    guardian_error = _guardian_check(payload)
    event_id = payload.get("shopware_event_id")
    if guardian_error:
        _mark_inbound_event(
            db_conn,
            event_id=event_id,
            status="failed",
            error_text=f"guardian_block: {guardian_error}",
        )
        return {"status": "blocked", "reason": guardian_error}

    order_number = str(payload["order_number"]).strip()
    total_minor = _as_int(payload.get("total_minor"))
    currency = str(payload.get("currency") or "RUB").upper()
    core_state = _core_state_from_shopware(payload)

    order_seed = f"shopware:{instance}:{order_number}"
    order_id = uuid5(NAMESPACE_URL, order_seed)
    customer_data = payload.get("customer") if isinstance(payload.get("customer"), dict) else {}
    delivery_data = payload.get("delivery") if isinstance(payload.get("delivery"), dict) else {}

    metadata = {
        "source": "shopware",
        "instance": instance,
        "shopware_event_id": event_id,
        "shopware_order_id": payload.get("shopware_order_id"),
        "order_number": order_number,
        "order_state": payload.get("order_state"),
        "payment_state": payload.get("payment_state"),
        "delivery_state": payload.get("delivery_state"),
        "currency": currency,
        "total_minor": total_minor,
        "handoff_received_at": datetime.now(timezone.utc).isoformat(),
    }
    state_history = [
        {
            "from": None,
            "to": core_state,
            "reason": "shopware_handoff",
            "at": datetime.now(timezone.utc).isoformat(),
        }
    ]

    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO order_ledger (
                order_id,
                insales_order_id,
                invoice_request_key,
                state,
                state_history,
                customer_data,
                delivery_data,
                error_log,
                metadata
            )
            VALUES (
                %s::uuid,
                %s,
                %s,
                %s,
                %s::jsonb,
                %s::jsonb,
                %s::jsonb,
                '[]'::jsonb,
                %s::jsonb
            )
            ON CONFLICT (insales_order_id) DO UPDATE SET
                state = EXCLUDED.state,
                metadata = EXCLUDED.metadata,
                customer_data = EXCLUDED.customer_data,
                delivery_data = EXCLUDED.delivery_data,
                updated_at = NOW()
            """,
            (
                str(order_id),
                order_seed,
                f"shopware-handoff:{instance}:{order_number}",
                core_state,
                json.dumps(state_history, ensure_ascii=False),
                json.dumps(customer_data, ensure_ascii=False),
                json.dumps(delivery_data, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
    finally:
        cur.close()

    outbound_enqueued = _enqueue_status_sync(
        db_conn,
        instance=instance,
        order_number=order_number,
        core_state=core_state,
        trace_id=trace_id,
    )
    _mark_inbound_event(db_conn, event_id=event_id, status="processed")

    return {
        "status": "completed",
        "order_id": str(order_id),
        "order_number": order_number,
        "core_state": core_state,
        "outbound_enqueued": outbound_enqueued,
    }

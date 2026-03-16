#!/usr/bin/env python3
"""
Phase C fallback: polling Shopware orders when webhook delivery degrades.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

OrderFetcher = Callable[[Any, str, Optional[str]], List[Dict[str, Any]]]


def _ensure_state_table(db_conn) -> None:
    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS wm_state (
                key TEXT PRIMARY KEY,
                value JSONB,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
    finally:
        cur.close()


def _get_cursor(db_conn, key: str) -> Optional[str]:
    _ensure_state_table(db_conn)
    cur = db_conn.cursor()
    try:
        cur.execute("SELECT value FROM wm_state WHERE key = %s", (key,))
        row = cur.fetchone()
        if not row:
            return None
        value = row[0]
        if isinstance(value, str):
            value = json.loads(value)
        if isinstance(value, dict):
            cursor_value = value.get("cursor")
            return str(cursor_value) if cursor_value else None
        return None
    finally:
        cur.close()


def _set_cursor(db_conn, key: str, cursor_value: str) -> None:
    _ensure_state_table(db_conn)
    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO wm_state (key, value, updated_at)
            VALUES (%s, %s::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_at = NOW()
            """,
            (key, json.dumps({"cursor": cursor_value}, ensure_ascii=False)),
        )
    finally:
        cur.close()


def _insert_inbound_event(db_conn, instance: str, event_id: str, event_type: str, payload: Dict[str, Any], trace_id: str) -> bool:
    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO shopware_inbound_events (
                instance, event_id, event_type, payload,
                idempotency_key, trace_id, processing_status
            )
            VALUES (%s, %s, %s, %s::jsonb, %s, %s::uuid, 'queued')
            ON CONFLICT (event_id) DO NOTHING
            RETURNING id
            """,
            (
                instance,
                event_id,
                event_type,
                json.dumps(payload, ensure_ascii=False),
                f"shopware-poll-event:{instance}:{event_id}",
                trace_id,
            ),
        )
        return bool(cur.fetchone())
    finally:
        cur.close()


def _enqueue_handoff_job(db_conn, instance: str, event_id: str, payload: Dict[str, Any], trace_id: str) -> bool:
    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO job_queue (id, job_type, payload, status, idempotency_key, trace_id)
            VALUES (gen_random_uuid(), 'shopware_order_handoff', %s::jsonb, 'pending', %s, %s::uuid)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (
                json.dumps(payload, ensure_ascii=False),
                f"shopware-poll-handoff:{instance}:{event_id}",
                trace_id,
            ),
        )
        return bool(cur.fetchone())
    finally:
        cur.close()


def _default_fetch_orders(_db_conn, _instance: str, _cursor: Optional[str]) -> List[Dict[str, Any]]:
    return []


def run_shopware_order_polling_fallback(
    db_conn,
    payload: Dict[str, Any],
    *,
    fetch_orders: Optional[OrderFetcher] = None,
) -> Dict[str, Any]:
    instance = str(payload.get("instance") or "ru").strip().lower()
    if instance not in {"ru", "int"}:
        raise ValueError("instance must be ru|int")

    cursor_key = f"shopware_poll_cursor:{instance}"
    current_cursor = _get_cursor(db_conn, cursor_key)

    fetcher = fetch_orders or _default_fetch_orders
    orders = fetcher(db_conn, instance, current_cursor)
    created_events = 0
    enqueued_jobs = 0
    max_cursor = current_cursor

    for order in orders:
        order_number = str(order.get("order_number") or "").strip()
        if not order_number:
            continue
        updated_at = str(order.get("updated_at") or datetime.now(timezone.utc).isoformat())
        event_id = f"poll:{instance}:{order_number}:{updated_at}"
        trace_id = str(uuid4())
        normalized = {
            "instance": instance,
            "event_type": "polling.order.detected",
            "shopware_event_id": event_id,
            "shopware_order_id": order.get("shopware_order_id"),
            "order_number": order_number,
            "order_state": order.get("order_state"),
            "payment_state": order.get("payment_state"),
            "delivery_state": order.get("delivery_state"),
            "currency": order.get("currency") or "RUB",
            "total_minor": int(order.get("total_minor") or 0),
            "customer": order.get("customer") if isinstance(order.get("customer"), dict) else {},
            "delivery": order.get("delivery") if isinstance(order.get("delivery"), list) else [],
            "raw_payload": order,
        }

        if _insert_inbound_event(db_conn, instance, event_id, "polling.order.detected", normalized, trace_id):
            created_events += 1
        if _enqueue_handoff_job(db_conn, instance, event_id, normalized, trace_id):
            enqueued_jobs += 1
        if max_cursor is None or updated_at > max_cursor:
            max_cursor = updated_at

    if max_cursor:
        _set_cursor(db_conn, cursor_key, max_cursor)
    db_conn.commit()
    return {
        "instance": instance,
        "source_cursor": current_cursor,
        "next_cursor": max_cursor,
        "created_events": created_events,
        "enqueued_jobs": enqueued_jobs,
        "scanned_orders": len(orders),
    }

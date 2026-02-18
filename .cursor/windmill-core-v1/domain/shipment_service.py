from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import UUID

from domain.fsm_guards import validate_transition


SHIPMENT_ALLOWED_TRANSITIONS = {
    "created": {"label_ready", "cancelled"},
    "label_ready": {"handed_over", "cancelled"},
    "handed_over": {"in_transit"},
    "in_transit": {"delivered", "exception"},
    "exception": {"in_transit", "returned"},
    "delivered": set(),
    "returned": set(),
    "cancelled": set(),
}

SHIPMENT_CREATION_ALLOWED_ORDER_STATES = {
    "paid",
    "shipment_pending",
    "partially_shipped",
    # legacy compatibility
    "shipment_created",
    "consignment_registered",
}


def _ensure_tx_connection(db_conn) -> None:
    if getattr(db_conn, "autocommit", False):
        raise RuntimeError("ShipmentService requires autocommit=False")


def _json_value(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return fallback
    return fallback


def _extract_line_item_ids(packages: Any) -> List[str]:
    parsed = _json_value(packages, [])
    if not isinstance(parsed, list):
        return []
    ids: List[str] = []
    for package in parsed:
        if not isinstance(package, dict):
            continue
        items = package.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            line_item_id = item.get("line_item_id")
            if line_item_id:
                ids.append(str(line_item_id))
    # keep deterministic order while deduplicating
    return list(dict.fromkeys(ids))


def recompute_order_cdek_cache_atomic(db_conn, *, order_id: UUID) -> Optional[str]:
    """
    UC-3 (v2.1):
    order_ledger.cdek_uuid = latest non-cancelled cdek shipment UUID.
    Must run in same transaction as shipment status updates.
    """
    _ensure_tx_connection(db_conn)
    cursor = db_conn.cursor()
    try:
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
        row = cursor.fetchone()
        latest = row[0] if row else None
        cursor.execute(
            """
            UPDATE order_ledger
            SET cdek_uuid = %s,
                updated_at = NOW()
            WHERE order_id = %s
            """,
            (latest, str(order_id)),
        )
        return latest
    finally:
        cursor.close()


def _upsert_order_state_history_transition(
    db_conn,
    *,
    order_id: UUID,
    from_state: str,
    to_state: str,
    event_id: str,
    reason: str,
    context: Dict[str, Any],
    occurred_at: str,
    trace_id: Optional[str],
) -> None:
    if not validate_transition(from_state, to_state):
        raise RuntimeError(
            f"FSM guard: transition {from_state!r} -> {to_state!r} not allowed"
        )

    cursor = db_conn.cursor()
    try:
        entry = {
            "from_state": from_state,
            "to_state": to_state,
            "reason": reason,
            "context": context,
            "timestamp": occurred_at,
            "event_id": event_id,
        }
        cursor.execute(
            """
            UPDATE order_ledger
            SET state = %s,
                state_history = state_history || %s::jsonb,
                trace_id = COALESCE(trace_id, %s::uuid),
                status_changed_at = NOW(),
                updated_at = NOW()
            WHERE order_id = %s
            """,
            (to_state, json.dumps([entry], ensure_ascii=False), trace_id, str(order_id)),
        )
    finally:
        cursor.close()


def _compute_next_shipment_seq(db_conn, *, order_id: UUID) -> int:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT COALESCE(MAX(shipment_seq), 0)
            FROM shipments
            WHERE order_id = %s
            FOR UPDATE
            """,
            (str(order_id),),
        )
        max_seq = int(cursor.fetchone()[0])
        return max_seq + 1
    finally:
        cursor.close()


def _mark_line_items_allocated(db_conn, *, order_id: UUID, packages: Any) -> List[str]:
    line_item_ids = _extract_line_item_ids(packages)
    if not line_item_ids:
        return []

    cursor = db_conn.cursor()
    try:
        allocated: List[str] = []
        for line_item_id in line_item_ids:
            cursor.execute(
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM reservations
                WHERE order_id = %s
                  AND line_item_id = %s
                  AND status = 'active'
                """,
                (str(order_id), line_item_id),
            )
            active_reservation_qty = int(cursor.fetchone()[0])
            if active_reservation_qty <= 0:
                raise RuntimeError(
                    f"line_item {line_item_id} has no active reservation; allocation forbidden"
                )

            cursor.execute(
                """
                UPDATE order_line_items
                SET line_status = 'allocated',
                    updated_at = NOW()
                WHERE id = %s
                  AND order_id = %s
                """,
                (line_item_id, str(order_id)),
            )
            if cursor.rowcount > 0:
                allocated.append(line_item_id)
        return allocated
    finally:
        cursor.close()


def create_shipment_atomic(
    db_conn,
    *,
    order_id: UUID,
    trace_id: Optional[str],
    carrier_code: str,
    carrier_external_id: Optional[str],
    service_tariff: Optional[str],
    packages: Any,
    address_snapshot: Any,
    idempotency_key: str,
    event_id: str,
    occurred_at: str,
    metadata: Optional[Dict[str, Any]] = None,
    carrier_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    _ensure_tx_connection(db_conn)

    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT order_id, state
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
        current_order_state = str(row[1] or "")
    finally:
        cursor.close()

    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, shipment_seq
            FROM shipments
            WHERE idempotency_key = %s
            LIMIT 1
            """,
            (idempotency_key,),
        )
        existing = cursor.fetchone()
        if existing:
            shipment_id = str(existing[0])
            shipment_seq = int(existing[1])
            if carrier_code == "cdek":
                recompute_order_cdek_cache_atomic(db_conn, order_id=order_id)
            return {
                "action": "duplicate",
                "shipment_id": shipment_id,
                "shipment_seq": shipment_seq,
            }
    finally:
        cursor.close()

    if current_order_state not in SHIPMENT_CREATION_ALLOWED_ORDER_STATES:
        raise RuntimeError(
            f"Cannot create shipment: order {order_id} in state {current_order_state!r}, "
            f"allowed: {sorted(SHIPMENT_CREATION_ALLOWED_ORDER_STATES)}"
        )

    shipment_seq = _compute_next_shipment_seq(db_conn, order_id=order_id)
    parsed_packages = _json_value(packages, [])
    parsed_address = _json_value(address_snapshot, {})
    allocated_ids = _mark_line_items_allocated(db_conn, order_id=order_id, packages=parsed_packages)
    status_history_entry = {
        "from_state": None,
        "to_state": "created",
        "reason": "shipment:create",
        "context": {"allocated_line_items": allocated_ids},
        "timestamp": occurred_at,
        "event_id": event_id,
    }

    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO shipments (
                order_id, trace_id, shipment_seq, carrier_code, carrier_external_id,
                service_tariff, current_status, status_changed_at, packages,
                address_snapshot, status_history, carrier_metadata, metadata,
                idempotency_key, created_at, updated_at
            )
            VALUES (
                %s, %s::uuid, %s, %s, %s, %s, 'created', NOW(), %s::jsonb,
                %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, NOW(), NOW()
            )
            RETURNING id
            """,
            (
                str(order_id),
                trace_id,
                shipment_seq,
                carrier_code,
                carrier_external_id,
                service_tariff,
                json.dumps(parsed_packages, ensure_ascii=False),
                json.dumps(parsed_address, ensure_ascii=False),
                json.dumps([status_history_entry], ensure_ascii=False),
                json.dumps(carrier_metadata or {}, ensure_ascii=False),
                json.dumps(metadata or {}, ensure_ascii=False),
                idempotency_key,
            ),
        )
        shipment_id = str(cursor.fetchone()[0])
    finally:
        cursor.close()

    if current_order_state in {"paid", "shipment_pending"}:
        _upsert_order_state_history_transition(
            db_conn,
            order_id=order_id,
            from_state=current_order_state,
            to_state="partially_shipped" if parsed_packages else "shipment_pending",
            event_id=event_id,
            reason="cdek:SHIPMENT_CREATED",
            context={"shipment_id": shipment_id, "carrier_external_id": carrier_external_id},
            occurred_at=occurred_at,
            trace_id=trace_id,
        )

    if carrier_code == "cdek":
        recompute_order_cdek_cache_atomic(db_conn, order_id=order_id)

    return {
        "action": "created",
        "shipment_id": shipment_id,
        "shipment_seq": shipment_seq,
        "allocated_line_items": allocated_ids,
    }


def _transition_allowed(from_status: str, to_status: str) -> bool:
    return to_status in SHIPMENT_ALLOWED_TRANSITIONS.get(from_status, set())


def _unpack_line_items_for_cancel(
    db_conn,
    *,
    order_id: UUID,
    packages: Any,
) -> Dict[str, list[str]]:
    line_item_ids = _extract_line_item_ids(packages)
    if not line_item_ids:
        return {"line_items_deallocated": [], "line_items_already_released": []}

    cursor = db_conn.cursor()
    try:
        deallocated: List[str] = []
        already_released: List[str] = []

        for line_item_id in line_item_ids:
            cursor.execute(
                """
                SELECT line_status
                FROM order_line_items
                WHERE id = %s
                  AND order_id = %s
                LIMIT 1
                FOR UPDATE
                """,
                (line_item_id, str(order_id)),
            )
            row = cursor.fetchone()
            if not row:
                continue
            line_status = row[0]

            if line_status == "allocated":
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(quantity), 0)
                    FROM reservations
                    WHERE order_id = %s
                      AND line_item_id = %s
                      AND status = 'active'
                    """,
                    (str(order_id), line_item_id),
                )
                active_reserved_qty = int(cursor.fetchone()[0])
                next_status = "reserved" if active_reserved_qty > 0 else "pending"
                cursor.execute(
                    """
                    UPDATE order_line_items
                    SET line_status = %s,
                        updated_at = NOW()
                    WHERE id = %s
                      AND order_id = %s
                    """,
                    (next_status, line_item_id, str(order_id)),
                )
                deallocated.append(line_item_id)
            else:
                already_released.append(line_item_id)

        return {
            "line_items_deallocated": deallocated,
            "line_items_already_released": already_released,
        }
    finally:
        cursor.close()


def update_shipment_status_atomic(
    db_conn,
    *,
    shipment_id: UUID,
    to_status: str,
    event_id: str,
    occurred_at: str,
    reason: str,
    trace_id: Optional[str],
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    _ensure_tx_connection(db_conn)
    context = context or {}
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, order_id, carrier_code, current_status, packages, status_history
            FROM shipments
            WHERE id = %s
            LIMIT 1
            FOR UPDATE
            """,
            (str(shipment_id),),
        )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError(f"shipment not found: {shipment_id}")

        order_id = UUID(str(row[1]))
        carrier_code = str(row[2])
        from_status = str(row[3])
        packages = _json_value(row[4], [])
        status_history = _json_value(row[5], [])
        if not isinstance(status_history, list):
            status_history = []

        if from_status == to_status:
            return {"action": "duplicate", "from_status": from_status, "to_status": to_status}

        if not _transition_allowed(from_status, to_status):
            raise RuntimeError(f"shipment transition not allowed: {from_status} -> {to_status}")

        unpack_result = None
        if to_status == "cancelled":
            if from_status not in {"created", "label_ready"}:
                raise RuntimeError("shipment cancellation forbidden after handover")
            unpack_result = _unpack_line_items_for_cancel(db_conn, order_id=order_id, packages=packages)

        history_entry = {
            "from_state": from_status,
            "to_state": to_status,
            "reason": reason,
            "context": context,
            "timestamp": occurred_at,
            "event_id": event_id,
        }
        if unpack_result is not None:
            history_entry["unpack_result"] = unpack_result
        status_history.append(history_entry)

        cursor.execute(
            """
            UPDATE shipments
            SET current_status = %s,
                status_changed_at = NOW(),
                status_history = %s::jsonb,
                trace_id = COALESCE(trace_id, %s::uuid),
                updated_at = NOW()
            WHERE id = %s
            """,
            (to_status, json.dumps(status_history, ensure_ascii=False), trace_id, str(shipment_id)),
        )
    finally:
        cursor.close()

    if carrier_code == "cdek":
        recompute_order_cdek_cache_atomic(db_conn, order_id=order_id)

    return {
        "action": "updated",
        "from_status": from_status,
        "to_status": to_status,
        "unpack_result": unpack_result,
    }


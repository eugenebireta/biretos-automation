from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
from uuid import UUID


@dataclass(frozen=True)
class ReservationResult:
    action: str  # reserved|backordered|duplicate|noop
    reserved_quantity: int
    line_status: str
    reservation_id: Optional[str] = None


def build_reservation_chunk_keys(
    order_id: UUID,
    line_item_id: UUID,
    fulfillment_event_id: UUID,
) -> tuple[str, str]:
    reservation_idempotency_key = (
        f"reservation:{order_id}:{line_item_id}:{fulfillment_event_id}"
    )
    stock_idempotency_key = (
        f"stock:{order_id}:{line_item_id}:{fulfillment_event_id}:reservation"
    )
    return reservation_idempotency_key, stock_idempotency_key


def _ensure_tx_connection(db_conn) -> None:
    if getattr(db_conn, "autocommit", False):
        raise RuntimeError("AvailabilityService requires autocommit=False")


def _ensure_snapshot_row(db_conn, product_id: UUID, warehouse_code: str, sku: str) -> None:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO availability_snapshot (
                product_id, warehouse_code, sku,
                quantity_on_hand, quantity_reserved, quantity_available,
                snapshot_at, updated_at
            )
            VALUES (%s, %s, %s, 0, 0, 0, NOW(), NOW())
            ON CONFLICT (product_id, warehouse_code) DO NOTHING
            """,
            (str(product_id), warehouse_code, sku),
        )
    finally:
        cursor.close()


def apply_stock_receipt_atomic(
    db_conn,
    *,
    product_id: UUID,
    sku: str,
    warehouse_code: str,
    quantity: int,
    reference_type: str,
    reference_id: Optional[UUID],
    trace_id: Optional[str],
    idempotency_key: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    _ensure_tx_connection(db_conn)
    if quantity <= 0:
        raise ValueError("quantity must be > 0 for stock receipt")

    _ensure_snapshot_row(db_conn, product_id, warehouse_code, sku)

    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT quantity_on_hand, quantity_reserved, quantity_available
            FROM availability_snapshot
            WHERE product_id = %s AND warehouse_code = %s
            FOR UPDATE
            """,
            (str(product_id), warehouse_code),
        )
        snap = cursor.fetchone()
        if not snap:
            raise RuntimeError("availability_snapshot row missing after ensure")

        cursor.execute(
            """
            INSERT INTO stock_ledger_entries (
                product_id, sku, warehouse_code, change_type, quantity_delta,
                reference_type, reference_id, trace_id, idempotency_key, metadata
            )
            VALUES (%s, %s, %s, 'receipt', %s, %s, %s, %s::uuid, %s, %s::jsonb)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (
                str(product_id),
                sku,
                warehouse_code,
                quantity,
                reference_type,
                str(reference_id) if reference_id else None,
                trace_id,
                idempotency_key,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        row = cursor.fetchone()
        if not row:
            return {"action": "duplicate", "quantity": 0}

        cursor.execute(
            """
            UPDATE availability_snapshot
            SET quantity_on_hand = quantity_on_hand + %s,
                quantity_available = quantity_available + %s,
                snapshot_at = NOW(),
                updated_at = NOW()
            WHERE product_id = %s AND warehouse_code = %s
            """,
            (quantity, quantity, str(product_id), warehouse_code),
        )
        return {"action": "applied", "quantity": quantity}
    finally:
        cursor.close()


def reserve_inventory_chunk_atomic(
    db_conn,
    *,
    order_id: UUID,
    line_item_id: UUID,
    fulfillment_event_id: UUID,
    product_id: UUID,
    sku_snapshot: str,
    warehouse_code: str,
    trace_id: Optional[str],
    expires_at: Optional[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> ReservationResult:
    """
    UC-1.x (v2.1):
    - Lock snapshot row FOR UPDATE.
    - Insert stock ledger reservation delta.
    - Insert immutable reservation chunk.
    - Update snapshot in the same DB transaction.
    """
    _ensure_tx_connection(db_conn)

    _ensure_snapshot_row(db_conn, product_id, warehouse_code, sku_snapshot)

    reservation_idempotency_key, stock_idempotency_key = build_reservation_chunk_keys(
        order_id, line_item_id, fulfillment_event_id
    )

    cursor = db_conn.cursor()
    try:
        # Fast idempotency gate.
        cursor.execute(
            """
            SELECT id
            FROM reservations
            WHERE idempotency_key = %s
            LIMIT 1
            """,
            (reservation_idempotency_key,),
        )
        existing_reservation = cursor.fetchone()
        if existing_reservation:
            cursor.execute(
                """
                SELECT line_status
                FROM order_line_items
                WHERE id = %s
                LIMIT 1
                """,
                (str(line_item_id),),
            )
            line_row = cursor.fetchone()
            line_status = line_row[0] if line_row else "pending"
            return ReservationResult(
                action="duplicate",
                reserved_quantity=0,
                line_status=line_status,
                reservation_id=str(existing_reservation[0]),
            )

        cursor.execute(
            """
            SELECT quantity_on_hand, quantity_reserved, quantity_available
            FROM availability_snapshot
            WHERE product_id = %s AND warehouse_code = %s
            FOR UPDATE
            """,
            (str(product_id), warehouse_code),
        )
        snap = cursor.fetchone()
        if not snap:
            raise RuntimeError("availability_snapshot row missing after ensure")
        quantity_available = int(snap[2])

        cursor.execute(
            """
            SELECT quantity
            FROM order_line_items
            WHERE id = %s AND order_id = %s
            LIMIT 1
            FOR UPDATE
            """,
            (str(line_item_id), str(order_id)),
        )
        line_row = cursor.fetchone()
        if not line_row:
            raise RuntimeError("line_item not found for reservation")
        line_total_qty = int(line_row[0])

        cursor.execute(
            """
            SELECT COALESCE(SUM(quantity), 0)
            FROM reservations
            WHERE order_id = %s
              AND line_item_id = %s
              AND status = 'active'
            """,
            (str(order_id), str(line_item_id)),
        )
        reserved_already = int(cursor.fetchone()[0])
        needed = max(0, line_total_qty - reserved_already)
        if needed <= 0:
            cursor.execute(
                """
                UPDATE order_line_items
                SET line_status = 'reserved',
                    updated_at = NOW()
                WHERE id = %s
                """,
                (str(line_item_id),),
            )
            return ReservationResult(action="noop", reserved_quantity=0, line_status="reserved")

        to_reserve = min(needed, quantity_available)
        if to_reserve <= 0:
            cursor.execute(
                """
                UPDATE order_line_items
                SET line_status = 'backordered',
                    updated_at = NOW()
                WHERE id = %s
                """,
                (str(line_item_id),),
            )
            return ReservationResult(action="backordered", reserved_quantity=0, line_status="backordered")

        cursor.execute(
            """
            INSERT INTO stock_ledger_entries (
                product_id, sku, warehouse_code, change_type, quantity_delta,
                reference_type, reference_id, trace_id, idempotency_key, metadata
            )
            VALUES (%s, %s, %s, 'reservation', %s, 'order_line_item', %s, %s::uuid, %s, %s::jsonb)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (
                str(product_id),
                sku_snapshot,
                warehouse_code,
                -to_reserve,
                str(line_item_id),
                trace_id,
                stock_idempotency_key,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        ledger_row = cursor.fetchone()
        if not ledger_row:
            return ReservationResult(action="duplicate", reserved_quantity=0, line_status="pending")

        cursor.execute(
            """
            INSERT INTO reservations (
                order_id, line_item_id, product_id, sku_snapshot, warehouse_code,
                quantity, status, fulfillment_event_id, trace_id, idempotency_key,
                expires_at, metadata, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'active', %s, %s::uuid, %s, %s::timestamptz, %s::jsonb, NOW(), NOW())
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (
                str(order_id),
                str(line_item_id),
                str(product_id),
                sku_snapshot,
                warehouse_code,
                to_reserve,
                str(fulfillment_event_id),
                trace_id,
                reservation_idempotency_key,
                expires_at,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        reservation_row = cursor.fetchone()
        if not reservation_row:
            return ReservationResult(action="duplicate", reserved_quantity=0, line_status="pending")

        cursor.execute(
            """
            UPDATE availability_snapshot
            SET quantity_reserved = quantity_reserved + %s,
                quantity_available = quantity_available - %s,
                snapshot_at = NOW(),
                updated_at = NOW()
            WHERE product_id = %s AND warehouse_code = %s
            """,
            (to_reserve, to_reserve, str(product_id), warehouse_code),
        )

        final_reserved = reserved_already + to_reserve
        final_line_status = "reserved" if final_reserved >= line_total_qty else "backordered"
        cursor.execute(
            """
            UPDATE order_line_items
            SET line_status = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (final_line_status, str(line_item_id)),
        )
        return ReservationResult(
            action="reserved" if final_line_status == "reserved" else "backordered",
            reserved_quantity=to_reserve,
            line_status=final_line_status,
            reservation_id=str(reservation_row[0]),
        )
    finally:
        cursor.close()


def release_reservations_for_order_atomic(
    db_conn,
    *,
    order_id: UUID,
    trace_id: Optional[str],
    reason: str = "terminal_failure_cleanup",
) -> Dict[str, Any]:
    """
    Release all active reservations for an order in one transaction.
    Idempotent: repeated calls after release return noop.
    """
    _ensure_tx_connection(db_conn)

    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, line_item_id, product_id, sku_snapshot, warehouse_code, quantity, status
            FROM reservations
            WHERE order_id = %s
              AND status = 'active'
            FOR UPDATE
            """,
            (str(order_id),),
        )
        rows = cursor.fetchall()
        if not rows:
            return {
                "action": "noop",
                "released_count": 0,
                "released_quantity": 0,
            }

        released_count = 0
        released_quantity = 0
        for reservation_id, line_item_id, product_id, sku_snapshot, warehouse_code, quantity, _status in rows:
            quantity = int(quantity or 0)
            if quantity <= 0:
                continue

            release_idempotency_key = f"release:{reservation_id}:{reason}"
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
                    json.dumps({"reason": reason}, ensure_ascii=False),
                ),
            )
            ledger_row = cursor.fetchone()
            if not ledger_row:
                # Already released by previous call.
                continue

            cursor.execute(
                """
                UPDATE reservations
                SET status = 'released',
                    released_at = NOW(),
                    updated_at = NOW(),
                    metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                WHERE id = %s
                  AND status = 'active'
                """,
                (json.dumps({"release_reason": reason}, ensure_ascii=False), str(reservation_id)),
            )
            if cursor.rowcount == 0:
                continue

            cursor.execute(
                """
                UPDATE availability_snapshot
                SET quantity_reserved = GREATEST(0, quantity_reserved - %s),
                    quantity_available = quantity_available + %s,
                    snapshot_at = NOW(),
                    updated_at = NOW()
                WHERE product_id = %s
                  AND warehouse_code = %s
                """,
                (quantity, quantity, str(product_id), warehouse_code),
            )
            cursor.execute(
                """
                UPDATE order_line_items
                SET line_status = CASE
                    WHEN line_status = 'reserved' THEN 'pending'
                    ELSE line_status
                END,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (str(line_item_id),),
            )

            released_count += 1
            released_quantity += quantity

        if released_count == 0:
            return {
                "action": "noop",
                "released_count": 0,
                "released_quantity": 0,
            }
        return {
            "action": "released",
            "released_count": released_count,
            "released_quantity": released_quantity,
        }
    finally:
        cursor.close()


from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

from domain.payment_service import _derive_payment_status, _extract_order_total_minor


HEALTH_PRIORITY = (
    "INCONSISTENT",
    "REQUIRES_MANUAL",
    "STUCK",
    "AWAITING_EXTERNAL",
    "PROGRESSING",
    "HEALTHY",
)

TERMINAL_ORDER_STATES = {"completed", "cancelled", "failed"}

FSM_STALENESS_MINUTES = {
    "pending_invoice": 60,
    "invoice_created": 72 * 60,
    "partially_paid": 24 * 60,
    "paid": 24 * 60,
    "shipment_pending": 48 * 60,
    "partially_shipped": 7 * 24 * 60,
    "shipped": 7 * 24 * 60,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.isoformat()


def _severity_for_fail(default: str) -> str:
    return default


def _build_verdict(
    *,
    check_name: str,
    entity_type: str,
    entity_id: str,
    verdict: str,
    severity: str,
    details: Dict[str, Any],
    trace_id: Optional[str],
    checked_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    ts = checked_at or _utcnow()
    return {
        "check_name": check_name,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "verdict": verdict,
        "severity": severity,
        "details": details,
        "checked_at": _iso_utc(ts),
        "trace_id": trace_id,
    }


def check_payment_cache_integrity(
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
            return _build_verdict(
                check_name="IC-1",
                entity_type="order",
                entity_id=str(order_id),
                verdict="UNKNOWN",
                severity="WARNING",
                details={"reason": "order_not_found"},
                trace_id=trace_id,
            )

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
        is_ok = expected_status == actual_status

        return _build_verdict(
            check_name="IC-1",
            entity_type="order",
            entity_id=str(order_id),
            verdict="PASS" if is_ok else "FAIL",
            severity="INFO" if is_ok else "CRITICAL",
            details={
                "expected_status": expected_status,
                "actual_status": actual_status,
                "charges_minor": charges_minor,
                "refunds_minor": refunds_minor,
                "net_paid_minor": net_paid_minor,
                "order_total_minor": order_total_minor,
            },
            trace_id=trace_id,
        )
    finally:
        cursor.close()


def check_shipment_cache_integrity(
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
            return _build_verdict(
                check_name="IC-2",
                entity_type="order",
                entity_id=str(order_id),
                verdict="UNKNOWN",
                severity="WARNING",
                details={"reason": "order_not_found"},
                trace_id=trace_id,
            )
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

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM shipments
            WHERE order_id = %s
              AND carrier_code = 'cdek'
            """,
            (str(order_id),),
        )
        total_shipments = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM shipments
            WHERE order_id = %s
              AND carrier_code = 'cdek'
              AND current_status = 'cancelled'
            """,
            (str(order_id),),
        )
        cancelled_shipments = int(cursor.fetchone()[0])

        is_ok = actual_cdek_uuid == expected_cdek_uuid
        return _build_verdict(
            check_name="IC-2",
            entity_type="order",
            entity_id=str(order_id),
            verdict="PASS" if is_ok else "FAIL",
            severity="INFO" if is_ok else "WARNING",
            details={
                "expected_cdek_uuid": expected_cdek_uuid,
                "actual_cdek_uuid": actual_cdek_uuid,
                "shipment_count": total_shipments,
                "cancelled_count": cancelled_shipments,
            },
            trace_id=trace_id,
        )
    finally:
        cursor.close()


def check_stock_snapshot_integrity(
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
            return _build_verdict(
                check_name="IC-3",
                entity_type="stock",
                entity_id=f"{product_id}:{warehouse_code}",
                verdict="UNKNOWN",
                severity="WARNING",
                details={"reason": "snapshot_missing"},
                trace_id=trace_id,
            )
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

        is_ok = (
            snapshot_on_hand == expected_on_hand
            and snapshot_reserved == expected_reserved
            and snapshot_available == expected_available
        )
        return _build_verdict(
            check_name="IC-3",
            entity_type="stock",
            entity_id=f"{product_id}:{warehouse_code}",
            verdict="PASS" if is_ok else "FAIL",
            severity="INFO" if is_ok else "CRITICAL",
            details={
                "snapshot": {
                    "quantity_on_hand": snapshot_on_hand,
                    "quantity_reserved": snapshot_reserved,
                    "quantity_available": snapshot_available,
                },
                "expected": {
                    "quantity_on_hand": expected_on_hand,
                    "quantity_reserved": expected_reserved,
                    "quantity_available": expected_available,
                },
                "delta": {
                    "on_hand": snapshot_on_hand - expected_on_hand,
                    "reserved": snapshot_reserved - expected_reserved,
                    "available": snapshot_available - expected_available,
                },
            },
            trace_id=trace_id,
        )
    finally:
        cursor.close()


def check_reservation_line_item_consistency(
    db_conn,
    *,
    order_id: UUID,
    line_item_id: UUID,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT quantity, line_status
            FROM order_line_items
            WHERE id = %s
              AND order_id = %s
            LIMIT 1
            """,
            (str(line_item_id), str(order_id)),
        )
        row = cursor.fetchone()
        if not row:
            return _build_verdict(
                check_name="IC-4",
                entity_type="line_item",
                entity_id=str(line_item_id),
                verdict="UNKNOWN",
                severity="WARNING",
                details={"reason": "line_item_not_found"},
                trace_id=trace_id,
            )
        line_quantity = int(row[0])
        line_status = str(row[1])

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
        active_reservation_sum = int(cursor.fetchone()[0])

        is_ok = True
        if line_status == "reserved":
            is_ok = active_reservation_sum >= line_quantity
        elif line_status == "allocated":
            is_ok = active_reservation_sum > 0

        return _build_verdict(
            check_name="IC-4",
            entity_type="line_item",
            entity_id=str(line_item_id),
            verdict="PASS" if is_ok else "FAIL",
            severity="INFO" if is_ok else "CRITICAL",
            details={
                "line_status": line_status,
                "line_quantity": line_quantity,
                "active_reservation_sum": active_reservation_sum,
            },
            trace_id=trace_id,
        )
    finally:
        cursor.close()


def check_document_generation_key_consistency(
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
            return _build_verdict(
                check_name="IC-5",
                entity_type="order",
                entity_id=str(order_id),
                verdict="UNKNOWN",
                severity="WARNING",
                details={"reason": "order_not_found"},
                trace_id=trace_id,
            )
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
            return _build_verdict(
                check_name="IC-5",
                entity_type="order",
                entity_id=str(order_id),
                verdict="PASS",
                severity="INFO",
                details={"reason": "no_issued_invoice"},
                trace_id=trace_id,
            )

        doc_id = str(doc[0])
        doc_key = str(doc[1])
        doc_revision = int(doc[2])
        is_ok = (ledger_key == doc_key) and (ledger_revision == doc_revision)

        return _build_verdict(
            check_name="IC-5",
            entity_type="order",
            entity_id=str(order_id),
            verdict="PASS" if is_ok else "FAIL",
            severity="INFO" if is_ok else "WARNING",
            details={
                "document_id": doc_id,
                "ledger_key": ledger_key,
                "document_key": doc_key,
                "ledger_revision": ledger_revision,
                "document_revision": doc_revision,
            },
            trace_id=trace_id,
        )
    finally:
        cursor.close()


def check_document_provider_binding(
    db_conn,
    *,
    document_id: UUID,
    trace_id: Optional[str] = None,
    now_ts: Optional[datetime] = None,
) -> Dict[str, Any]:
    now_ts = now_ts or _utcnow()
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT status, provider_document_id, created_at
            FROM documents
            WHERE id = %s
            LIMIT 1
            """,
            (str(document_id),),
        )
        row = cursor.fetchone()
        if not row:
            return _build_verdict(
                check_name="IC-6",
                entity_type="document",
                entity_id=str(document_id),
                verdict="UNKNOWN",
                severity="WARNING",
                details={"reason": "document_not_found"},
                trace_id=trace_id,
                checked_at=now_ts,
            )
        status = str(row[0])
        provider_document_id = row[1]
        created_at = row[2]

        if status != "issued":
            return _build_verdict(
                check_name="IC-6",
                entity_type="document",
                entity_id=str(document_id),
                verdict="PASS",
                severity="INFO",
                details={"reason": "status_not_issued", "status": status},
                trace_id=trace_id,
                checked_at=now_ts,
            )

        age_minutes = int((now_ts - created_at).total_seconds() // 60) if created_at else 0
        if age_minutes <= 5:
            return _build_verdict(
                check_name="IC-6",
                entity_type="document",
                entity_id=str(document_id),
                verdict="PASS",
                severity="INFO",
                details={"status": status, "provider_document_id": provider_document_id, "age_minutes": age_minutes},
                trace_id=trace_id,
                checked_at=now_ts,
            )

        has_provider_binding = provider_document_id is not None
        if has_provider_binding:
            verdict = "PASS"
            severity = "INFO"
        else:
            verdict = "FAIL"
            severity = "CRITICAL" if age_minutes > 60 else "WARNING"

        return _build_verdict(
            check_name="IC-6",
            entity_type="document",
            entity_id=str(document_id),
            verdict=verdict,
            severity=severity,
            details={"status": status, "provider_document_id": provider_document_id, "age_minutes": age_minutes},
            trace_id=trace_id,
            checked_at=now_ts,
        )
    finally:
        cursor.close()


def check_fsm_staleness(
    db_conn,
    *,
    order_id: UUID,
    trace_id: Optional[str] = None,
    now_ts: Optional[datetime] = None,
) -> Dict[str, Any]:
    now_ts = now_ts or _utcnow()
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT state, status_changed_at
            FROM order_ledger
            WHERE order_id = %s
            LIMIT 1
            """,
            (str(order_id),),
        )
        row = cursor.fetchone()
        if not row:
            return _build_verdict(
                check_name="IC-7",
                entity_type="order",
                entity_id=str(order_id),
                verdict="UNKNOWN",
                severity="WARNING",
                details={"reason": "order_not_found"},
                trace_id=trace_id,
                checked_at=now_ts,
            )
        state = str(row[0] or "")
        status_changed_at = row[1]

        if state in TERMINAL_ORDER_STATES:
            return _build_verdict(
                check_name="IC-7",
                entity_type="order",
                entity_id=str(order_id),
                verdict="PASS",
                severity="INFO",
                details={"state": state, "reason": "terminal_state"},
                trace_id=trace_id,
                checked_at=now_ts,
            )

        threshold_minutes = FSM_STALENESS_MINUTES.get(state, 24 * 60)
        if status_changed_at is None:
            return _build_verdict(
                check_name="IC-7",
                entity_type="order",
                entity_id=str(order_id),
                verdict="STALE",
                severity="WARNING",
                details={"state": state, "reason": "status_changed_at_missing", "threshold_minutes": threshold_minutes},
                trace_id=trace_id,
                checked_at=now_ts,
            )

        age_minutes = int((now_ts - status_changed_at).total_seconds() // 60)
        if age_minutes <= threshold_minutes:
            return _build_verdict(
                check_name="IC-7",
                entity_type="order",
                entity_id=str(order_id),
                verdict="PASS",
                severity="INFO",
                details={"state": state, "age_minutes": age_minutes, "threshold_minutes": threshold_minutes},
                trace_id=trace_id,
                checked_at=now_ts,
            )

        severity = "CRITICAL" if age_minutes > (2 * threshold_minutes) else "WARNING"
        return _build_verdict(
            check_name="IC-7",
            entity_type="order",
            entity_id=str(order_id),
            verdict="STALE",
            severity=severity,
            details={"state": state, "age_minutes": age_minutes, "threshold_minutes": threshold_minutes},
            trace_id=trace_id,
            checked_at=now_ts,
        )
    finally:
        cursor.close()


def check_zombie_reservations(
    db_conn,
    *,
    trace_id: Optional[str] = None,
    now_ts: Optional[datetime] = None,
    sample_limit: int = 20,
) -> Dict[str, Any]:
    now_ts = now_ts or _utcnow()
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, order_id, expires_at
            FROM reservations
            WHERE status = 'active'
              AND expires_at IS NOT NULL
              AND expires_at < %s
            ORDER BY expires_at ASC
            LIMIT %s
            """,
            (now_ts, sample_limit),
        )
        rows = cursor.fetchall()
        sample = [
            {
                "reservation_id": str(r[0]),
                "order_id": str(r[1]),
                "expires_at": r[2].isoformat() if r[2] else None,
                "age_past_expiry_minutes": int((now_ts - r[2]).total_seconds() // 60) if r[2] else None,
            }
            for r in rows
        ]

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM reservations
            WHERE status = 'active'
              AND expires_at IS NOT NULL
              AND expires_at < %s
            """,
            (now_ts,),
        )
        total_count = int(cursor.fetchone()[0])
        is_ok = total_count == 0
        return _build_verdict(
            check_name="IC-8",
            entity_type="reservation",
            entity_id="global",
            verdict="PASS" if is_ok else "FAIL",
            severity="INFO" if is_ok else "WARNING",
            details={"count": total_count, "sample": sample},
            trace_id=trace_id,
            checked_at=now_ts,
        )
    finally:
        cursor.close()


def check_orphan_payment_transactions(
    db_conn,
    *,
    trace_id: Optional[str] = None,
    now_ts: Optional[datetime] = None,
    sample_limit: int = 20,
) -> Dict[str, Any]:
    now_ts = now_ts or _utcnow()
    stale_at = now_ts - timedelta(minutes=15)
    critical_at = now_ts - timedelta(minutes=60)
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, order_id, provider_code, provider_transaction_id, created_at
            FROM payment_transactions
            WHERE status = 'pending'
              AND created_at < %s
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (stale_at, sample_limit),
        )
        rows = cursor.fetchall()
        sample = []
        has_critical_age = False
        for row in rows:
            age_minutes = int((now_ts - row[4]).total_seconds() // 60)
            if row[4] < critical_at:
                has_critical_age = True
            sample.append(
                {
                    "transaction_id": str(row[0]),
                    "order_id": str(row[1]),
                    "provider_code": str(row[2]),
                    "provider_transaction_id": str(row[3]),
                    "age_minutes": age_minutes,
                }
            )

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM payment_transactions
            WHERE status = 'pending'
              AND created_at < %s
            """,
            (stale_at,),
        )
        total_count = int(cursor.fetchone()[0])
        if total_count == 0:
            verdict = "PASS"
            severity = "INFO"
        else:
            verdict = "STALE"
            severity = "CRITICAL" if has_critical_age else "WARNING"
        return _build_verdict(
            check_name="IC-9",
            entity_type="payment_transaction",
            entity_id="global",
            verdict=verdict,
            severity=severity,
            details={"count": total_count, "sample": sample},
            trace_id=trace_id,
            checked_at=now_ts,
        )
    finally:
        cursor.close()


def collect_order_invariant_verdicts(
    db_conn,
    *,
    order_id: UUID,
    trace_id: Optional[str] = None,
    now_ts: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    now_ts = now_ts or _utcnow()
    verdicts = [
        check_payment_cache_integrity(db_conn, order_id=order_id, trace_id=trace_id),
        check_shipment_cache_integrity(db_conn, order_id=order_id, trace_id=trace_id),
        check_document_generation_key_consistency(db_conn, order_id=order_id, trace_id=trace_id),
        check_fsm_staleness(db_conn, order_id=order_id, trace_id=trace_id, now_ts=now_ts),
    ]

    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id
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
    finally:
        cursor.close()

    if doc_row:
        verdicts.append(
            check_document_provider_binding(
                db_conn,
                document_id=UUID(str(doc_row[0])),
                trace_id=trace_id,
                now_ts=now_ts,
            )
        )
    return verdicts


def classify_order_health(
    db_conn,
    *,
    order_id: UUID,
    trace_id: Optional[str] = None,
    now_ts: Optional[datetime] = None,
    reconciliation_failed: bool = False,
) -> Dict[str, Any]:
    now_ts = now_ts or _utcnow()
    verdicts = collect_order_invariant_verdicts(
        db_conn,
        order_id=order_id,
        trace_id=trace_id,
        now_ts=now_ts,
    )

    has_fail = any(v["verdict"] == "FAIL" for v in verdicts)
    has_stale = any(v["verdict"] == "STALE" for v in verdicts)

    if has_fail and reconciliation_failed:
        health = "REQUIRES_MANUAL"
    elif has_fail:
        health = "INCONSISTENT"
    else:
        stale_checks = {v["check_name"]: v for v in verdicts if v["verdict"] == "STALE"}
        if "IC-7" in stale_checks:
            health = "STUCK"
        elif "IC-6" in stale_checks:
            health = "AWAITING_EXTERNAL"
        else:
            cursor = db_conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT state, status_changed_at
                    FROM order_ledger
                    WHERE order_id = %s
                    LIMIT 1
                    """,
                    (str(order_id),),
                )
                row = cursor.fetchone()
            finally:
                cursor.close()
            if row and str(row[0] or "") in TERMINAL_ORDER_STATES:
                health = "HEALTHY"
            else:
                health = "PROGRESSING"

    return {
        "order_id": str(order_id),
        "health": health,
        "priority_order": list(HEALTH_PRIORITY),
        "verdicts": verdicts,
        "checked_at": _iso_utc(now_ts),
        "trace_id": trace_id,
    }


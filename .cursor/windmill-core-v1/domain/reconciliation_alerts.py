from __future__ import annotations

import json
from typing import Any, Dict, Optional


def emit_alert(
    db_conn,
    *,
    sweep_trace_id: str,
    check_code: str,
    entity_type: str,
    entity_id: str,
    severity: str,
    verdict_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """
    L3 alert emission: idempotent via UNIQUE(notification_key).
    Writes only to reconciliation_alerts.
    """
    notification_key = f"{check_code}:{entity_id}"
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO reconciliation_alerts (
                sweep_trace_id,
                check_code,
                entity_type,
                entity_id,
                severity,
                verdict_snapshot,
                notification_key
            )
            VALUES (%s::uuid, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (notification_key) DO NOTHING
            RETURNING id
            """,
            (
                str(sweep_trace_id),
                str(check_code),
                str(entity_type),
                str(entity_id),
                str(severity),
                json.dumps(verdict_snapshot, ensure_ascii=False),
                str(notification_key),
            ),
        )
        row = cursor.fetchone()
        if row:
            return {"action": "created", "alert_id": str(row[0]), "notification_key": notification_key}
        return {"action": "duplicate", "notification_key": notification_key}
    finally:
        cursor.close()


def emit_batch_alert(
    db_conn,
    *,
    sweep_trace_id: str,
    check_code: str,
    severity: str,
    sample: list[Dict[str, Any]],
    total_count: int,
) -> Dict[str, Any]:
    entity_id = f"batch:{check_code}:{sweep_trace_id}"
    verdict_snapshot = {"check_code": check_code, "total_count": int(total_count), "sample": sample}
    return emit_alert(
        db_conn,
        sweep_trace_id=sweep_trace_id,
        check_code=check_code,
        entity_type="batch",
        entity_id=entity_id,
        severity=severity,
        verdict_snapshot=verdict_snapshot,
    )


def ack_alert(db_conn, *, alert_id: str) -> Dict[str, Any]:
    """
    Acknowledge an alert row (operational helper). Writes only to reconciliation_alerts.
    """
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE reconciliation_alerts
            SET notification_state = 'acked',
                acked_at = NOW()
            WHERE id = %s::uuid
              AND notification_state <> 'acked'
            """,
            (str(alert_id),),
        )
        updated = bool(getattr(cursor, "rowcount", 0))
        return {"updated": updated}
    finally:
        cursor.close()


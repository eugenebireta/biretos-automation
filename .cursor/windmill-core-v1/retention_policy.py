from __future__ import annotations

import os
from typing import Any, Dict

from ru_worker.lib_integrations import log_event


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _delete_audit_log_batch(audit_conn, *, batch_size: int) -> int:
    cursor = audit_conn.cursor()
    try:
        cursor.execute(
            """
            WITH batch AS (
                SELECT id
                FROM reconciliation_audit_log
                WHERE created_at < (NOW() - INTERVAL '30 days')
                ORDER BY created_at ASC
                LIMIT %s
            )
            DELETE FROM reconciliation_audit_log
            WHERE id IN (SELECT id FROM batch)
            """,
            (int(batch_size),),
        )
        return int(getattr(cursor, "rowcount", 0) or 0)
    finally:
        cursor.close()


def _delete_alerts_batch(audit_conn, *, batch_size: int) -> int:
    cursor = audit_conn.cursor()
    try:
        cursor.execute(
            """
            WITH batch AS (
                SELECT id
                FROM reconciliation_alerts
                WHERE notification_state IN ('sent', 'acked')
                  AND created_at < (NOW() - INTERVAL '90 days')
                ORDER BY created_at ASC
                LIMIT %s
            )
            DELETE FROM reconciliation_alerts
            WHERE id IN (SELECT id FROM batch)
            """,
            (int(batch_size),),
        )
        return int(getattr(cursor, "rowcount", 0) or 0)
    finally:
        cursor.close()


def _delete_suppressions_batch(audit_conn, *, batch_size: int) -> int:
    cursor = audit_conn.cursor()
    try:
        cursor.execute(
            """
            WITH batch AS (
                SELECT id
                FROM reconciliation_suppressions
                WHERE suppression_state = 'expired'
                  AND expires_at IS NOT NULL
                  AND expires_at < (NOW() - INTERVAL '30 days')
                ORDER BY expires_at ASC
                LIMIT %s
            )
            DELETE FROM reconciliation_suppressions
            WHERE id IN (SELECT id FROM batch)
            """,
            (int(batch_size),),
        )
        deleted = int(getattr(cursor, "rowcount", 0) or 0)
        if deleted > 0:
            return deleted

        cursor.execute(
            """
            WITH batch AS (
                SELECT id
                FROM reconciliation_suppressions
                WHERE suppression_state = 'expired'
                  AND expires_at IS NULL
                  AND created_at < (NOW() - INTERVAL '30 days')
                ORDER BY created_at ASC
                LIMIT %s
            )
            DELETE FROM reconciliation_suppressions
            WHERE id IN (SELECT id FROM batch)
            """,
            (int(batch_size),),
        )
        return int(getattr(cursor, "rowcount", 0) or 0)
    finally:
        cursor.close()


def run_retention_cleanup(audit_conn, *, trace_id: str) -> Dict[str, Any]:
    """
    Retention Policy (Option A):
      - audit_log: 30d TTL by created_at
      - alerts: 90d TTL by created_at for sent/acked only
      - suppressions: 30d after formal expiration (suppression_state='expired')

    Constraints:
      - audit_conn only (autocommit=True)
      - batched deletes via CTE (PostgreSQL has no DELETE...LIMIT)
      - hardcoded literals in SQL for partial index stability
    """
    batch_size = _env_int("RETENTION_BATCH_SIZE", 1000)
    max_batches = _env_int("RETENTION_MAX_BATCHES", 10)

    audit_log_deleted = 0
    alerts_deleted = 0
    suppressions_deleted = 0
    batches_run = 0

    for _ in range(int(max_batches)):
        batches_run += 1
        deleted_any = False

        try:
            n = _delete_audit_log_batch(audit_conn, batch_size=batch_size)
            audit_log_deleted += int(n)
            deleted_any = deleted_any or (n > 0)
        except Exception as exc:
            log_event("retention_cleanup_table_error", {"table": "reconciliation_audit_log", "error": str(exc), "trace_id": trace_id})

        try:
            n = _delete_alerts_batch(audit_conn, batch_size=batch_size)
            alerts_deleted += int(n)
            deleted_any = deleted_any or (n > 0)
        except Exception as exc:
            log_event("retention_cleanup_table_error", {"table": "reconciliation_alerts", "error": str(exc), "trace_id": trace_id})

        try:
            n = _delete_suppressions_batch(audit_conn, batch_size=batch_size)
            suppressions_deleted += int(n)
            deleted_any = deleted_any or (n > 0)
        except Exception as exc:
            log_event(
                "retention_cleanup_table_error",
                {"table": "reconciliation_suppressions", "error": str(exc), "trace_id": trace_id},
            )

        if not deleted_any:
            break

    summary = {
        "trace_id": str(trace_id),
        "batch_size": int(batch_size),
        "max_batches": int(max_batches),
        "batches_run": int(batches_run),
        "audit_log_deleted": int(audit_log_deleted),
        "alerts_deleted": int(alerts_deleted),
        "suppressions_deleted": int(suppressions_deleted),
    }
    log_event("retention_cleanup", summary)
    return summary


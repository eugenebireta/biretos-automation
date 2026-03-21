"""
NLU SLA Tracker — Phase 7.8.

Appends one row to nlu_sla_log per NLU parse attempt.
Fire-and-forget: DB errors are swallowed so SLA tracking never
breaks the main request flow.

Table: nlu_sla_log (migration 029).
Retention: 90 days (managed externally by pg_cron or similar).
"""
from __future__ import annotations

from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# record_nlu_sla
# ---------------------------------------------------------------------------


def record_nlu_sla(
    db_conn: Any,
    *,
    trace_id: str,
    employee_id: str,
    intent_type: Optional[str],
    model_version: str,
    prompt_version: str,
    degradation_level: int,
    parse_duration_ms: int,
    total_duration_ms: int,
    status: str,
) -> None:
    """
    Append one SLA record to nlu_sla_log.

    status should be one of:
      ok / fallback / failed / shadow / button_only / injection_rejected

    Fire-and-forget: any DB exception is silently swallowed.
    """
    try:
        cur = db_conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO nlu_sla_log
                    (trace_id, employee_id, intent_type,
                     model_version, prompt_version,
                     degradation_level,
                     parse_duration_ms, total_duration_ms,
                     status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    trace_id,
                    employee_id,
                    intent_type,
                    model_version,
                    prompt_version,
                    degradation_level,
                    parse_duration_ms,
                    total_duration_ms,
                    status,
                ),
            )
        finally:
            cur.close()
    except Exception:
        # SLA tracking must never fail the main flow
        pass


# ---------------------------------------------------------------------------
# get_sla_stats  (for monitoring / alerting)
# ---------------------------------------------------------------------------


def get_sla_stats(db_conn: Any, *, hours: int = 1) -> Dict[str, Any]:
    """
    Return P50 / P95 / P99 parse_duration_ms and success rate
    from nlu_sla_log for the last N hours.

    Returns dict:
      total: int
      ok_count: int
      success_rate: float  (0.0–1.0)
      p50_ms / p95_ms / p99_ms: int
      by_status: {status: count}
    """
    try:
        cur = db_conn.cursor()
        try:
            cur.execute(
                """
                SELECT
                    COUNT(*)                                      AS total,
                    SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) AS ok_count,
                    PERCENTILE_CONT(0.50) WITHIN GROUP
                        (ORDER BY parse_duration_ms)              AS p50,
                    PERCENTILE_CONT(0.95) WITHIN GROUP
                        (ORDER BY parse_duration_ms)              AS p95,
                    PERCENTILE_CONT(0.99) WITHIN GROUP
                        (ORDER BY parse_duration_ms)              AS p99
                FROM nlu_sla_log
                WHERE created_at >= NOW() - INTERVAL '%s hours'
                """,
                (hours,),
            )
            row = cur.fetchone()
            total    = int(row[0] or 0) if row else 0
            ok_count = int(row[1] or 0) if row else 0
            p50      = int(row[2] or 0) if row else 0
            p95      = int(row[3] or 0) if row else 0
            p99      = int(row[4] or 0) if row else 0

            cur.execute(
                """
                SELECT status, COUNT(*) AS cnt
                FROM nlu_sla_log
                WHERE created_at >= NOW() - INTERVAL '%s hours'
                GROUP BY status
                ORDER BY cnt DESC
                """,
                (hours,),
            )
            status_rows = cur.fetchall()
        finally:
            cur.close()

        by_status = {r[0]: int(r[1]) for r in (status_rows or [])}
        success_rate = round(ok_count / total, 4) if total > 0 else 0.0

        return {
            "total": total,
            "ok_count": ok_count,
            "success_rate": success_rate,
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "by_status": by_status,
            "hours": hours,
        }
    except Exception as exc:
        return {
            "error": str(exc),
            "total": 0,
            "ok_count": 0,
            "success_rate": 0.0,
            "p50_ms": 0,
            "p95_ms": 0,
            "p99_ms": 0,
        }

"""
NLU Shadow Log — Phase 7.7.

During shadow mode (config.shadow_mode=True) NLU parses the message
but does NOT execute.  Results are written here for later analysis.

Table: shadow_rag_log (assumed to exist or ignored gracefully).
Fire-and-forget: errors are logged but never propagate.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# write_nlu_shadow_entry
# ---------------------------------------------------------------------------


def write_nlu_shadow_entry(
    db_conn: Any,
    *,
    trace_id: str,
    employee_id: str,
    raw_text_hash: str,
    intent_type: Optional[str],
    entities: Dict[str, str],
    confidence: float,
    model_version: str,
    prompt_version: str,
    parse_duration_ms: int,
) -> None:
    """
    Append one shadow-mode parse result to shadow_rag_log.

    Fire-and-forget: any DB error is silently swallowed (shadow mode
    must not break the main request flow).

    Args:
        db_conn: open psycopg2 connection.
        trace_id: from original update.
        employee_id: Telegram user_id as string.
        raw_text_hash: 12-char hash prefix from ParsedIntent.
        intent_type: recognized intent or None.
        entities: extracted entities dict.
        confidence: parse confidence 0.0–1.0.
        model_version / prompt_version: versioning metadata.
        parse_duration_ms: wall-clock parse time.
    """
    try:
        cur = db_conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO shadow_rag_log
                    (trace_id, employee_id, raw_text_hash,
                     intent_type, entities, confidence,
                     model_version, prompt_version,
                     parse_duration_ms, created_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, NOW())
                ON CONFLICT DO NOTHING
                """,
                (
                    trace_id,
                    employee_id,
                    raw_text_hash,
                    intent_type,
                    json.dumps(entities),
                    confidence,
                    model_version,
                    prompt_version,
                    parse_duration_ms,
                ),
            )
        finally:
            cur.close()
    except Exception:
        # Shadow log must never fail the main flow
        pass


# ---------------------------------------------------------------------------
# get_shadow_stats  (for monitoring / manual review)
# ---------------------------------------------------------------------------


def get_shadow_stats(db_conn: Any, *, hours: int = 24) -> Dict[str, Any]:
    """
    Return basic stats from shadow_rag_log for the last N hours.

    Returns a dict:
      total: int
      by_intent: {intent_type: count}
      avg_confidence: float
      avg_parse_ms: float
    """
    try:
        cur = db_conn.cursor()
        try:
            cur.execute(
                """
                SELECT
                    COUNT(*)                          AS total,
                    AVG(confidence)                   AS avg_confidence,
                    AVG(parse_duration_ms)            AS avg_parse_ms
                FROM shadow_rag_log
                WHERE created_at >= NOW() - INTERVAL '%s hours'
                """,
                (hours,),
            )
            row = cur.fetchone()
            total = int(row[0] or 0) if row else 0
            avg_conf = float(row[1] or 0.0) if row else 0.0
            avg_ms = float(row[2] or 0.0) if row else 0.0

            cur.execute(
                """
                SELECT intent_type, COUNT(*) AS cnt
                FROM shadow_rag_log
                WHERE created_at >= NOW() - INTERVAL '%s hours'
                GROUP BY intent_type
                ORDER BY cnt DESC
                """,
                (hours,),
            )
            rows = cur.fetchall()
        finally:
            cur.close()

        by_intent = {r[0] if r[0] else "unknown": int(r[1]) for r in (rows or [])}
        return {
            "total": total,
            "by_intent": by_intent,
            "avg_confidence": round(avg_conf, 4),
            "avg_parse_ms": round(avg_ms, 1),
            "hours": hours,
        }
    except Exception as exc:
        return {"error": str(exc), "total": 0, "by_intent": {}}

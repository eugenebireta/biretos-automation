"""
Backoffice Shadow Logger for RAG. Phase 6.9.

Captures full employee intent context for future AI assistant training.
Fire-and-forget: exceptions are logged but never re-raised.
No commit here — caller owns transaction boundary.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


def write_shadow_rag_entry(
    db_conn: Any,
    *,
    trace_id: str,
    employee_id: str,
    intent_type: str,
    context_json: Dict[str, Any],
    response_summary: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Insert one shadow RAG log row.

    Fire-and-forget: any DB error returns {"action": "error", "error": ...}
    without raising. The caller must not depend on this succeeding.

    context_json should include:
      intent payload, snapshot data, rate window, outcome.
    """
    try:
        cursor = db_conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO shadow_rag_log (
                    trace_id,
                    employee_id,
                    intent_type,
                    context_json,
                    response_summary
                )
                VALUES (
                    %s::uuid,
                    %s,
                    %s,
                    %s::jsonb,
                    %s
                )
                """,
                (
                    str(trace_id),
                    str(employee_id),
                    str(intent_type),
                    json.dumps(context_json, ensure_ascii=False),
                    response_summary,
                ),
            )
            return {"action": "created"}
        finally:
            cursor.close()
    except Exception as exc:
        # Fire-and-forget: structured error log, no re-raise
        return {
            "action": "error",
            "error_class": "TRANSIENT",
            "severity": "WARNING",
            "retriable": True,
            "error": str(exc),
        }

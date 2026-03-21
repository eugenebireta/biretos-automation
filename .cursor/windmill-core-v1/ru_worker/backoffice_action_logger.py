"""
Backoffice Action Logger. Phase 6.3.

Writes one row per employee backoffice action to employee_actions_log.
Idempotent via UNIQUE(idempotency_key).
No commit here — caller owns transaction boundary.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


def write_employee_action(
    db_conn: Any,
    *,
    trace_id: str,
    idempotency_key: str,
    employee_id: str,
    employee_role: str,
    intent_type: str,
    risk_level: str,
    payload_snapshot: Dict[str, Any],
    context_snapshot: Dict[str, Any],
    outcome: Optional[str] = None,
    outcome_detail: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Insert one employee action log row idempotently.

    Returns:
        {"action": "created", "idempotency_key": ...}
        {"action": "duplicate", "idempotency_key": ...}
    """
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO employee_actions_log (
                trace_id,
                idempotency_key,
                employee_id,
                employee_role,
                intent_type,
                risk_level,
                payload_snapshot,
                context_snapshot,
                outcome,
                outcome_detail
            )
            VALUES (
                %s::uuid,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s::jsonb,
                %s::jsonb,
                %s,
                %s::jsonb
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (
                str(trace_id),
                str(idempotency_key),
                str(employee_id),
                str(employee_role),
                str(intent_type),
                str(risk_level),
                json.dumps(payload_snapshot, ensure_ascii=False),
                json.dumps(context_snapshot, ensure_ascii=False),
                outcome,
                json.dumps(outcome_detail, ensure_ascii=False) if outcome_detail else None,
            ),
        )
        row = cursor.fetchone()
        if row:
            return {"action": "created", "idempotency_key": idempotency_key}
        return {"action": "duplicate", "idempotency_key": idempotency_key}
    finally:
        cursor.close()

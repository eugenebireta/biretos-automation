"""
NLU Confirmation Store — Phase 7.5.

Persists and atomically consumes pending NLU confirmations in the DB.
Table: nlu_pending_confirmations (migration 029).

Key invariant: INV-MBC — every NLU intent must be confirmed by a human
before execution.  get_and_consume() uses atomic UPDATE ... RETURNING
to prevent double-execution.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from domain.assistant_models import ConfirmationPending
from domain.nlu_models import ParsedIntent


# ---------------------------------------------------------------------------
# store_confirmation
# ---------------------------------------------------------------------------


def store_confirmation(
    db_conn: Any,
    trace_id: str,
    employee_id: str,
    employee_role: str,
    parsed: ParsedIntent,
) -> str:
    """
    Persist a pending NLU confirmation row.

    Returns the UUID of the newly created row (confirmation_id).

    Args:
        db_conn: open psycopg2 connection.
        trace_id: from original Telegram update.
        employee_id: Telegram user_id as string.
        employee_role: e.g. "operator" / "manager".
        parsed: ParsedIntent from parse_intent().
    """
    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO nlu_pending_confirmations
                (trace_id, employee_id, employee_role,
                 parsed_intent_type, parsed_entities,
                 model_version, prompt_version, confidence)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            RETURNING id
            """,
            (
                trace_id,
                employee_id,
                employee_role,
                parsed.intent_type,
                json.dumps(parsed.entities),
                parsed.model_version,
                parsed.prompt_version,
                parsed.confidence,
            ),
        )
        row = cur.fetchone()
    finally:
        cur.close()

    if not row:
        raise RuntimeError(
            f"nlu_confirmation_store: INSERT RETURNING returned no row "
            f"(trace_id={trace_id})"
        )
    return str(row[0])


# ---------------------------------------------------------------------------
# get_and_consume
# ---------------------------------------------------------------------------


def get_and_consume(
    db_conn: Any,
    confirmation_id: str,
) -> Optional[ConfirmationPending]:
    """
    Atomically consume a pending confirmation.

    Uses UPDATE ... WHERE status='pending' AND expires_at > NOW() RETURNING *
    so that concurrent calls cannot both consume the same row.

    Returns ConfirmationPending if found-and-consumed, None if already
    consumed / expired / cancelled.

    The caller MUST commit after processing the result.
    """
    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            UPDATE nlu_pending_confirmations
            SET    status = 'confirmed'
            WHERE  id = %s
              AND  status = 'pending'
              AND  expires_at > NOW()
            RETURNING
                id, trace_id, employee_id, employee_role,
                parsed_intent_type, parsed_entities,
                model_version, prompt_version, confidence
            """,
            (confirmation_id,),
        )
        row = cur.fetchone()
    finally:
        cur.close()

    if not row:
        return None

    (
        row_id, trace_id, employee_id, employee_role,
        intent_type, entities_raw,
        model_version, prompt_version, confidence,
    ) = row

    if isinstance(entities_raw, str):
        entities = json.loads(entities_raw)
    else:
        entities = dict(entities_raw) if entities_raw else {}

    return ConfirmationPending(
        confirmation_id=str(row_id),
        trace_id=trace_id,
        employee_id=employee_id,
        employee_role=employee_role,
        parsed_intent_type=intent_type,
        parsed_entities=entities,
        model_version=model_version,
        prompt_version=prompt_version,
        confidence=float(confidence) if confidence is not None else 0.0,
    )


# ---------------------------------------------------------------------------
# expire_stale
# ---------------------------------------------------------------------------


def expire_stale(db_conn: Any) -> int:
    """
    Mark all pending confirmations past their TTL as 'expired'.

    Returns the number of rows updated.
    Safe to call periodically (e.g. from a maintenance job).
    """
    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            UPDATE nlu_pending_confirmations
            SET    status = 'expired'
            WHERE  status = 'pending'
              AND  expires_at <= NOW()
            """,
        )
        count = cur.rowcount
    finally:
        cur.close()
    return count

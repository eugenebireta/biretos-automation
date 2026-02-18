from __future__ import annotations

import json
from typing import Any, Dict, Optional


def _idempotency_key(*, trace_id: str, gate_name: str, original_decision_seq: int) -> str:
    return f"review:{trace_id}:{gate_name}:{int(original_decision_seq)}"


def create_review_case(
    db_conn,
    *,
    trace_id: str,
    order_id: Optional[str],
    gate_name: str,
    original_verdict: str,
    original_decision_seq: int,
    policy_hash: str,
    action_snapshot: Dict[str, Any],
    resume_context: Optional[Dict[str, Any]] = None,
    sla_deadline_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a review_case row idempotently.

    Contract:
      - Idempotency is enforced by UNIQUE(review_cases.idempotency_key).
      - No commit/rollback here; caller owns transaction boundaries.
      - Returns {"case_id": ..., "status": ..., "created": True/False}.
    """
    key = _idempotency_key(trace_id=trace_id, gate_name=gate_name, original_decision_seq=original_decision_seq)
    if not isinstance(action_snapshot, dict):
        raise ValueError("action_snapshot must be a dict")
    if resume_context is not None and not isinstance(resume_context, dict):
        raise ValueError("resume_context must be a dict or None")

    resume_json = json.dumps(resume_context, ensure_ascii=False) if resume_context is not None else None

    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO review_cases (
                id,
                trace_id,
                order_id,
                gate_name,
                original_verdict,
                original_decision_seq,
                policy_hash,
                action_snapshot,
                resume_context,
                status,
                sla_deadline_at,
                escalation_level,
                idempotency_key,
                created_at,
                updated_at
            )
            VALUES (
                gen_random_uuid(),
                %s::uuid,
                %s::uuid,
                %s,
                %s,
                %s,
                %s,
                %s::jsonb,
                %s::jsonb,
                'open',
                %s,
                0,
                %s,
                NOW(),
                NOW()
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, status
            """,
            (
                trace_id,
                order_id,
                gate_name,
                original_verdict,
                int(original_decision_seq),
                policy_hash,
                json.dumps(action_snapshot, ensure_ascii=False),
                resume_json,
                sla_deadline_at,
                key,
            ),
        )
        row = cursor.fetchone()
        if row:
            return {"case_id": str(row[0]), "status": str(row[1]), "created": True}
    finally:
        cursor.close()

    cursor2 = db_conn.cursor()
    try:
        cursor2.execute(
            "SELECT id, status FROM review_cases WHERE idempotency_key = %s",
            (key,),
        )
        row2 = cursor2.fetchone()
        if not row2:
            # Should not happen unless the INSERT failed silently; fail fast.
            raise RuntimeError("Idempotent insert conflict but existing review_case row not found")
        return {"case_id": str(row2[0]), "status": str(row2[1]), "created": False}
    finally:
        cursor2.close()


def assign_case(
    db_conn,
    *,
    case_id: str,
    assigned_to: str,
) -> Dict[str, Any]:
    """
    Transition: open -> assigned only.

    No commit/rollback here; caller owns transaction boundaries.
    """
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE review_cases
            SET status = 'assigned',
                assigned_to = %s,
                assigned_at = NOW(),
                updated_at = NOW()
            WHERE id = %s::uuid
              AND status = 'open'
            """,
            (assigned_to, case_id),
        )
        return {"updated": bool(getattr(cursor, "rowcount", 0))}
    finally:
        cursor.close()


def resolve_case(
    db_conn,
    *,
    case_id: str,
    status: str,
    resolved_by: str,
    resolution_decision_seq: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Transition to a terminal status.

    Allowed source states: open, assigned, approved.
    No commit/rollback here; caller owns transaction boundaries.
    """
    terminal_statuses = {"executed", "rejected", "expired", "cancelled"}
    if status not in terminal_statuses:
        raise ValueError(f"resolve_case status must be terminal: {sorted(terminal_statuses)}")

    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE review_cases
            SET status = %s,
                resolved_at = NOW(),
                resolved_by = %s,
                resolution_decision_seq = %s,
                updated_at = NOW()
            WHERE id = %s::uuid
              AND status IN ('open', 'assigned', 'approved')
            """,
            (status, resolved_by, resolution_decision_seq, case_id),
        )
        return {"updated": bool(getattr(cursor, "rowcount", 0))}
    finally:
        cursor.close()


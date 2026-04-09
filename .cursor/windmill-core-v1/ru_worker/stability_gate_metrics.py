from __future__ import annotations

import json
from typing import Any, Dict, Optional

from config import get_config

MANUAL_INTERVENTION = "manual_intervention"
CLOSED_CYCLE_COUNTER = "closed_cycle_counter"
ESCALATION_TRACKING = "escalation_tracking"

_DEFAULT_POLICY_HASH = "stability-gate-day2-v1"


def _schema_version() -> str:
    try:
        cfg = get_config()
    except BaseException:
        return "v3"
    value = getattr(cfg, "gate_chain_version", None)
    if value is None or str(value).strip() == "":
        return "v3"
    return str(value)


def _next_decision_seq(db_conn: Any, trace_id: str) -> int:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT COALESCE(MAX(decision_seq), 0) + 1
            FROM control_decisions
            WHERE trace_id = %s::uuid
            """,
            (trace_id,),
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 1
    finally:
        cursor.close()


def _insert_metric(
    db_conn: Any,
    *,
    trace_id: str,
    gate_name: str,
    verdict: str,
    policy_hash: str,
    decision_context: Dict[str, Any],
) -> int:
    decision_seq = _next_decision_seq(db_conn, trace_id)
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO control_decisions (
                trace_id,
                decision_seq,
                gate_name,
                verdict,
                schema_version,
                policy_hash,
                decision_context,
                reference_snapshot,
                replay_config_status
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
                %s
            )
            """,
            (
                trace_id,
                decision_seq,
                gate_name,
                verdict,
                _schema_version(),
                policy_hash,
                json.dumps(decision_context, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
                None,
            ),
        )
    finally:
        cursor.close()
    return decision_seq


def record_manual_intervention(
    db_conn: Any,
    *,
    trace_id: str,
    intent_type: str,
    reason: str,
    employee_id: Optional[str] = None,
    employee_role: Optional[str] = None,
    policy_hash: str = _DEFAULT_POLICY_HASH,
    extra: Optional[Dict[str, Any]] = None,
) -> int:
    context: Dict[str, Any] = {
        "intent_type": intent_type,
        "reason": reason,
    }
    if employee_id:
        context["employee_id"] = employee_id
    if employee_role:
        context["employee_role"] = employee_role
    if extra:
        context.update(extra)
    return _insert_metric(
        db_conn,
        trace_id=trace_id,
        gate_name=MANUAL_INTERVENTION,
        verdict="REQUIRED",
        policy_hash=policy_hash,
        decision_context=context,
    )


def record_closed_cycle(
    db_conn: Any,
    *,
    trace_id: str,
    intent_type: str,
    employee_id: Optional[str] = None,
    policy_hash: str = _DEFAULT_POLICY_HASH,
    extra: Optional[Dict[str, Any]] = None,
) -> int:
    context: Dict[str, Any] = {
        "intent_type": intent_type,
    }
    if employee_id:
        context["employee_id"] = employee_id
    if extra:
        context.update(extra)
    return _insert_metric(
        db_conn,
        trace_id=trace_id,
        gate_name=CLOSED_CYCLE_COUNTER,
        verdict="CLOSED",
        policy_hash=policy_hash,
        decision_context=context,
    )


def record_escalation(
    db_conn: Any,
    *,
    trace_id: str,
    intent_type: str,
    reason: str,
    escalation_level: int = 1,
    employee_id: Optional[str] = None,
    policy_hash: str = _DEFAULT_POLICY_HASH,
    extra: Optional[Dict[str, Any]] = None,
) -> int:
    context: Dict[str, Any] = {
        "intent_type": intent_type,
        "reason": reason,
        "escalation_level": int(escalation_level),
    }
    if employee_id:
        context["employee_id"] = employee_id
    if extra:
        context.update(extra)
    return _insert_metric(
        db_conn,
        trace_id=trace_id,
        gate_name=ESCALATION_TRACKING,
        verdict="ESCALATED",
        policy_hash=policy_hash,
        decision_context=context,
    )


def get_metric_counts(db_conn: Any, *, hours: int = 24) -> Dict[str, Any]:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT gate_name, COUNT(*)
            FROM control_decisions
            WHERE gate_name IN (%s, %s, %s)
              AND created_at >= NOW() - INTERVAL '1 second' * %s
            GROUP BY gate_name
            """,
            (
                MANUAL_INTERVENTION,
                CLOSED_CYCLE_COUNTER,
                ESCALATION_TRACKING,
                int(hours) * 3600,
            ),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()

    counts = {
        MANUAL_INTERVENTION: 0,
        CLOSED_CYCLE_COUNTER: 0,
        ESCALATION_TRACKING: 0,
    }
    for gate_name, count in rows:
        counts[str(gate_name)] = int(count)
    return counts

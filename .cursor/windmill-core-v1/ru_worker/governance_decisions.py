from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from config import get_config

HUMAN_APPROVE = "HUMAN_APPROVE"
HUMAN_REJECT = "HUMAN_REJECT"
HUMAN_APPROVE_WITH_CORRECTION = "HUMAN_APPROVE_WITH_CORRECTION"

_GATE_NAME = "human_override"


def _require_live_execution(execution_mode: Optional[str]) -> str:
    """
    Phase 1 contract: this module is LIVE-only and must not be used in REPLAY.
    """
    if execution_mode is None:
        cfg = get_config()
        execution_mode = getattr(cfg, "execution_mode", None) or "LIVE"
    mode = str(execution_mode).strip().upper()
    if mode == "REPLAY":
        raise RuntimeError("governance_decisions is LIVE-only in Phase 1 (execution_mode=REPLAY is forbidden)")
    return mode


def _schema_version(schema_version: Optional[str]) -> str:
    if schema_version is not None and str(schema_version).strip() != "":
        return str(schema_version)
    cfg = get_config()
    return str(getattr(cfg, "gate_chain_version", "v3"))


def _next_decision_seq(db_conn, trace_id: str) -> int:
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


def _insert_control_decision(
    db_conn,
    *,
    trace_id: str,
    verdict: str,
    schema_version: str,
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
                _GATE_NAME,
                verdict,
                schema_version,
                policy_hash,
                json.dumps(decision_context, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
                None,
            ),
        )
    finally:
        cursor.close()
    return decision_seq


def record_human_decision(
    db_conn,
    *,
    trace_id: Optional[str],
    verdict: str,
    policy_hash: str,
    decision_context: Optional[Dict[str, Any]] = None,
    corrections_content: Optional[List[Dict[str, Any]]] = None,
    override_ref: Optional[int] = None,
    execution_mode: Optional[str] = None,
    schema_version: Optional[str] = None,
) -> int:
    """
    Insert a human governance decision into append-only control_decisions.

    Phase 1: standalone helper only. No wiring into runtime flows.
    """
    if trace_id is None or str(trace_id).strip() == "":
        raise ValueError("trace_id is required")

    _require_live_execution(execution_mode)
    sv = _schema_version(schema_version)

    ctx: Dict[str, Any] = dict(decision_context or {})
    if override_ref is not None:
        ctx["override_ref"] = int(override_ref)
    if corrections_content is not None:
        ctx["corrections_content"] = corrections_content

    # Fail fast if decision_context isn't JSON-serializable.
    json.dumps(ctx, ensure_ascii=False)

    return _insert_control_decision(
        db_conn,
        trace_id=str(trace_id),
        verdict=verdict,
        schema_version=sv,
        policy_hash=policy_hash,
        decision_context=ctx,
    )


def record_human_approve(
    db_conn,
    *,
    trace_id: Optional[str],
    policy_hash: str,
    decision_context: Optional[Dict[str, Any]] = None,
    override_ref: Optional[int] = None,
    execution_mode: Optional[str] = None,
    schema_version: Optional[str] = None,
) -> int:
    return record_human_decision(
        db_conn,
        trace_id=trace_id,
        verdict=HUMAN_APPROVE,
        policy_hash=policy_hash,
        decision_context=decision_context,
        override_ref=override_ref,
        execution_mode=execution_mode,
        schema_version=schema_version,
    )


def record_human_reject(
    db_conn,
    *,
    trace_id: Optional[str],
    policy_hash: str,
    decision_context: Optional[Dict[str, Any]] = None,
    override_ref: Optional[int] = None,
    execution_mode: Optional[str] = None,
    schema_version: Optional[str] = None,
) -> int:
    return record_human_decision(
        db_conn,
        trace_id=trace_id,
        verdict=HUMAN_REJECT,
        policy_hash=policy_hash,
        decision_context=decision_context,
        override_ref=override_ref,
        execution_mode=execution_mode,
        schema_version=schema_version,
    )


def record_human_approve_with_correction(
    db_conn,
    *,
    trace_id: Optional[str],
    policy_hash: str,
    corrections_content: List[Dict[str, Any]],
    decision_context: Optional[Dict[str, Any]] = None,
    override_ref: Optional[int] = None,
    execution_mode: Optional[str] = None,
    schema_version: Optional[str] = None,
) -> int:
    return record_human_decision(
        db_conn,
        trace_id=trace_id,
        verdict=HUMAN_APPROVE_WITH_CORRECTION,
        policy_hash=policy_hash,
        decision_context=decision_context,
        corrections_content=corrections_content,
        override_ref=override_ref,
        execution_mode=execution_mode,
        schema_version=schema_version,
    )


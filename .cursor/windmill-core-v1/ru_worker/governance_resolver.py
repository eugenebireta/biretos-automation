from __future__ import annotations

from typing import Any, Dict, List, Optional

from config import get_config
from lib_integrations import log_event

import governance_decisions
import governance_workflow


SUPPORTED_VERDICTS = {
    governance_decisions.HUMAN_APPROVE,
    governance_decisions.HUMAN_REJECT,
    governance_decisions.HUMAN_APPROVE_WITH_CORRECTION,
}


def _enqueue_governance_execute(db_conn, *, case_id: str, trace_id: str) -> Dict[str, Any]:
    """
    Enqueue governance_execute with deterministic idempotency key.
    """
    idempotency_key = f"gov_exec_enqueue:{case_id}"

    # Local import to avoid circular import at module load time.
    from ru_worker import enqueue_job_with_trace  # type: ignore

    try:
        enqueue_job_with_trace(
            db_conn=db_conn,
            job_type="governance_execute",
            payload={"case_id": case_id},
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )
        return {"enqueued": True, "duplicate": False, "idempotency_key": idempotency_key}
    except Exception as e:
        msg = str(e).lower()
        if "duplicate" in msg or "unique" in msg:
            return {"enqueued": True, "duplicate": True, "idempotency_key": idempotency_key}
        raise


def execute_governance_resolve(
    payload: Dict[str, Any],
    db_conn,
    *,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Resolve review_cases from human decisions and optionally enqueue execution.

    Contract:
      - LIVE: apply decision to review_cases + append control_decisions.
      - REPLAY: no-op (skip).
      - Must not commit/rollback; ru_worker main loop owns tx boundaries.
    """
    cfg = get_config()
    mode = (getattr(cfg, "execution_mode", None) or "LIVE").strip().upper()
    if mode == "REPLAY":
        return {"status": "success", "skipped": True, "reason": "replay_mode"}

    case_id_raw = payload.get("case_id")
    if not case_id_raw:
        raise ValueError("case_id is required for governance_resolve")
    case_id = str(case_id_raw)

    verdict = str(payload.get("verdict") or "").strip()
    if verdict not in SUPPORTED_VERDICTS:
        raise ValueError(f"unsupported verdict for governance_resolve: {verdict}")

    resolved_by = payload.get("resolved_by")
    if not resolved_by:
        raise ValueError("resolved_by is required for governance_resolve")

    policy_hash = payload.get("policy_hash")
    if not policy_hash:
        raise ValueError("policy_hash is required for governance_resolve")

    case_state = governance_workflow.read_case_for_resume(db_conn, case_id=case_id)
    if case_state is None:
        return {"status": "error", "reason": "case_not_found", "case_id": case_id}

    case_status = str(case_state.get("status"))
    if case_status not in {"open", "assigned"}:
        return {
            "status": "success",
            "case_id": case_id,
            "already_resolved": True,
            "case_status": case_status,
        }

    effective_trace_id = trace_id or payload.get("trace_id") or case_state.get("trace_id")
    if not effective_trace_id:
        raise ValueError("trace_id is required for governance_resolve")

    decision_context = payload.get("decision_context")
    if decision_context is not None and not isinstance(decision_context, dict):
        raise ValueError("decision_context must be a dict when provided")

    override_ref = payload.get("override_ref")
    decision_seq: Optional[int] = None
    execution_enqueue: Dict[str, Any] = {"enqueued": False}

    if verdict == governance_decisions.HUMAN_APPROVE:
        decision_seq = governance_decisions.record_human_approve(
            db_conn,
            trace_id=str(effective_trace_id),
            policy_hash=str(policy_hash),
            decision_context=decision_context,
            override_ref=override_ref,
        )
        update = governance_workflow.approve_case(
            db_conn,
            case_id=case_id,
            approved_by=str(resolved_by),
        )
        if not update.get("updated"):
            return {"status": "skipped", "reason": "case_status_changed", "case_id": case_id}
        execution_enqueue = _enqueue_governance_execute(db_conn, case_id=case_id, trace_id=str(effective_trace_id))

    elif verdict == governance_decisions.HUMAN_APPROVE_WITH_CORRECTION:
        corrections_content = payload.get("corrections_content")
        if not isinstance(corrections_content, list) or not corrections_content:
            raise ValueError("corrections_content must be a non-empty list for HUMAN_APPROVE_WITH_CORRECTION")

        decision_seq = governance_decisions.record_human_approve_with_correction(
            db_conn,
            trace_id=str(effective_trace_id),
            policy_hash=str(policy_hash),
            corrections_content=corrections_content,
            decision_context=decision_context,
            override_ref=override_ref,
        )
        update = governance_workflow.approve_case_with_correction(
            db_conn,
            case_id=case_id,
            approved_by=str(resolved_by),
            corrections_content=corrections_content,
        )
        if not update.get("updated"):
            return {"status": "skipped", "reason": "case_status_changed", "case_id": case_id}
        execution_enqueue = _enqueue_governance_execute(db_conn, case_id=case_id, trace_id=str(effective_trace_id))

    else:
        decision_seq = governance_decisions.record_human_reject(
            db_conn,
            trace_id=str(effective_trace_id),
            policy_hash=str(policy_hash),
            decision_context=decision_context,
            override_ref=override_ref,
        )
        update = governance_workflow.resolve_case(
            db_conn,
            case_id=case_id,
            status="rejected",
            resolved_by=str(resolved_by),
            resolution_decision_seq=decision_seq,
        )
        if not update.get("updated"):
            return {"status": "skipped", "reason": "case_status_changed", "case_id": case_id}

    log_event(
        "governance_case_resolved",
        {
            "case_id": case_id,
            "trace_id": str(effective_trace_id),
            "verdict": verdict,
            "decision_seq": int(decision_seq) if decision_seq is not None else None,
            "execution_enqueued": bool(execution_enqueue.get("enqueued")),
            "execution_duplicate": bool(execution_enqueue.get("duplicate")),
            "execution_idempotency_key": execution_enqueue.get("idempotency_key"),
        },
    )

    return {
        "status": "success",
        "case_id": case_id,
        "trace_id": str(effective_trace_id),
        "verdict": verdict,
        "decision_seq": int(decision_seq) if decision_seq is not None else None,
        "execution_enqueued": bool(execution_enqueue.get("enqueued")),
        "execution_duplicate": bool(execution_enqueue.get("duplicate")),
        "execution_idempotency_key": execution_enqueue.get("idempotency_key"),
    }

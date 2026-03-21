from __future__ import annotations

import json
from typing import Any, Dict, Optional

from pydantic import ValidationError

from config import get_config
from domain.cdm_models import ActionSnapshot

import governance_workflow


def execute_governance_case_create(
    payload: Dict[str, Any],
    db_conn,
    *,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Job handler for job_type=governance_case_create.

    Phase 2 contract:
      - LIVE: create review_case idempotently.
      - REPLAY: no-op (skip) to preserve R7 replay isolation. (H1)
      - Must not enqueue further jobs.
      - Must not write to control_decisions.
      - Must not commit/rollback; ru_worker main loop owns tx boundaries.
    """
    cfg = get_config()
    mode = (getattr(cfg, "execution_mode", None) or "LIVE").strip().upper()
    if mode == "REPLAY":
        return {"status": "success", "skipped": True, "reason": "replay_mode"}

    effective_trace_id = trace_id or payload.get("trace_id")
    if not effective_trace_id:
        raise ValueError("trace_id is required for governance_case_create")

    gate_name = payload.get("gate_name")
    if not gate_name:
        raise ValueError("gate_name is required for governance_case_create")

    original_decision_seq = payload.get("original_decision_seq")
    if original_decision_seq is None:
        raise ValueError("original_decision_seq is required for governance_case_create")

    policy_hash = payload.get("policy_hash")
    if not policy_hash:
        raise ValueError("policy_hash is required for governance_case_create")

    action_snapshot = payload.get("action_snapshot")
    if not isinstance(action_snapshot, dict):
        raise ValueError("action_snapshot must be a dict for governance_case_create")
    # ── B2 (Task 5.2): validate action_snapshot schema BEFORE writing to DB ───
    try:
        ActionSnapshot.model_validate(action_snapshot)
    except ValidationError as _exc:
        # 5.3: structured validation-error log at decision boundary
        print(
            json.dumps(
                {
                    "event": "validation_error",
                    "boundary": "governance_case_creator",
                    "error_class": "POLICY_VIOLATION",
                    "severity": "ERROR",
                    "retriable": False,
                    "detail": str(_exc),
                }
            ),
            flush=True,
        )
        raise ValueError(
            f"action_snapshot schema violation (Task 5.2): {_exc}"
        ) from _exc
    # ─────────────────────────────────────────────────────────────────────────

    result = governance_workflow.create_review_case(
        db_conn,
        trace_id=str(effective_trace_id),
        order_id=payload.get("order_id"),
        gate_name=str(gate_name),
        original_verdict=str(payload.get("original_verdict") or "NEEDS_HUMAN"),
        original_decision_seq=int(original_decision_seq),
        policy_hash=str(policy_hash),
        action_snapshot=action_snapshot,
        resume_context=payload.get("resume_context") if isinstance(payload.get("resume_context"), dict) else None,
        sla_deadline_at=payload.get("sla_deadline_at"),
    )

    return {"status": "success", "case_id": result["case_id"], "created": result["created"]}


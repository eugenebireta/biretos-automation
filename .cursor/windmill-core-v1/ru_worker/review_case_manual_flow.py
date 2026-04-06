from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

try:
    import ru_worker.governance_decisions as governance_decisions
    import ru_worker.governance_workflow as governance_workflow
    from ru_worker.send_invoice_execution import SEND_INVOICE_POLICY_HASH
    from ru_worker.stability_gate_metrics import record_closed_cycle
except ImportError:
    import governance_decisions  # type: ignore
    import governance_workflow  # type: ignore
    from send_invoice_execution import SEND_INVOICE_POLICY_HASH  # type: ignore
    from stability_gate_metrics import record_closed_cycle  # type: ignore

SEND_INVOICE_MANUAL_REVIEW_GATE = "send_invoice_manual_review"
_LISTABLE_STATUSES = ("open", "assigned")
_RESOLVABLE_STATUSES = {"executed", "rejected", "cancelled"}


def _jsonb_to_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        loaded = json.loads(value)
        if isinstance(loaded, dict):
            return loaded
    return {}


def _fetch_case(db_conn, *, case_id: str) -> Optional[Dict[str, Any]]:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT
                id,
                trace_id,
                gate_name,
                status,
                assigned_to,
                original_decision_seq,
                policy_hash,
                action_snapshot,
                resume_context,
                resolved_by,
                resolution_decision_seq
            FROM review_cases
            WHERE id = %s::uuid
            """,
            (case_id,),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    if not row:
        return None
    return {
        "case_id": str(row[0]),
        "trace_id": str(row[1]),
        "gate_name": str(row[2]),
        "status": str(row[3]),
        "assigned_to": str(row[4]) if row[4] is not None else None,
        "original_decision_seq": int(row[5]),
        "policy_hash": str(row[6]),
        "action_snapshot": _jsonb_to_dict(row[7]),
        "resume_context": _jsonb_to_dict(row[8]),
        "resolved_by": str(row[9]) if row[9] is not None else None,
        "resolution_decision_seq": int(row[10]) if row[10] is not None else None,
    }


def _case_message_context(case_row: Dict[str, Any]) -> Dict[str, Any]:
    resume_context = case_row.get("resume_context") or {}
    order_reference = resume_context.get("order_reference")
    context: Dict[str, Any] = {
        "case_id": case_row["case_id"],
        "review_gate_name": case_row["gate_name"],
        "intent_type": "send_invoice",
        "manual_outcome": resume_context.get("manual_outcome"),
        "reason": resume_context.get("reason"),
        "source": "telegram_review_case_manual_path",
    }
    if order_reference:
        context["order_reference"] = order_reference
    required_fields = resume_context.get("required_fields")
    if required_fields:
        context["required_fields"] = required_fields
    return context


def list_send_invoice_manual_cases(
    db_conn,
    *,
    limit: int = 10,
) -> Dict[str, Any]:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT
                id,
                status,
                assigned_to,
                trace_id,
                resume_context,
                created_at
            FROM review_cases
            WHERE gate_name = %s
              AND status IN ('open', 'assigned')
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (SEND_INVOICE_MANUAL_REVIEW_GATE, int(limit)),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()

    cases: List[Dict[str, Any]] = []
    for row in rows:
        resume_context = _jsonb_to_dict(row[4])
        cases.append(
            {
                "case_id": str(row[0]),
                "status": str(row[1]),
                "assigned_to": str(row[2]) if row[2] is not None else None,
                "trace_id": str(row[3]),
                "resume_context": resume_context,
                "created_at": str(row[5]) if row[5] is not None else None,
            }
        )

    return {
        "status": "success",
        "gate_name": SEND_INVOICE_MANUAL_REVIEW_GATE,
        "cases": cases,
        "count": len(cases),
    }


def assign_send_invoice_manual_case(
    db_conn,
    *,
    case_id: str,
    actor_id: str,
) -> Dict[str, Any]:
    case_row = _fetch_case(db_conn, case_id=case_id)
    if not case_row:
        return {"status": "not_found", "case_id": case_id}
    if case_row["gate_name"] != SEND_INVOICE_MANUAL_REVIEW_GATE:
        return {
            "status": "unsupported_gate",
            "case_id": case_id,
            "gate_name": case_row["gate_name"],
        }

    if case_row["status"] == "assigned":
        if case_row["assigned_to"] == actor_id:
            return {
                "status": "already_assigned",
                "case_id": case_id,
                "assigned_to": actor_id,
                "trace_id": case_row["trace_id"],
                "resume_context": case_row["resume_context"],
            }
        return {
            "status": "assigned_to_other",
            "case_id": case_id,
            "assigned_to": case_row["assigned_to"],
            "trace_id": case_row["trace_id"],
            "resume_context": case_row["resume_context"],
        }

    if case_row["status"] != "open":
        return {
            "status": "not_assignable",
            "case_id": case_id,
            "case_status": case_row["status"],
            "trace_id": case_row["trace_id"],
            "resume_context": case_row["resume_context"],
        }

    updated = governance_workflow.assign_case(
        db_conn,
        case_id=case_id,
        assigned_to=actor_id,
    )
    if not updated.get("updated"):
        raise RuntimeError(f"assign_case_failed:{case_id}")

    return {
        "status": "assigned",
        "case_id": case_id,
        "assigned_to": actor_id,
        "trace_id": case_row["trace_id"],
        "resume_context": case_row["resume_context"],
    }


def resolve_send_invoice_manual_case(
    db_conn,
    *,
    case_id: str,
    actor_id: str,
    resolution_status: str,
) -> Dict[str, Any]:
    resolution_status = str(resolution_status).strip().lower()
    if resolution_status not in _RESOLVABLE_STATUSES:
        raise ValueError(f"unsupported review resolution status: {resolution_status}")

    case_row = _fetch_case(db_conn, case_id=case_id)
    if not case_row:
        return {"status": "not_found", "case_id": case_id}
    if case_row["gate_name"] != SEND_INVOICE_MANUAL_REVIEW_GATE:
        return {
            "status": "unsupported_gate",
            "case_id": case_id,
            "gate_name": case_row["gate_name"],
        }

    if case_row["status"] in _RESOLVABLE_STATUSES:
        return {
            "status": "already_resolved",
            "case_id": case_id,
            "case_status": case_row["status"],
            "trace_id": case_row["trace_id"],
            "resume_context": case_row["resume_context"],
        }

    if case_row["status"] != "assigned":
        return {
            "status": "needs_assignment",
            "case_id": case_id,
            "case_status": case_row["status"],
            "trace_id": case_row["trace_id"],
            "resume_context": case_row["resume_context"],
        }

    if case_row["assigned_to"] != actor_id:
        return {
            "status": "assigned_to_other",
            "case_id": case_id,
            "assigned_to": case_row["assigned_to"],
            "trace_id": case_row["trace_id"],
            "resume_context": case_row["resume_context"],
        }

    decision_context = _case_message_context(case_row)
    decision_context["resolution_status"] = resolution_status
    decision_context["actor_employee_id"] = actor_id

    if resolution_status == "executed":
        human_decision_seq = governance_decisions.record_human_approve(
            db_conn,
            trace_id=case_row["trace_id"],
            policy_hash=case_row["policy_hash"] or SEND_INVOICE_POLICY_HASH,
            decision_context=decision_context,
            override_ref=case_row["original_decision_seq"],
        )
    else:
        human_decision_seq = governance_decisions.record_human_reject(
            db_conn,
            trace_id=case_row["trace_id"],
            policy_hash=case_row["policy_hash"] or SEND_INVOICE_POLICY_HASH,
            decision_context=decision_context,
            override_ref=case_row["original_decision_seq"],
        )

    updated = governance_workflow.resolve_case(
        db_conn,
        case_id=case_id,
        status=resolution_status,
        resolved_by=actor_id,
        resolution_decision_seq=human_decision_seq,
    )
    if not updated.get("updated"):
        raise RuntimeError(f"resolve_case_failed:{case_id}:{resolution_status}")

    closed_cycle_seq = record_closed_cycle(
        db_conn,
        trace_id=case_row["trace_id"],
        intent_type="send_invoice",
        employee_id=actor_id,
        policy_hash=case_row["policy_hash"] or SEND_INVOICE_POLICY_HASH,
        extra={
            "case_id": case_id,
            "resolution_status": resolution_status,
            "review_gate_name": SEND_INVOICE_MANUAL_REVIEW_GATE,
        },
    )

    return {
        "status": "resolved",
        "case_id": case_id,
        "trace_id": case_row["trace_id"],
        "resolution_status": resolution_status,
        "human_decision_seq": human_decision_seq,
        "closed_cycle_decision_seq": closed_cycle_seq,
        "resume_context": case_row["resume_context"],
    }

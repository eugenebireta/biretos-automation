"""
Backoffice Router. Phase 6.1 — main entry point for employee intents.

Supported intents:
  check_payment  → TBank invoice status (read-only)
  get_tracking   → CDEK tracking status (read-only)
  get_waybill    → CDEK waybill PDF (read-only external call)

Pipeline per intent:
  1. Validate BackofficeTaskIntent (Pydantic)
  2. guard_employee_intent()   — permission check (INV-PERMISSION-DENIED)
  3. classify_intent_risk()    — LOW / MEDIUM / HIGH
  4. check_rate_limit()        — INV-RATE
  5. guard_backoffice_rate_limit()
  6. <leaf handler>            — external adapter call
  7. snapshot_external_read()  — INV-ERS
  8. write_employee_action()   — audit log
  9. write_shadow_rag_entry()  — fire-and-forget RAG
  10. db_conn.commit()

CLAUDE.md constraints:
  - trace_id from payload (BackofficeTaskIntent.trace_id)
  - idempotency_key for every log write
  - commit only at router boundary (step 10)
  - no secrets in logs
  - structured error: error_class / severity / retriable
  - no silent exception swallowing
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from pydantic import ValidationError

from domain.backoffice_models import BackofficeTaskIntent, RiskLevel
from domain.backoffice_permission import guard_employee_intent
from domain.backoffice_rate_limiter import check_rate_limit
from domain.backoffice_risk_registry import classify_intent_risk
from domain.guardian import GuardianVeto, guard_backoffice_rate_limit
from domain.ports import (
    ShipmentTrackingStatusRequest,
    WaybillRequest,
)

try:
    from backoffice_action_logger import write_employee_action
    from backoffice_shadow_logger import write_shadow_rag_entry
    from backoffice_snapshot_store import snapshot_external_read
except ImportError:
    from ru_worker.backoffice_action_logger import write_employee_action  # type: ignore
    from ru_worker.backoffice_shadow_logger import write_shadow_rag_entry  # type: ignore
    from ru_worker.backoffice_snapshot_store import snapshot_external_read  # type: ignore

from ru_worker.send_invoice_execution import (
    SEND_INVOICE_POLICY_HASH,
    execute_send_invoice,
)
from ru_worker.stability_gate_metrics import (
    record_closed_cycle,
    record_escalation,
    record_manual_intervention,
)
from ru_worker import governance_workflow


SEND_INVOICE_MANUAL_REVIEW_GATE = "send_invoice_manual_review"
_SEND_INVOICE_MANUAL_REVIEW_DECISION_SEQ = {
    "insufficient_context": 1,
    "review_required": 2,
}
_SEND_INVOICE_REQUIRED_FIELDS = {
    "send_invoice_order_context_unavailable": ["order_context"],
    "send_invoice_missing_customer_inn": ["customer_data.inn"],
    "send_invoice_missing_total_amount": ["total_amount"],
    "send_invoice_missing_line_items": ["order_line_items"],
    "send_invoice_multiple_line_items_unsupported": ["single_line_item_snapshot"],
    "send_invoice_invalid_line_quantity": ["valid_line_item_quantity"],
    "send_invoice_negative_delivery_delta": ["consistent_order_total_vs_line_items"],
}


# ---------------------------------------------------------------------------
# Structured logging helper (no secrets)
# ---------------------------------------------------------------------------

def _log(event: str, data: Dict[str, Any]) -> None:
    import time
    print(json.dumps({"event": event, "ts": time.time(), **data}), flush=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _send_invoice_review_required_fields(leaf_result: Dict[str, Any]) -> list[str]:
    required_fields = leaf_result.get("required_fields")
    if isinstance(required_fields, list):
        return [str(item) for item in required_fields if str(item).strip()]
    reason = str(leaf_result.get("error") or "")
    return list(_SEND_INVOICE_REQUIRED_FIELDS.get(reason, []))


def _send_invoice_redacted_summary(intent: BackofficeTaskIntent, leaf_result: Dict[str, Any]) -> str:
    insales_order_id = str(
        leaf_result.get("insales_order_id")
        or intent.payload.get("insales_order_id")
        or ""
    ).strip()
    if insales_order_id:
        return f"send_invoice manual review for order {insales_order_id}"
    return "send_invoice manual review without explicit order reference"


def _create_send_invoice_manual_review_case(
    db_conn: Any,
    *,
    intent: BackofficeTaskIntent,
    leaf_result: Dict[str, Any],
    risk_level: RiskLevel,
) -> Dict[str, Any]:
    leaf_status = str(leaf_result.get("status") or "")
    decision_seq = _SEND_INVOICE_MANUAL_REVIEW_DECISION_SEQ.get(leaf_status)
    if decision_seq is None:
        raise ValueError(f"unsupported send_invoice manual review status: {leaf_status}")

    created_at = _utc_now_iso()
    reason = str(leaf_result.get("error") or leaf_status)
    required_fields = _send_invoice_review_required_fields(leaf_result)
    summary = _send_invoice_redacted_summary(intent, leaf_result)
    nlu_meta = intent.metadata.get("nlu") if isinstance(intent.metadata.get("nlu"), dict) else {}
    source_entrypoint = "assistant_nlu_confirm" if nlu_meta else "backoffice_router"
    order_ref = str(
        leaf_result.get("insales_order_id")
        or intent.payload.get("insales_order_id")
        or ""
    ).strip() or None
    order_id = leaf_result.get("order_id")

    action_snapshot = {
        "case_type": "manual_review",
        "intent_type": "send_invoice",
        "manual_outcome": leaf_status,
        "reason": reason,
        "redacted_summary": summary,
        "order_reference": {
            "insales_order_id": order_ref,
            "order_id": order_id,
        },
        "risk_level": risk_level.value,
        "source": source_entrypoint,
        "created_at": created_at,
    }
    resume_context = {
        "intent_type": "send_invoice",
        "manual_outcome": leaf_status,
        "reason": reason,
        "redacted_summary": summary,
        "message": leaf_result.get("message"),
        "entities": dict(intent.payload),
        "required_fields": required_fields,
        "order_reference": {
            "insales_order_id": order_ref,
            "order_id": order_id,
        },
        "risk_level": risk_level.value,
        "source": {
            "channel": "telegram" if nlu_meta else "backoffice",
            "entrypoint": source_entrypoint,
            "confirmation_id": nlu_meta.get("confirmation_id"),
            "model_version": nlu_meta.get("model_version"),
            "prompt_version": nlu_meta.get("prompt_version"),
            "confidence": nlu_meta.get("confidence"),
        },
        "employee": {
            "employee_id": intent.employee_id,
            "employee_role": intent.employee_role,
        },
        "created_at": created_at,
    }

    result = governance_workflow.create_review_case(
        db_conn,
        trace_id=intent.trace_id,
        order_id=str(order_id) if order_id else None,
        gate_name=SEND_INVOICE_MANUAL_REVIEW_GATE,
        original_verdict="NEEDS_HUMAN",
        original_decision_seq=decision_seq,
        policy_hash=SEND_INVOICE_POLICY_HASH,
        action_snapshot=action_snapshot,
        resume_context=resume_context,
        sla_deadline_at=None,
    )
    return {
        "case_id": result["case_id"],
        "status": result["status"],
        "created": bool(result["created"]),
        "gate_name": SEND_INVOICE_MANUAL_REVIEW_GATE,
        "original_decision_seq": decision_seq,
    }


# ---------------------------------------------------------------------------
# Leaf handlers — each returns a plain dict result
# ---------------------------------------------------------------------------

def _handle_check_payment(
    intent: BackofficeTaskIntent,
    payment_adapter: Any,
) -> Dict[str, Any]:
    """
    check_payment: fetch T-Bank invoice status.
    payment_adapter must implement PaymentInvoicePort.
    """
    from domain.ports import InvoiceStatusRequest

    invoice_id = intent.payload.get("invoice_id") or intent.payload.get("provider_document_id")
    if not invoice_id:
        raise ValueError("check_payment requires payload.invoice_id")

    req = InvoiceStatusRequest(
        provider_document_id=str(invoice_id),
        trace_id=intent.trace_id,
    )
    resp = payment_adapter.get_invoice_status(req)
    return {
        "provider_document_id": resp.provider_document_id,
        "provider_status": resp.provider_status,
        "raw_response": resp.raw_response,
        "_snapshot": {
            "provider": "tbank",
            "entity_type": "invoice",
            "entity_id": str(invoice_id),
            "data": resp.raw_response,
        },
    }


def _handle_get_tracking(
    intent: BackofficeTaskIntent,
    shipment_adapter: Any,
) -> Dict[str, Any]:
    """
    get_tracking: fetch CDEK tracking status.
    shipment_adapter must implement ShipmentPort.
    """
    carrier_id = (
        intent.payload.get("carrier_external_id")
        or intent.payload.get("cdek_uuid")
        or intent.payload.get("tracking_id")
    )
    if not carrier_id:
        raise ValueError("get_tracking requires payload.carrier_external_id")

    req = ShipmentTrackingStatusRequest(
        carrier_external_id=str(carrier_id),
        trace_id=intent.trace_id,
    )
    resp = shipment_adapter.get_tracking_status(req)
    return {
        "carrier_external_id": resp.carrier_external_id,
        "carrier_status": resp.carrier_status,
        "raw_response": resp.raw_response,
        "_snapshot": {
            "provider": "cdek",
            "entity_type": "tracking",
            "entity_id": str(carrier_id),
            "data": resp.raw_response,
        },
    }


def _handle_get_waybill(
    intent: BackofficeTaskIntent,
    shipment_adapter: Any,
) -> Dict[str, Any]:
    """
    get_waybill: download CDEK waybill PDF.
    shipment_adapter must implement ShipmentPort with get_waybill().
    Returns pdf_bytes as hex string (JSON-safe).
    """
    carrier_id = (
        intent.payload.get("carrier_external_id")
        or intent.payload.get("cdek_uuid")
    )
    if not carrier_id:
        raise ValueError("get_waybill requires payload.carrier_external_id")

    req = WaybillRequest(
        carrier_external_id=str(carrier_id),
        trace_id=intent.trace_id,
    )
    resp = shipment_adapter.get_waybill(req)
    return {
        "carrier_external_id": resp.carrier_external_id,
        "pdf_size_bytes": len(resp.pdf_bytes),
        "pdf_hex": resp.pdf_bytes.hex(),
        "_snapshot": {
            "provider": "cdek",
            "entity_type": "waybill",
            "entity_id": str(carrier_id),
            "data": {**resp.raw_response, "pdf_size_bytes": len(resp.pdf_bytes)},
        },
    }


def _handle_send_invoice(
    intent: BackofficeTaskIntent,
    db_conn: Any,
) -> Dict[str, Any]:
    return execute_send_invoice(
        db_conn,
        trace_id=intent.trace_id,
        payload=intent.payload,
    )


_LEAF_HANDLERS: Dict[str, Callable] = {
    "check_payment": _handle_check_payment,
    "get_tracking":  _handle_get_tracking,
    "get_waybill":   _handle_get_waybill,
    "send_invoice":  _handle_send_invoice,
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def route_backoffice_intent(
    payload: Dict[str, Any],
    db_conn: Any,
    *,
    payment_adapter: Any = None,
    shipment_adapter: Any = None,
) -> Dict[str, Any]:
    """
    Main entry point for all backoffice employee intents.

    payload keys (merged from action dict):
      trace_id, intent_type, employee_id, employee_role, payload, metadata

    payment_adapter: PaymentInvoicePort (injected; default: TBankInvoiceAdapter)
    shipment_adapter: ShipmentPort (injected; default: CDEKShipmentAdapter)

    Returns structured result dict.
    Raises GuardianVeto on permission/rate violations (never swallowed here).
    """
    # ── Step 1: Validate BackofficeTaskIntent ─────────────────────────────
    try:
        intent = BackofficeTaskIntent.model_validate(payload)
    except ValidationError as exc:
        _log("backoffice_validation_error", {
            "boundary": "backoffice_router",
            "error_class": "POLICY_VIOLATION",
            "severity": "ERROR",
            "retriable": False,
            "detail": str(exc),
        })
        return {
            "status": "error",
            "error": "invalid_backoffice_intent",
            "error_class": "POLICY_VIOLATION",
        }

    trace_id = intent.trace_id
    idem_key = intent.effective_idempotency_key()

    _log("backoffice_intent_start", {
        "trace_id": trace_id,
        "intent_type": intent.intent_type,
        "employee_id": intent.employee_id,
        "employee_role": intent.employee_role,
    })

    # ── Step 2: Permission guard ──────────────────────────────────────────
    try:
        guard_employee_intent(intent)
    except GuardianVeto as veto:
        _log("backoffice_permission_denied", {
            "trace_id": trace_id,
            "invariant": veto.invariant,
            "reason": veto.reason,
            "error_class": "POLICY_VIOLATION",
            "severity": "WARNING",
            "retriable": False,
        })
        _write_action_log(db_conn, intent, idem_key, "forbidden",
                          {"invariant": veto.invariant, "reason": veto.reason})
        db_conn.commit()
        return {
            "status": "forbidden",
            "error": veto.reason,
            "invariant": veto.invariant,
        }

    # ── Step 3: Risk classification ───────────────────────────────────────
    risk_level: RiskLevel = classify_intent_risk(intent.intent_type)

    # ── Step 4+5: Rate limit check ────────────────────────────────────────
    rate_result = check_rate_limit(
        db_conn,
        employee_id=intent.employee_id,
        intent_type=intent.intent_type,
        risk_level=risk_level,
    )
    try:
        guard_backoffice_rate_limit(rate_result)
    except GuardianVeto as veto:
        _log("backoffice_rate_limited", {
            "trace_id": trace_id,
            "invariant": veto.invariant,
            "employee_id": intent.employee_id,
            "intent_type": intent.intent_type,
            "current_count": rate_result.current_count,
            "limit": rate_result.limit,
            "error_class": "POLICY_VIOLATION",
            "severity": "WARNING",
            "retriable": False,
        })
        _write_action_log(db_conn, intent, idem_key, "rate_limited", {
            "current_count": rate_result.current_count,
            "limit": rate_result.limit,
        })
        db_conn.commit()
        return {
            "status": "rate_limited",
            "error": veto.reason,
            "current_count": rate_result.current_count,
            "limit": rate_result.limit,
        }

    # ── Step 6: Lazy-load default adapters ───────────────────────────────
    if intent.intent_type == "check_payment" and payment_adapter is None:
        from side_effects.adapters.tbank_adapter import TBankInvoiceAdapter
        payment_adapter = TBankInvoiceAdapter()
    if intent.intent_type in {"get_tracking", "get_waybill"} and shipment_adapter is None:
        from side_effects.adapters.cdek_adapter import CDEKShipmentAdapter
        shipment_adapter = CDEKShipmentAdapter()

    # ── Step 6: Leaf handler call ─────────────────────────────────────────
    handler = _LEAF_HANDLERS[intent.intent_type]
    if intent.intent_type == "check_payment":
        adapter = payment_adapter
    elif intent.intent_type == "send_invoice":
        adapter = db_conn
    else:
        adapter = shipment_adapter

    try:
        leaf_result = handler(intent, adapter)
    except Exception as exc:
        _log("backoffice_leaf_error", {
            "trace_id": trace_id,
            "intent_type": intent.intent_type,
            "error_class": "TRANSIENT",
            "severity": "ERROR",
            "retriable": True,
            "error": str(exc),
        })
        _write_action_log(db_conn, intent, idem_key, "error", {
            "error": str(exc),
            "error_class": "TRANSIENT",
        })
        db_conn.commit()
        return {
            "status": "error",
            "error": str(exc),
            "error_class": "TRANSIENT",
        }

    if intent.intent_type == "send_invoice":
        leaf_status = str(leaf_result.get("status") or "error")
        if leaf_status in {"insufficient_context", "review_required"}:
            reason = str(leaf_result.get("error") or leaf_status)
            try:
                review_case = _create_send_invoice_manual_review_case(
                    db_conn,
                    intent=intent,
                    leaf_result=leaf_result,
                    risk_level=risk_level,
                )
            except Exception as exc:
                if hasattr(db_conn, "rollback"):
                    db_conn.rollback()
                _log("send_invoice_review_case_error", {
                    "trace_id": trace_id,
                    "intent_type": intent.intent_type,
                    "employee_id": intent.employee_id,
                    "manual_outcome": leaf_status,
                    "error_class": "ERROR",
                    "severity": "ERROR",
                    "retriable": False,
                    "error": str(exc),
                })
                raise
            record_manual_intervention(
                db_conn,
                trace_id=trace_id,
                intent_type=intent.intent_type,
                reason=reason,
                employee_id=intent.employee_id,
                employee_role=intent.employee_role,
                policy_hash=SEND_INVOICE_POLICY_HASH,
                extra={"insales_order_id": leaf_result.get("insales_order_id")},
            )
            record_escalation(
                db_conn,
                trace_id=trace_id,
                intent_type=intent.intent_type,
                reason=reason,
                employee_id=intent.employee_id,
                policy_hash=SEND_INVOICE_POLICY_HASH,
                extra={"insales_order_id": leaf_result.get("insales_order_id")},
            )
            _write_action_log(
                db_conn,
                intent,
                idem_key,
                leaf_status,
                {
                    "error": reason,
                    "required_fields": leaf_result.get("required_fields"),
                    "review_case_id": review_case["case_id"],
                    "review_case_created": review_case["created"],
                },
                context_snapshot={"risk_level": risk_level.value},
            )
            write_shadow_rag_entry(
                db_conn,
                trace_id=trace_id,
                employee_id=intent.employee_id,
                intent_type=intent.intent_type,
                context_json={
                    "intent_payload": intent.payload,
                    "risk_level": risk_level.value,
                    "outcome": leaf_status,
                    "error": reason,
                    "review_case_id": review_case["case_id"],
                },
                response_summary=f"{intent.intent_type} {leaf_status}",
            )
            db_conn.commit()
            _log("backoffice_intent_complete", {
                "trace_id": trace_id,
                "intent_type": intent.intent_type,
                "employee_id": intent.employee_id,
                "outcome": leaf_status,
                "review_case_id": review_case["case_id"],
                "review_case_created": review_case["created"],
            })
            return {
                "trace_id": trace_id,
                "intent_type": intent.intent_type,
                "review_case_id": review_case["case_id"],
                "review_case_created": review_case["created"],
                "review_case_gate_name": review_case["gate_name"],
                **leaf_result,
            }
        if leaf_status == "success":
            record_closed_cycle(
                db_conn,
                trace_id=trace_id,
                intent_type=intent.intent_type,
                employee_id=intent.employee_id,
                policy_hash=SEND_INVOICE_POLICY_HASH,
                extra={"provider_document_id": leaf_result.get("provider_document_id")},
            )

    # ── Step 7: Snapshot external read (INV-ERS) ──────────────────────────
    snap_meta = leaf_result.pop("_snapshot", None)
    if snap_meta:
        snapshot_external_read(
            db_conn,
            trace_id=trace_id,
            provider=snap_meta["provider"],
            entity_type=snap_meta["entity_type"],
            entity_id=snap_meta["entity_id"],
            snapshot_data=snap_meta["data"],
        )

    # ── Step 8: Audit log ─────────────────────────────────────────────────
    context_snapshot = {
        "rate_current": rate_result.current_count,
        "rate_limit": rate_result.limit,
        "risk_level": risk_level.value,
    }
    _write_action_log(
        db_conn, intent, idem_key, "success",
        {"result_keys": list(leaf_result.keys())},
        context_snapshot=context_snapshot,
    )

    # ── Step 9: Shadow RAG log (fire-and-forget) ──────────────────────────
    write_shadow_rag_entry(
        db_conn,
        trace_id=trace_id,
        employee_id=intent.employee_id,
        intent_type=intent.intent_type,
        context_json={
            "intent_payload": intent.payload,
            "risk_level": risk_level.value,
            "rate_window": context_snapshot,
            "outcome": "success",
        },
        response_summary=f"{intent.intent_type} ok",
    )

    # ── Step 10: Commit ───────────────────────────────────────────────────
    db_conn.commit()

    _log("backoffice_intent_complete", {
        "trace_id": trace_id,
        "intent_type": intent.intent_type,
        "employee_id": intent.employee_id,
        "outcome": "success",
    })

    return {
        "status": "success",
        "intent_type": intent.intent_type,
        "trace_id": trace_id,
        **leaf_result,
    }


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _write_action_log(
    db_conn: Any,
    intent: BackofficeTaskIntent,
    idem_key: str,
    outcome: str,
    outcome_detail: Optional[Dict[str, Any]] = None,
    context_snapshot: Optional[Dict[str, Any]] = None,
) -> None:
    risk = classify_intent_risk(intent.intent_type) if intent.intent_type in ("check_payment", "get_tracking", "get_waybill", "send_invoice") else RiskLevel.LOW
    write_employee_action(
        db_conn,
        trace_id=intent.trace_id,
        idempotency_key=idem_key,
        employee_id=intent.employee_id,
        employee_role=intent.employee_role,
        intent_type=intent.intent_type,
        risk_level=risk.value,
        payload_snapshot=intent.payload,
        context_snapshot=context_snapshot or {},
        outcome=outcome,
        outcome_detail=outcome_detail,
    )

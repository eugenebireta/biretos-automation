"""
Assistant Router — Phase 7.2 / 7.5.

Two public entry points:

  route_assistant_intent(payload, db_conn) → dict
    Called when an employee sends a free-text message.
    Sanitizes → parses → (shadow/fallback/ok) → stores confirmation → returns
    button payload for Telegram.

  confirm_nlu_intent(payload, db_conn, ...) → dict
    Called when an employee clicks nlu_confirm:<id>.
    Atomically consumes the pending confirmation → routes to backoffice_router.

Both functions:
  - Accept trace_id from payload (POLICY_VIOLATION if missing/empty).
  - Commit only at this boundary (not inside domain operations).
  - Write SLA log as fire-and-forget.
  - Never log raw employee text.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from domain.guardian import GuardianVeto, guard_nlu_confirmation
from domain.nlu_models import NLUConfig
from domain.intent_parser import parse_intent
from domain.prompt_injection_guard import sanitize_nlu_input

from .nlu_confirmation_store import get_and_consume, store_confirmation
from .nlu_shadow_log import write_nlu_shadow_entry
from .nlu_sla_tracker import record_nlu_sla


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_nlu_config() -> NLUConfig:
    """Load NLUConfig from environment at call time (no import cycle)."""
    import os

    def _bool(name: str, default: bool) -> bool:
        v = os.environ.get(name, "").strip().lower()
        if not v:
            return default
        return v in ("1", "true", "yes", "y", "on")

    def _int(name: str, default: int) -> int:
        v = os.environ.get(name, "").strip()
        try:
            return int(v) if v else default
        except ValueError:
            return default

    def _float(name: str, default: float) -> float:
        v = os.environ.get(name, "").strip()
        try:
            return float(v) if v else default
        except ValueError:
            return default

    return NLUConfig(
        nlu_enabled=_bool("NLU_ENABLED", False),
        degradation_level=_int("NLU_DEGRADATION_LEVEL", 2),
        confidence_threshold=_float("NLU_CONFIDENCE_THRESHOLD", 0.80),
        shadow_mode=_bool("NLU_SHADOW_MODE", True),
        model_version=os.environ.get("NLU_MODEL_VERSION", "regex-v1"),
        prompt_version=os.environ.get("NLU_PROMPT_VERSION", "v1.0"),
        max_input_bytes=_int("NLU_MAX_INPUT_BYTES", 1024),
    )


def _extract_trace_id(payload: Dict[str, Any]) -> Optional[str]:
    return payload.get("trace_id") or None


def _policy_violation(trace_id: str, reason: str) -> Dict[str, Any]:
    return {
        "status": "error",
        "error_class": "POLICY_VIOLATION",
        "severity": "ERROR",
        "retriable": False,
        "error": reason,
        "trace_id": trace_id,
    }


# ---------------------------------------------------------------------------
# route_assistant_intent  (nlu_parse action)
# ---------------------------------------------------------------------------


def route_assistant_intent(
    payload: Dict[str, Any],
    db_conn: Any,
) -> Dict[str, Any]:
    """
    Handle free-text NLU parse request.

    Expected payload keys:
      trace_id        (required, non-empty)
      employee_id     (required)
      employee_role   (optional, default "operator")
      text            (required — raw free-text from Telegram message)

    Returns dict with:
      status:  "needs_confirmation" | "shadow" | "fallback" | "button_only" | "error"
      + supporting fields for Telegram UI construction.

    Side-effects:
      - Inserts into nlu_pending_confirmations (if status=needs_confirmation).
      - Writes to nlu_sla_log (fire-and-forget).
      - Writes to shadow_rag_log (fire-and-forget, only in shadow mode).
      - Commits db_conn.
    """
    t_total_start = time.monotonic()

    trace_id = _extract_trace_id(payload)
    if not trace_id:
        return _policy_violation("", "trace_id is required and must be non-empty")

    employee_id = str(payload.get("employee_id") or "unknown")
    employee_role = str(payload.get("employee_role") or "operator")
    raw_text = str(payload.get("text") or "")

    if not raw_text:
        return _policy_violation(trace_id, "text is required and must be non-empty")

    config = _load_nlu_config()

    # Sanitize input (INV-injection-guard)
    sanitized = sanitize_nlu_input(raw_text, config)

    # Detect injection attempts: if was_stripped and text is now empty
    if sanitized.was_stripped and not sanitized.text.strip():
        _write_sla(
            db_conn, trace_id, employee_id, None, config,
            parse_duration_ms=0,
            total_duration_ms=_ms(t_total_start),
            status="injection_rejected",
        )
        db_conn.commit()
        return {
            "status": "error",
            "error_class": "POLICY_VIOLATION",
            "severity": "WARNING",
            "retriable": False,
            "error": "input_rejected_by_injection_guard",
            "trace_id": trace_id,
        }

    # Parse intent
    nlu_result = parse_intent(sanitized.text, config)
    parse_ms = nlu_result.parse_duration_ms

    # Shadow mode: log parse result, do NOT store confirmation
    if nlu_result.status == "shadow" and nlu_result.parsed is not None:
        parsed = nlu_result.parsed
        write_nlu_shadow_entry(
            db_conn,
            trace_id=trace_id,
            employee_id=employee_id,
            raw_text_hash=parsed.raw_text_hash,
            intent_type=parsed.intent_type,
            entities=dict(parsed.entities),
            confidence=parsed.confidence,
            model_version=parsed.model_version,
            prompt_version=parsed.prompt_version,
            parse_duration_ms=parse_ms,
        )
        _write_sla(
            db_conn, trace_id, employee_id, parsed.intent_type, config,
            parse_duration_ms=parse_ms,
            total_duration_ms=_ms(t_total_start),
            status="shadow",
        )
        db_conn.commit()
        return {
            "status": "shadow",
            "message": "shadow_mode_active",
            "trace_id": trace_id,
        }

    # Button-only mode
    if nlu_result.status == "button_only":
        _write_sla(
            db_conn, trace_id, employee_id, None, config,
            parse_duration_ms=parse_ms,
            total_duration_ms=_ms(t_total_start),
            status="button_only",
        )
        db_conn.commit()
        return {
            "status": "button_only",
            "message": "nlu_disabled_use_commands",
            "trace_id": trace_id,
        }

    # Fallback / low confidence
    if nlu_result.status == "fallback":
        intent_type = nlu_result.parsed.intent_type if nlu_result.parsed else None
        _write_sla(
            db_conn, trace_id, employee_id, intent_type, config,
            parse_duration_ms=parse_ms,
            total_duration_ms=_ms(t_total_start),
            status="fallback",
        )
        db_conn.commit()
        return {
            "status": "fallback",
            "message": "intent_unclear_use_commands",
            "trace_id": trace_id,
        }

    # NLU ok — store confirmation pending INV-MBC
    parsed = nlu_result.parsed
    confirmation_id = store_confirmation(
        db_conn,
        trace_id=trace_id,
        employee_id=employee_id,
        employee_role=employee_role,
        parsed=parsed,
    )

    _write_sla(
        db_conn, trace_id, employee_id, parsed.intent_type, config,
        parse_duration_ms=parse_ms,
        total_duration_ms=_ms(t_total_start),
        status="ok",
    )
    db_conn.commit()

    from domain.assistant_models import build_confirm_buttons, INTENT_LABELS
    label = INTENT_LABELS.get(parsed.intent_type, parsed.intent_type)

    return {
        "status": "needs_confirmation",
        "confirmation_id": confirmation_id,
        "intent_type": parsed.intent_type,
        "intent_label": label,
        "entities": dict(parsed.entities),
        "confidence": parsed.confidence,
        "reply_markup": build_confirm_buttons(confirmation_id, parsed.intent_type),
        "trace_id": trace_id,
    }


# ---------------------------------------------------------------------------
# confirm_nlu_intent  (nlu_confirm callback)
# ---------------------------------------------------------------------------


def confirm_nlu_intent(
    payload: Dict[str, Any],
    db_conn: Any,
    payment_adapter: Any = None,
    shipment_adapter: Any = None,
) -> Dict[str, Any]:
    """
    Handle nlu_confirm:<id> callback — atomically consume confirmation
    and route to backoffice_router.

    Expected payload keys:
      trace_id            (required)
      confirmation_id     (required)
      employee_id         (for audit)
      employee_role       (for audit)

    Returns same shape as route_backoffice_intent().
    """
    t_total_start = time.monotonic()

    trace_id = _extract_trace_id(payload)
    if not trace_id:
        return _policy_violation("", "trace_id is required and must be non-empty")

    confirmation_id = str(payload.get("confirmation_id") or "")
    if not confirmation_id:
        return _policy_violation(trace_id, "confirmation_id is required")

    # Atomic consume — INV-MBC enforced here
    pending = get_and_consume(db_conn, confirmation_id)
    if pending is None:
        db_conn.commit()
        return {
            "status": "error",
            "error_class": "PERMANENT",
            "severity": "WARNING",
            "retriable": False,
            "error": "confirmation_not_found_or_expired",
            "confirmation_id": confirmation_id,
            "invariant": "INV-MBC",
            "trace_id": trace_id,
        }

    # Guardian: INV-MBC — confirmation must not be bypassed
    try:
        guard_nlu_confirmation(pending)
    except GuardianVeto as veto:
        db_conn.commit()
        return {
            "status": "forbidden",
            "error_class": "PERMANENT",
            "severity": "ERROR",
            "retriable": False,
            "error": veto.reason,
            "invariant": veto.invariant,
            "trace_id": trace_id,
        }

    # send_invoice is recognized but execution is not yet implemented
    if pending.parsed_intent_type == "send_invoice":
        db_conn.commit()
        return {
            "status": "not_implemented",
            "error_class": "PERMANENT",
            "severity": "WARNING",
            "retriable": False,
            "error": "send_invoice_execution_not_implemented_yet",
            "intent_type": "send_invoice",
            "trace_id": trace_id,
        }

    # Route to backoffice_router
    from ru_worker.backoffice_router import route_backoffice_intent  # type: ignore

    backoffice_payload = {
        "trace_id": pending.trace_id,
        "intent_type": pending.parsed_intent_type,
        "employee_id": pending.employee_id,
        "employee_role": pending.employee_role,
        "payload": dict(pending.parsed_entities),
        "metadata": {
            "nlu": {
                "confirmation_id": pending.confirmation_id,
                "model_version": pending.model_version,
                "prompt_version": pending.prompt_version,
                "confidence": pending.confidence,
            }
        },
    }

    result = route_backoffice_intent(
        backoffice_payload,
        db_conn,
        payment_adapter=payment_adapter,
        shipment_adapter=shipment_adapter,
    )
    # route_backoffice_intent commits internally; no second commit here
    result["nlu_confirmed"] = True
    result["confirmation_id"] = confirmation_id
    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _ms(t_start: float) -> int:
    return max(0, int((time.monotonic() - t_start) * 1000))


def _write_sla(
    db_conn: Any,
    trace_id: str,
    employee_id: str,
    intent_type: Optional[str],
    config: NLUConfig,
    *,
    parse_duration_ms: int,
    total_duration_ms: int,
    status: str,
) -> None:
    record_nlu_sla(
        db_conn,
        trace_id=trace_id,
        employee_id=employee_id,
        intent_type=intent_type,
        model_version=config.model_version,
        prompt_version=config.prompt_version,
        degradation_level=config.degradation_level,
        parse_duration_ms=parse_duration_ms,
        total_duration_ms=total_duration_ms,
        status=status,
    )

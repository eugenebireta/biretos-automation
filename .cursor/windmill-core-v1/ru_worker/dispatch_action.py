#!/usr/bin/env python3
"""
Dispatch Action для Windmill
Единая точка для всех side-effects (полная версия без зависимостей от telegram_bot_mvp0.py).
"""

import json
import os
import time
from typing import Any, Dict, Optional

from pydantic import ValidationError

from config import get_config
from commercial_sanity_gate import evaluate_commercial_sanity
from lib_integrations import (
    execute_tbank_payment,
    execute_tbank_invoice_status,
    execute_tbank_invoices_list,
    execute_cdek_shipment,
    map_tbank_invoice_to_cdek_payload,
)
from policy_hash import (
    current_policy_context,
    get_config_snapshot,
    parse_expected_tax_rates,
    upsert_config_snapshot,
)

try:
    from domain.cdm_models import TaskIntent
    from domain.guardian import GuardianVeto, guard_task_intent
except ImportError:
    from .domain.cdm_models import TaskIntent  # type: ignore
    from .domain.guardian import GuardianVeto, guard_task_intent  # type: ignore

try:
    from idempotency import (
        acquire_action_lock,
        complete_action,
        compute_request_hash,
        generate_idempotency_key,
    )
except ImportError:
    from .idempotency import (  # type: ignore
        acquire_action_lock,
        complete_action,
        compute_request_hash,
        generate_idempotency_key,
    )

_CONFIG = get_config()
ACTION_MODE = _CONFIG.action_mode or "REAL"
EXECUTION_MODE = (_CONFIG.execution_mode or "LIVE").upper()


def _resolve_action_idempotency_ttl_seconds() -> int:
    """
    Global TTL for action locks in action_idempotency_log.

    Config:
      - ACTION_IDEMPOTENCY_TTL_SECONDS (int)
      - default: 300
      - bounds: 30..3600 (clamped)
    """
    raw = (os.getenv("ACTION_IDEMPOTENCY_TTL_SECONDS") or "").strip()
    try:
        ttl = int(raw)
    except Exception:
        ttl = 300

    if ttl < 30:
        return 30
    if ttl > 3600:
        return 3600
    return ttl


def log_event(event: str, data: Dict[str, Any]) -> None:
    """Structured logging в stdout."""
    log_entry = {"event": event, "timestamp": time.time(), **data}
    print(json.dumps(log_entry), flush=True)


def _next_decision_seq(db_conn, trace_id: Optional[str]) -> int:
    if not trace_id:
        return 1
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
        return int(cursor.fetchone()[0])
    finally:
        cursor.close()


def _write_control_decision(
    db_conn,
    *,
    trace_id: Optional[str],
    gate_name: str,
    verdict: str,
    schema_version: str,
    policy_hash: str,
    decision_context: Optional[Dict[str, Any]] = None,
    reference_snapshot: Optional[Dict[str, Any]] = None,
    replay_config_status: Optional[str] = None,
) -> None:
    if db_conn is None:
        return
    cursor = db_conn.cursor()
    try:
        decision_seq = _next_decision_seq(db_conn, trace_id)
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
                schema_version,
                policy_hash,
                json.dumps(decision_context or {}, ensure_ascii=False),
                json.dumps(reference_snapshot or {}, ensure_ascii=False),
                replay_config_status,
            ),
        )
    finally:
        cursor.close()


def _resolve_gate_config_values() -> Dict[str, Any]:
    return {
        "MAX_INPUT_SIZE_BYTES": _CONFIG.max_input_size_bytes,
        "MAX_PRICE_DEVIATION": _CONFIG.max_price_deviation,
        "ROUNDING_TOLERANCE": _CONFIG.rounding_tolerance,
        "expected_tax_rates": parse_expected_tax_rates(_CONFIG.expected_tax_rates),
    }


def _extract_tracking_from_cdek_result(cdek_result: Dict[str, Any]) -> str:
    cdek_response = cdek_result.get("response", {})
    return (
        cdek_response.get("entity", {}).get("uuid")
        or (
            cdek_response.get("requests", [{}])[0].get("request_uuid")
            if cdek_response.get("requests")
            else None
        )
        or cdek_response.get("uuid")
        or cdek_response.get("tracking_number")
        or cdek_response.get("number")
        or "N/A"
    )


def _dispatch_dry_run(
    action_type: str,
    payload: Dict[str, Any],
    source: str,
    mode: str,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    # Логирование намерения
    log_event(
        "action_dispatched",
        {
            "action_type": action_type,
            "mode": mode,
            "source": source,
            "payload": payload,
            "metadata": metadata,
        },
    )

    # Только логирование, никаких реальных вызовов
    if action_type == "tbank_invoices_list":
        fake_invoices = [
            {"invoice_id": "INV-001", "status": "paid"},
            {"invoice_id": "INV-002", "status": "unpaid"},
            {"invoice_id": "INV-003", "status": "paid"},
            {"invoice_id": "INV-004", "status": "unpaid"},
            {"invoice_id": "INV-005", "status": "paid"},
        ]
        return {"status": "success", "action_type": action_type, "invoices": fake_invoices}
    if action_type == "ship_paid":
        invoice_id = payload.get("invoice_id", "")
        fake_tracking_number = f"TEST-{int(time.time()) % 100000}"
        log_event(
            "ship_paid_requested",
            {"action_type": action_type, "mode": mode, "source": source, "invoice_id": invoice_id},
        )
        return {
            "status": "success",
            "action_type": action_type,
            "tracking_number": fake_tracking_number,
            "dry_run": True,
        }
    if action_type == "cdek_shipment":
        invoice_id = payload.get("invoice_id")
        if invoice_id:
            import uuid

            fake_tracking_number = f"TEST-{uuid.uuid4().hex[:5].upper()}"
            log_event(
                "cdek_shipment_requested",
                {
                    "action_type": action_type,
                    "mode": mode,
                    "source": source,
                    "invoice_id": invoice_id,
                },
            )
            return {
                "status": "success",
                "action_type": action_type,
                "tracking_number": fake_tracking_number,
                "dry_run": True,
            }
        return {"status": "dry_run", "action_type": action_type, "message": "Action logged, not executed"}
    if action_type == "auto_ship_all_paid":
        fake_results = [
            {"invoice_id": "INV-001", "status": "success", "tracking": "TEST-001"},
            {"invoice_id": "INV-003", "status": "success", "tracking": "TEST-003"},
            {"invoice_id": "INV-005", "status": "success", "tracking": "TEST-005"},
        ]
        log_event("auto_ship_all_paid_requested", {"action_type": action_type, "mode": mode, "source": source})
        return {
            "status": "success",
            "action_type": action_type,
            "dry_run": True,
            "processed_count": len(fake_results),
            "success_count": len(fake_results),
            "results": fake_results,
        }

    return {"status": "dry_run", "action_type": action_type, "message": "Action logged, not executed"}


def _dispatch_real(
    action_type: str,
    payload: Dict[str, Any],
    source: str,
    metadata: Dict[str, Any],
    mode: str,
    db_conn=None,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    # Реальное выполнение для tbank_payment
    if action_type == "tbank_payment":
        try:
            result = execute_tbank_payment(_CONFIG, payload)
            if result.get("status") == "success":
                log_event(
                    "action_real_executed",
                    {"action_type": action_type, "mode": mode, "source": source, "result": result},
                )
                return {"status": "success", "action_type": action_type, "result": result}
            log_event(
                "action_real_failed",
                {
                    "action_type": action_type,
                    "mode": mode,
                    "source": source,
                    "error": result.get("error", "Unknown error"),
                },
            )
            return {
                "status": "error",
                "action_type": action_type,
                "error": result.get("error", "Unknown error"),
            }
        except Exception as e:
            log_event(
                "action_real_failed",
                {"action_type": action_type, "mode": mode, "source": source, "error": str(e)},
            )
            return {"status": "error", "action_type": action_type, "error": str(e)}

    # Реальное выполнение для cdek_shipment
    if action_type == "cdek_shipment":
        try:
            invoice_id = payload.get("invoice_id")
            if invoice_id:
                # Шаг 1: Проверка статуса счёта в T-Bank
                invoice_status_result = execute_tbank_invoice_status(_CONFIG, {"invoice_id": invoice_id})
                if invoice_status_result.get("status") != "success":
                    log_event(
                        "action_real_failed",
                        {
                            "action_type": action_type,
                            "mode": mode,
                            "source": source,
                            "invoice_id": invoice_id,
                            "error": invoice_status_result.get("error", "Failed to check invoice status"),
                        },
                    )
                    return {
                        "status": "error",
                        "action_type": action_type,
                        "error": invoice_status_result.get("error", "Failed to check invoice status"),
                    }
                result_status = invoice_status_result.get("result_status", "unknown")
                # Шаг 2: Проверка, что счёт оплачен
                if result_status != "paid":
                    log_event(
                        "action_real_blocked_not_paid",
                        {
                            "action_type": action_type,
                            "mode": mode,
                            "source": source,
                            "invoice_id": invoice_id,
                            "invoice_status": result_status,
                        },
                    )
                    return {"status": "not_paid", "action_type": action_type, "invoice_status": result_status}

                # Шаг 3: Счёт оплачен - создаём CDEK shipment
                invoice_response = invoice_status_result.get("response", {})
                cdek_payload, mapping_error = map_tbank_invoice_to_cdek_payload(_CONFIG, invoice_id, invoice_response)
                if mapping_error:
                    log_event(
                        "action_real_failed",
                        {
                            "action_type": action_type,
                            "mode": mode,
                            "source": source,
                            "invoice_id": invoice_id,
                            "error": f"Data mapping failed: {mapping_error}",
                        },
                    )
                    return {
                        "status": "error",
                        "action_type": action_type,
                        "error": f"Data mapping failed: {mapping_error}",
                    }
                # Вызов CDEK shipment
                result = execute_cdek_shipment(_CONFIG, cdek_payload)
            else:
                # Обычный cdek_shipment с полным payload
                result = execute_cdek_shipment(_CONFIG, payload)

            if result.get("status") == "success":
                log_event(
                    "action_real_executed",
                    {"action_type": action_type, "mode": mode, "source": source, "result": result},
                )
                return {"status": "success", "action_type": action_type, "result": result}
            log_event(
                "action_real_failed",
                {
                    "action_type": action_type,
                    "mode": mode,
                    "source": source,
                    "error": result.get("error", "Unknown error"),
                },
            )
            return {"status": "error", "action_type": action_type, "error": result.get("error", "Unknown error")}
        except Exception as e:
            log_event(
                "action_real_failed",
                {"action_type": action_type, "mode": mode, "source": source, "error": str(e)},
            )
            return {"status": "error", "action_type": action_type, "error": str(e)}

    # Реальное выполнение для tbank_invoice_status
    if action_type == "tbank_invoice_status":
        try:
            result = execute_tbank_invoice_status(_CONFIG, payload)
            invoice_id = payload.get("invoice_id", "")
            if result.get("status") == "success":
                log_event(
                    "action_real_executed",
                    {
                        "action_type": action_type,
                        "mode": mode,
                        "source": source,
                        "invoice_id": invoice_id,
                        "result_status": result.get("result_status", "unknown"),
                    },
                )
                return {"status": "success", "action_type": action_type, "result": result}
            log_event(
                "action_real_failed",
                {
                    "action_type": action_type,
                    "mode": mode,
                    "source": source,
                    "invoice_id": invoice_id,
                    "error": result.get("error", "Unknown error"),
                },
            )
            return {"status": "error", "action_type": action_type, "error": result.get("error", "Unknown error")}
        except Exception as e:
            invoice_id = payload.get("invoice_id", "")
            log_event(
                "action_real_failed",
                {
                    "action_type": action_type,
                    "mode": mode,
                    "source": source,
                    "invoice_id": invoice_id,
                    "error": str(e),
                },
            )
            return {"status": "error", "action_type": action_type, "error": str(e)}

    # Реальное выполнение для tbank_invoices_list
    if action_type == "tbank_invoices_list":
        try:
            invoice_ids = payload.get("invoice_ids", [])
            if invoice_ids:
                invoices = []
                for invoice_id in invoice_ids:
                    status_result = execute_tbank_invoice_status(_CONFIG, {"invoice_id": invoice_id})
                    result_status = status_result.get("result_status", "error")
                    invoices.append({"invoice_id": invoice_id, "status": result_status})
                log_event(
                    "action_real_executed",
                    {
                        "action_type": action_type,
                        "mode": mode,
                        "source": source,
                        "invoices_count": len(invoices),
                    },
                )
                return {"status": "success", "action_type": action_type, "invoices": invoices}

            invoices_result = execute_tbank_invoices_list(_CONFIG, payload)
            if invoices_result.get("status") == "success":
                log_event(
                    "action_real_executed",
                    {
                        "action_type": action_type,
                        "mode": mode,
                        "source": source,
                        "invoices_count": len(invoices_result.get("invoices", [])),
                    },
                )
                return {
                    "status": "success",
                    "action_type": action_type,
                    "invoices": invoices_result.get("invoices", []),
                }
            log_event(
                "action_real_failed",
                {
                    "action_type": action_type,
                    "mode": mode,
                    "source": source,
                    "error": invoices_result.get("error", "Unknown error"),
                },
            )
            return {
                "status": "error",
                "action_type": action_type,
                "error": invoices_result.get("error", "Unknown error"),
            }
        except Exception as e:
            log_event(
                "action_real_failed",
                {"action_type": action_type, "mode": mode, "source": source, "error": str(e)},
            )
            return {"status": "error", "action_type": action_type, "error": str(e)}

    # Реальное выполнение для ship_paid
    if action_type == "ship_paid":
        try:
            invoice_id = payload.get("invoice_id", "")
            # Шаг 1: Проверка статуса счёта в T-Bank
            invoice_status_result = execute_tbank_invoice_status(_CONFIG, {"invoice_id": invoice_id})
            if invoice_status_result.get("status") != "success":
                log_event(
                    "action_real_failed",
                    {
                        "action_type": action_type,
                        "mode": mode,
                        "source": source,
                        "invoice_id": invoice_id,
                        "error": invoice_status_result.get("error", "Failed to check invoice status"),
                    },
                )
                return {
                    "status": "error",
                    "action_type": action_type,
                    "error": invoice_status_result.get("error", "Failed to check invoice status"),
                }
            result_status = invoice_status_result.get("result_status", "unknown")

            # Шаг 2: Проверка, что счёт оплачен
            if result_status != "paid":
                log_event(
                    "action_real_blocked_not_paid",
                    {
                        "action_type": action_type,
                        "mode": mode,
                        "source": source,
                        "invoice_id": invoice_id,
                        "invoice_status": result_status,
                    },
                )
                return {"status": "not_paid", "action_type": action_type, "invoice_status": result_status}

            # Шаг 3: Счёт оплачен - создаём CDEK shipment
            invoice_response = invoice_status_result.get("response", {})
            cdek_payload, mapping_error = map_tbank_invoice_to_cdek_payload(_CONFIG, invoice_id, invoice_response)
            if mapping_error:
                log_event(
                    "action_real_failed",
                    {
                        "action_type": action_type,
                        "mode": mode,
                        "source": source,
                        "invoice_id": invoice_id,
                        "error": f"Data mapping failed: {mapping_error}",
                    },
                )
                return {
                    "status": "error",
                    "action_type": action_type,
                    "error": f"Data mapping failed: {mapping_error}",
                }

            cdek_result = execute_cdek_shipment(_CONFIG, cdek_payload)
            if cdek_result.get("status") == "success":
                tracking_number = _extract_tracking_from_cdek_result(cdek_result)
                log_event(
                    "ship_paid_success",
                    {
                        "invoice_id": invoice_id,
                        "user_id": metadata.get("user_id"),
                        "chat_id": metadata.get("chat_id"),
                        "tracking_number": tracking_number,
                        "dry_run": False,
                    },
                )
                return {"status": "success", "action_type": action_type, "result": cdek_result}

            error_msg = cdek_result.get("error", "CDEK shipment failed")
            log_event(
                "ship_paid_failed",
                {
                    "invoice_id": invoice_id,
                    "user_id": metadata.get("user_id"),
                    "chat_id": metadata.get("chat_id"),
                    "error": error_msg,
                },
            )
            return {
                "status": "error",
                "action_type": action_type,
                "error": cdek_result.get("error", "CDEK shipment failed"),
            }
        except Exception as e:
            invoice_id = payload.get("invoice_id", "")
            log_event(
                "action_real_failed",
                {
                    "action_type": action_type,
                    "mode": mode,
                    "source": source,
                    "invoice_id": invoice_id,
                    "error": str(e),
                },
            )
            return {"status": "error", "action_type": action_type, "error": str(e)}

    # Реальное выполнение для auto_ship_all_paid
    if action_type == "auto_ship_all_paid":
        try:
            invoices_result = execute_tbank_invoices_list(_CONFIG, {"limit": 50})
            if invoices_result.get("status") != "success":
                return {
                    "status": "error",
                    "action_type": action_type,
                    "error": f"Failed to get invoices: {invoices_result.get('error')}",
                }

            invoices = invoices_result.get("invoices", [])
            paid_invoices = [inv for inv in invoices if inv.get("status") == "paid"]
            if not paid_invoices:
                return {
                    "status": "success",
                    "action_type": action_type,
                    "processed_count": 0,
                    "success_count": 0,
                    "message": "Нет оплаченных счетов для обработки",
                    "results": [],
                }

            # Fan-out: каждый invoice обрабатывается через ship_paid, без прямого CDEK вызова здесь.
            results = []
            for invoice in paid_invoices:
                invoice_id = invoice.get("invoice_id")
                if not invoice_id:
                    continue

                ship_action = {
                    "action_type": "ship_paid",
                    "payload": {"invoice_id": invoice_id},
                    "source": f"{source}:auto_ship_all_paid",
                    "metadata": metadata,
                }
                ship_result = dispatch_action(ship_action, mode=mode, db_conn=db_conn, trace_id=trace_id)

                if ship_result.get("status") == "success":
                    tracking = _extract_tracking_from_cdek_result(ship_result.get("result", {}))
                    results.append({"invoice_id": invoice_id, "status": "success", "tracking": tracking})
                elif ship_result.get("status") == "not_paid":
                    results.append({"invoice_id": invoice_id, "status": "skipped", "reason": "not_paid"})
                elif ship_result.get("status") == "duplicate":
                    results.append(
                        {
                            "invoice_id": invoice_id,
                            "status": "duplicate",
                            "reason": ship_result.get("duplicate_status", "processing"),
                            "error": ship_result.get("error"),
                        }
                    )
                else:
                    results.append(
                        {
                            "invoice_id": invoice_id,
                            "status": "error",
                            "error": ship_result.get("error", "Unknown error"),
                        }
                    )

            success_count = len([r for r in results if r.get("status") == "success"])
            log_event(
                "auto_ship_all_paid_completed",
                {
                    "action_type": action_type,
                    "mode": mode,
                    "source": source,
                    "processed_count": len(results),
                    "success_count": success_count,
                },
            )
            return {
                "status": "success",
                "action_type": action_type,
                "processed_count": len(results),
                "success_count": success_count,
                "results": results,
            }
        except Exception as e:
            log_event(
                "action_real_failed",
                {"action_type": action_type, "mode": mode, "source": source, "error": str(e)},
            )
            return {"status": "error", "action_type": action_type, "error": str(e)}

    # Блокировка для всех прочих action_type
    log_event("action_real_blocked", {"action_type": action_type, "mode": mode, "source": source})
    return {"status": "blocked", "action_type": action_type, "message": "REAL mode not implemented"}


def dispatch_action(
    action: Dict[str, Any],
    mode: Optional[str] = None,
    db_conn=None,
    trace_id: Optional[str] = None,
    execution_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Единая точка для всех side-effects.

    Args:
        action: Action dict с action_type, payload, source, metadata
        mode: "DRY_RUN" (по умолчанию) или "REAL"
        db_conn: DB connection required for guarded REAL actions
        trace_id: Optional trace_id propagated by caller

    Returns:
        dict: Результат выполнения (в DRY_RUN - только логирование)
    """
    # ── B1 (Task 5.2): validate inbound action as TaskIntent ──────────────────
    # Merge best available trace_id into validation input so the model can
    # enforce non-empty trace_id even when it is supplied as a kwarg.
    _trace = (
        trace_id
        or (action.get("metadata") or {}).get("trace_id")
        or action.get("trace_id")
    )
    _validation_input: Dict[str, Any] = dict(action)
    if _trace and "trace_id" not in _validation_input:
        _validation_input["trace_id"] = _trace
    try:
        _intent = TaskIntent.model_validate(_validation_input)
    except ValidationError as _exc:
        # 5.3: structured validation-error log at decision boundary
        log_event(
            "validation_error",
            {
                "boundary": "dispatch_action",
                "error_class": "POLICY_VIOLATION",
                "severity": "ERROR",
                "retriable": False,
                "detail": str(_exc),
            },
        )
        return {
            "status": "error",
            "error": "invalid_task_intent",
            "error_class": "POLICY_VIOLATION",
        }
    # ── B1 (Task 5.4): Guardian invariant check ───────────────────────────────
    try:
        guard_task_intent(_intent)
    except GuardianVeto as _veto:
        log_event(
            "guardian_veto",
            {
                "boundary": "dispatch_action",
                "error_class": "POLICY_VIOLATION",
                "severity": "ERROR",
                "retriable": False,
                "invariant": _veto.invariant,
                "reason": _veto.reason,
            },
        )
        return {
            "status": "error",
            "error": "guardian_veto",
            "error_class": "POLICY_VIOLATION",
            "reason": _veto.reason,
        }
    # ─────────────────────────────────────────────────────────────────────────

    if mode is None:
        mode = ACTION_MODE
    if execution_mode is None:
        execution_mode = EXECUTION_MODE
    execution_mode = execution_mode.upper()

    action_type = action.get("action_type")
    payload = action.get("payload", {})
    source = action.get("source", "unknown")
    metadata = action.get("metadata", {})
    effective_trace_id = trace_id or metadata.get("trace_id")

    if mode == "DRY_RUN":
        return _dispatch_dry_run(action_type, payload, source, mode, metadata)

    if mode != "REAL":
        return {"status": "error", "error": f"Unknown mode: {mode}"}

    idempotency_key = generate_idempotency_key(action)
    lease_token: Optional[str] = None
    lock_status: Optional[str] = None

    if idempotency_key is None:
        log_event(
            "action_idempotency_skipped",
            {
                "action_type": action_type,
                "mode": mode,
                "reason": "no_idempotency_key",
                "trace_id": effective_trace_id,
            },
        )
    else:
        if db_conn is None:
            raise RuntimeError("REAL mode requires db_conn for idempotent actions")

        request_hash = compute_request_hash(action_type, payload)
        ttl_seconds = _resolve_action_idempotency_ttl_seconds()
        lock_result = acquire_action_lock(
            db_conn=db_conn,
            idempotency_key=idempotency_key,
            action_type=action_type,
            request_hash=request_hash,
            trace_id=effective_trace_id,
            ttl_seconds=ttl_seconds,
        )
        lock_status = lock_result.get("status")

        if lock_status in {"ACQUIRED", "STALE_TAKEOVER"}:
            lease_token = lock_result.get("lease_token")
        elif lock_status == "DUPLICATE_SUCCEEDED":
            cached_result = lock_result.get("result_ref")
            if isinstance(cached_result, dict):
                return cached_result
            return {"status": "success", "action_type": action_type, "result": cached_result}
        elif lock_status == "DUPLICATE_FAILED":
            return {
                "status": "duplicate",
                "action_type": action_type,
                "duplicate_status": "failed",
                "error": lock_result.get("last_error"),
            }
        elif lock_status == "DUPLICATE_PROCESSING":
            return {
                "status": "duplicate",
                "action_type": action_type,
                "duplicate_status": "processing",
                "message": "Action already processing",
            }
        else:
            raise RuntimeError(f"Unknown acquire_action_lock status: {lock_status}")

    policy_context = current_policy_context(_CONFIG)
    current_policy_hash = policy_context["policy_hash"]

    if db_conn is not None:
        try:
            upsert_config_snapshot(db_conn, current_policy_hash, policy_context["policy_inputs"])
        except Exception as snapshot_error:
            log_event(
                "config_snapshot_write_failed",
                {
                    "action_type": action_type,
                    "policy_hash": current_policy_hash,
                    "error": str(snapshot_error),
                },
            )

    replay_policy_hash = metadata.get("policy_hash") or action.get("policy_hash")
    replay_config_snapshot = None
    replay_config_status: Optional[str] = None

    if execution_mode == "REPLAY":
        if db_conn is not None and replay_policy_hash:
            replay_config_snapshot = get_config_snapshot(db_conn, str(replay_policy_hash))
        if replay_config_snapshot is None:
            replay_config_status = "REPLAY_CONFIG_UNAVAILABLE"

    gate_config_values = _resolve_gate_config_values()
    if replay_config_snapshot:
        csg_cfg = replay_config_snapshot.get("csg_config", {})
        gate_config_values["MAX_PRICE_DEVIATION"] = csg_cfg.get(
            "MAX_PRICE_DEVIATION", gate_config_values["MAX_PRICE_DEVIATION"]
        )
        gate_config_values["ROUNDING_TOLERANCE"] = csg_cfg.get(
            "ROUNDING_TOLERANCE", gate_config_values["ROUNDING_TOLERANCE"]
        )
        gate_config_values["expected_tax_rates"] = replay_config_snapshot.get(
            "expected_tax_rates", gate_config_values["expected_tax_rates"]
        )

    csg_verdict = evaluate_commercial_sanity(
        action,
        config_values=gate_config_values,
        execution_mode=execution_mode,
        replay_config_snapshot=replay_config_snapshot,
    )
    replay_config_status = replay_config_status or csg_verdict.details.get("replay_config_status")

    if db_conn is not None:
        try:
            _write_control_decision(
                db_conn,
                trace_id=effective_trace_id,
                gate_name="commercial_sanity",
                verdict=csg_verdict.verdict,
                schema_version=_CONFIG.gate_chain_version,
                policy_hash=str(replay_policy_hash or current_policy_hash),
                decision_context={
                    "reason": csg_verdict.reason,
                    "details": csg_verdict.details,
                    "execution_mode": execution_mode,
                },
                reference_snapshot=csg_verdict.details.get("reference_price_snapshot"),
                replay_config_status=replay_config_status,
            )
        except Exception as decision_error:
            log_event(
                "control_decision_write_failed",
                {
                    "action_type": action_type,
                    "gate_name": "commercial_sanity",
                    "error": str(decision_error),
                    "trace_id": effective_trace_id,
                },
            )

    result: Dict[str, Any]
    if execution_mode != "REPLAY" and csg_verdict.verdict == "REJECT":
        result = {
            "status": "error",
            "action_type": action_type,
            "error": csg_verdict.reason,
            "details": csg_verdict.details,
        }
    elif execution_mode != "REPLAY" and csg_verdict.verdict == "NEEDS_HUMAN":
        result = {
            "status": "pending_approval",
            "action_type": action_type,
            "reason": csg_verdict.reason,
            "details": csg_verdict.details,
        }
    else:
        try:
            result = _dispatch_real(
                action_type=action_type,
                payload=payload,
                source=source,
                metadata=metadata,
                mode=mode,
                db_conn=db_conn,
                trace_id=effective_trace_id,
            )
        except Exception as e:
            if idempotency_key and lease_token:
                try:
                    complete_action(
                        db_conn=db_conn,
                        idempotency_key=idempotency_key,
                        lease_token=lease_token,
                        status="failed",
                        result_ref=None,
                        last_error=str(e),
                    )
                except Exception as complete_error:
                    log_event(
                        "action_complete_failed",
                        {
                            "action_type": action_type,
                            "idempotency_key": idempotency_key,
                            "lock_status": lock_status,
                            "error": str(complete_error),
                        },
                    )
            return {"status": "error", "action_type": action_type, "error": str(e)}

    if idempotency_key and lease_token:
        completion_status = "succeeded" if result.get("status") in {"success", "pending_approval"} else "failed"
        completion_error = None if completion_status == "succeeded" else result.get("error")
        complete_action(
            db_conn=db_conn,
            idempotency_key=idempotency_key,
            lease_token=lease_token,
            status=completion_status,
            result_ref=result if completion_status == "succeeded" else None,
            last_error=completion_error,
        )
    return result


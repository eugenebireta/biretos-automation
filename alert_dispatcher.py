"""
alert_dispatcher.py — Orchestrator-level alert dispatcher.

Dispatches structured WARNING/ERROR/INFO alerts from orchestrator modules.
No live API calls. No Telegram in this module.
No secrets logged. trace_id required on every call.

Architecture:
  - dispatch() is the sole public entry point
  - _dispatch_fn is injectable for deterministic testing (patch it in tests)
  - Default sink: Python structured logger
  - error_class / severity / retriable on every payload (CLAUDE.md §6)
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Injectable dispatch function — replaced in tests via monkeypatching.
# When None, dispatch() falls back to the structured logger.
_dispatch_fn: Optional[Callable[..., None]] = None


def dispatch(
    *,
    trace_id: str,
    intent_type: str,
    error_summary: str,
    level: str = "WARNING",
) -> None:
    """
    Dispatch a validation alert.

    Parameters:
        trace_id      Trace ID from the originating operation.
        intent_type   Type of intent or action that failed validation.
        error_summary Human-readable summary of Pydantic validation errors.
        level         Alert level: WARNING | ERROR | INFO

    When _dispatch_fn is set (e.g., in tests), it is called with all keyword
    args instead of logging.  This allows fully deterministic test assertions
    without live side-effects.
    """
    payload: Dict[str, Any] = {
        "trace_id": trace_id,
        "intent_type": intent_type,
        "error_summary": error_summary,
        "level": level,
        "error_class": "PERMANENT",
        "severity": level,
        "retriable": False,
    }

    if _dispatch_fn is not None:
        _dispatch_fn(**payload)
        return

    log_fn = {
        "WARNING": logger.warning,
        "ERROR": logger.error,
        "INFO": logger.info,
    }.get(level.upper(), logger.warning)

    log_fn(
        "alert_dispatcher.dispatch intent_type=%s trace_id=%s error=%s",
        intent_type,
        trace_id,
        error_summary,
        extra=payload,
    )

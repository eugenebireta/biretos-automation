"""
guardian.py — Orchestrator-level intent and snapshot guard.

Validates TaskIntent and ActionSnapshot via Pydantic models.
On Pydantic ValidationError, dispatches a WARNING-level alert via
alert_dispatcher.dispatch() and returns None.

Does NOT touch Tier-1 frozen files.
Does NOT import from domain.reconciliation_*.
Does NOT commit inside domain operations.

Every call carries trace_id.  Structured error logging includes
error_class / severity / retriable per CLAUDE.md §6.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, ValidationError

import alert_dispatcher

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TaskIntent(BaseModel):
    """Represents a task intent to be validated before orchestrator execution."""

    trace_id: str
    task_id: str
    intent_type: str
    payload: Dict[str, Any] = {}


class ActionSnapshot(BaseModel):
    """Represents an action snapshot to be validated before mutation."""

    trace_id: str
    action_type: str
    idempotency_key: str
    payload: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def guard_task_intent(raw: Dict[str, Any]) -> Optional[TaskIntent]:
    """
    Validate raw dict as TaskIntent.

    Returns validated TaskIntent on success.
    On Pydantic ValidationError: logs structured WARNING, dispatches alert,
    and returns None.
    """
    trace_id = str(raw.get("trace_id") or "unknown")
    intent_type = str(raw.get("intent_type") or "unknown")
    try:
        return TaskIntent(**raw)
    except ValidationError as exc:
        error_summary = "; ".join(
            f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        logger.warning(
            "guard_task_intent ValidationError trace_id=%s intent_type=%s error=%s",
            trace_id,
            intent_type,
            error_summary,
            extra={
                "trace_id": trace_id,
                "intent_type": intent_type,
                "error_class": "PERMANENT",
                "severity": "WARNING",
                "retriable": False,
            },
        )
        alert_dispatcher.dispatch(
            trace_id=trace_id,
            intent_type=intent_type,
            error_summary=error_summary,
            level="WARNING",
        )
        return None


def guard_action_snapshot(raw: Dict[str, Any]) -> Optional[ActionSnapshot]:
    """
    Validate raw dict as ActionSnapshot.

    Returns validated ActionSnapshot on success.
    On Pydantic ValidationError: logs structured WARNING, dispatches alert,
    and returns None.
    """
    trace_id = str(raw.get("trace_id") or "unknown")
    intent_type = str(raw.get("action_type") or "unknown")
    try:
        return ActionSnapshot(**raw)
    except ValidationError as exc:
        error_summary = "; ".join(
            f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        logger.warning(
            "guard_action_snapshot ValidationError trace_id=%s action_type=%s error=%s",
            trace_id,
            intent_type,
            error_summary,
            extra={
                "trace_id": trace_id,
                "intent_type": intent_type,
                "error_class": "PERMANENT",
                "severity": "WARNING",
                "retriable": False,
            },
        )
        alert_dispatcher.dispatch(
            trace_id=trace_id,
            intent_type=intent_type,
            error_summary=error_summary,
            level="WARNING",
        )
        return None

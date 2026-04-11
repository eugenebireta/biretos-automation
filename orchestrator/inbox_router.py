"""
inbox_router.py — Stream-aware inbox routing (Wave 3).

Classifies inbound messages into three streams:
    COMMAND  — system commands (/status, /ping, /health) → immediate response, no FSM
    QUERY    — free-text questions when not parked → Claude chat, no FSM
    TASK     — /task commands, approve/reject, freetext instructions → FSM pipeline

Each stream has different latency and side-effect characteristics:
    COMMAND  → <1s, read-only
    QUERY    → ~10s (Claude subprocess), read-only
    TASK     → async, mutates manifest FSM

This module is transport-agnostic: it operates on CanonicalEvent-shaped dicts
from owner_inbox.jsonl regardless of source (telegram, max, etc).

Usage:
    from orchestrator.inbox_router import InboxRouter, Stream

    router = InboxRouter()
    result = router.classify(text, manifest)
    # result.stream == Stream.TASK
    # result.input_type == "new_task"
    # result.payload == {"instruction": "..."}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Stream(str, Enum):
    """Inbox message stream classification."""
    COMMAND = "command"   # system commands, read-only, instant
    QUERY = "query"       # chat questions, read-only, Claude response
    TASK = "task"         # FSM-affecting: approve/reject/new_task/freetext


@dataclass(frozen=True)
class RouteResult:
    """Classification result for one inbox message."""
    stream: Stream
    input_type: str
    payload: dict[str, Any] = field(default_factory=dict)


# ── Constants ──────────────────────────────────────────────────────────

APPROVE_WORDS = frozenset({"ок", "ok", "да", "yes", "го", "давай", "продолжай"})
REJECT_WORDS = frozenset({"нет", "no", "стоп", "stop"})
STATUS_COMMANDS = frozenset({"/status", "/ping", "/health"})
TASK_PREFIX = "/task"
MIN_FREETEXT_LEN = 5

PARK_STATES = frozenset({
    "awaiting_owner_reply", "error", "blocked", "blocked_by_consensus",
    "parked_budget_daily", "parked_budget_run", "parked_api_outage",
})


class InboxRouter:
    """Stateless, deterministic inbox classifier.

    Separates message classification from handler execution.
    All classification logic is pure — no I/O, no side-effects.
    """

    def classify(self, text: str, manifest: dict) -> RouteResult:
        """Classify owner message into (stream, input_type, payload).

        Args:
            text: raw message text from inbox
            manifest: current orchestrator manifest (for FSM state)

        Returns:
            RouteResult with stream, input_type, and payload
        """
        lower = text.lower().strip()

        # ── COMMAND stream: system commands ────────────────────────
        if lower in STATUS_COMMANDS:
            return RouteResult(Stream.COMMAND, "status")

        # ── TASK stream: explicit /task prefix ────────────────────
        if lower.startswith(TASK_PREFIX):
            task_text = text[len(TASK_PREFIX):].strip()
            if len(task_text) >= MIN_FREETEXT_LEN:
                return RouteResult(Stream.TASK, "new_task",
                                   {"instruction": task_text})
            return RouteResult(Stream.TASK, "too_short",
                               {"length": len(task_text)})

        fsm_state = manifest.get("fsm_state", "")

        # ── TASK stream: A/B/C decision when pending + parked ─────
        # NOTE: Wave 3 intentionally gates pending_decision on PARK_STATES.
        # Old classify_input() checked pending_decision before PARK_STATES,
        # allowing decisions in any FSM state — that was a latent bug.
        # Decision prompts are only presented when parked (owner interaction).
        if fsm_state in PARK_STATES:
            pending = manifest.get("pending_decision")
            if pending and isinstance(pending, dict):
                options = pending.get("options", {})
                key = text.strip().upper()
                if key in options:
                    return RouteResult(Stream.TASK, "decision",
                                       {"key": key, "text": options[key]})

        # ── TASK stream: parked state → approve/reject/freetext ───
        if fsm_state in PARK_STATES:
            if lower in APPROVE_WORDS:
                return RouteResult(Stream.TASK, "approve")
            if lower in REJECT_WORDS:
                return RouteResult(Stream.TASK, "reject")
            if len(text) >= MIN_FREETEXT_LEN:
                return RouteResult(Stream.TASK, "freetext",
                                   {"instruction": text})
            return RouteResult(Stream.TASK, "too_short",
                               {"length": len(text)})

        # ── QUERY stream: not parked, free text → chat ────────────
        if len(text) >= MIN_FREETEXT_LEN:
            return RouteResult(Stream.QUERY, "chat",
                               {"message": text})

        # ── Edge cases ────────────────────────────────────────────
        if lower in APPROVE_WORDS or lower in REJECT_WORDS:
            return RouteResult(Stream.TASK, "no_pending_state",
                               {"fsm_state": fsm_state})

        return RouteResult(Stream.TASK, "too_short",
                           {"length": len(text)})

    def target_from_source(self, source: str) -> str:
        """Map inbox source to outbox target transport name.

        Examples:
            "telegram_gateway" → "telegram"
            "telegram"         → "telegram"
            "max"              → "max"
            "max_gateway"      → "max"
        """
        if not source:
            return "telegram"
        # removesuffix — only strip '_gateway' at the end, not mid-string
        return source.removesuffix("_gateway")

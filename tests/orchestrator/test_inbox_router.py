"""Tests for orchestrator/inbox_router.py — Wave 3 stream-aware routing."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure orchestrator/ is on sys.path for direct imports
_orch = str(Path(__file__).resolve().parent.parent.parent / "orchestrator")
if _orch not in sys.path:
    sys.path.insert(0, _orch)

from inbox_router import InboxRouter, Stream, RouteResult, PARK_STATES  # noqa: E402


class TestStreamClassification:
    """Verify that messages are assigned to correct streams."""

    def setup_method(self):
        self.router = InboxRouter()
        self.idle_manifest = {"fsm_state": "idle"}
        self.parked_manifest = {"fsm_state": "awaiting_owner_reply"}

    # ── COMMAND stream ─────────────────────────────────────────────

    def test_status_command(self):
        r = self.router.classify("/status", self.idle_manifest)
        assert r.stream == Stream.COMMAND
        assert r.input_type == "status"

    def test_ping_command(self):
        r = self.router.classify("/ping", self.idle_manifest)
        assert r.stream == Stream.COMMAND

    def test_health_command(self):
        r = self.router.classify("/health", self.parked_manifest)
        assert r.stream == Stream.COMMAND
        assert r.input_type == "status"

    def test_status_case_insensitive(self):
        r = self.router.classify("/Status", self.idle_manifest)
        assert r.stream == Stream.COMMAND

    # ── TASK stream: /task prefix ──────────────────────────────────

    def test_task_command(self):
        r = self.router.classify("/task deploy to production", self.idle_manifest)
        assert r.stream == Stream.TASK
        assert r.input_type == "new_task"
        assert r.payload["instruction"] == "deploy to production"

    def test_task_too_short(self):
        r = self.router.classify("/task hi", self.idle_manifest)
        assert r.stream == Stream.TASK
        assert r.input_type == "too_short"

    # ── TASK stream: approve/reject when parked ────────────────────

    def test_approve_when_parked(self):
        r = self.router.classify("ок", self.parked_manifest)
        assert r.stream == Stream.TASK
        assert r.input_type == "approve"

    def test_reject_when_parked(self):
        r = self.router.classify("нет", self.parked_manifest)
        assert r.stream == Stream.TASK
        assert r.input_type == "reject"

    def test_ok_english_when_parked(self):
        r = self.router.classify("ok", self.parked_manifest)
        assert r.stream == Stream.TASK
        assert r.input_type == "approve"

    def test_freetext_when_parked(self):
        r = self.router.classify("пожалуйста используй другой подход",
                                  self.parked_manifest)
        assert r.stream == Stream.TASK
        assert r.input_type == "freetext"
        assert "другой подход" in r.payload["instruction"]

    # ── TASK stream: decision ──────────────────────────────────────

    def test_decision_when_pending(self):
        manifest = {
            "fsm_state": "awaiting_owner_reply",
            "pending_decision": {
                "options": {"A": "Use approach A", "B": "Use approach B"},
            },
        }
        r = self.router.classify("A", manifest)
        assert r.stream == Stream.TASK
        assert r.input_type == "decision"
        assert r.payload["key"] == "A"
        assert r.payload["text"] == "Use approach A"

    def test_non_matching_decision_falls_through(self):
        manifest = {
            "fsm_state": "awaiting_owner_reply",
            "pending_decision": {"options": {"A": "opt A"}},
        }
        r = self.router.classify("ок", manifest)
        assert r.input_type == "approve"  # falls through to approve

    def test_decision_ignored_when_not_parked(self):
        """pending_decision is ignored when fsm_state is not in PARK_STATES."""
        manifest = {
            "fsm_state": "running",
            "pending_decision": {"options": {"A": "opt A", "B": "opt B"}},
        }
        r = self.router.classify("A", manifest)
        # Should NOT be decision — "A" is too short for chat, goes to too_short
        assert r.input_type != "decision"

    # ── QUERY stream: chat when not parked ─────────────────────────

    def test_chat_when_idle(self):
        r = self.router.classify("как работает gateway?", self.idle_manifest)
        assert r.stream == Stream.QUERY
        assert r.input_type == "chat"
        assert r.payload["message"] == "как работает gateway?"

    def test_chat_when_running(self):
        manifest = {"fsm_state": "running"}
        r = self.router.classify("покажи статус задачи", manifest)
        assert r.stream == Stream.QUERY
        assert r.input_type == "chat"

    # ── Edge cases ─────────────────────────────────────────────────

    def test_approve_when_not_parked(self):
        r = self.router.classify("ок", self.idle_manifest)
        assert r.stream == Stream.TASK
        assert r.input_type == "no_pending_state"

    def test_short_text_when_not_parked(self):
        r = self.router.classify("хм", self.idle_manifest)
        assert r.stream == Stream.TASK
        assert r.input_type == "too_short"

    def test_short_text_when_parked(self):
        r = self.router.classify("хм", self.parked_manifest)
        assert r.stream == Stream.TASK
        assert r.input_type == "too_short"


class TestRouteResultImmutability:
    """RouteResult is frozen dataclass — no mutation after creation."""

    def test_frozen(self):
        r = RouteResult(Stream.COMMAND, "status")
        try:
            r.stream = Stream.TASK  # type: ignore[misc]
            assert False, "Should raise FrozenInstanceError"
        except AttributeError:
            pass


class TestParkStates:
    """PARK_STATES is canonical set of FSM states that accept approve/reject."""

    def test_known_park_states(self):
        assert "awaiting_owner_reply" in PARK_STATES
        assert "error" in PARK_STATES
        assert "blocked" in PARK_STATES
        assert "parked_api_outage" in PARK_STATES

    def test_non_park_states(self):
        assert "idle" not in PARK_STATES
        assert "running" not in PARK_STATES
        assert "ready" not in PARK_STATES


class TestAllParkStatesRoute:
    """Every PARK_STATE triggers TASK stream for approve/reject."""

    def setup_method(self):
        self.router = InboxRouter()

    def test_all_park_states_approve(self):
        for state in PARK_STATES:
            manifest = {"fsm_state": state}
            r = self.router.classify("ок", manifest)
            assert r.stream == Stream.TASK, f"Failed for state={state}"
            assert r.input_type == "approve", f"Failed for state={state}"

    def test_all_park_states_reject(self):
        for state in PARK_STATES:
            manifest = {"fsm_state": state}
            r = self.router.classify("нет", manifest)
            assert r.stream == Stream.TASK, f"Failed for state={state}"
            assert r.input_type == "reject", f"Failed for state={state}"


class TestTargetFromSource:
    """Source → target transport name mapping."""

    def setup_method(self):
        self.router = InboxRouter()

    def test_telegram_gateway(self):
        assert self.router.target_from_source("telegram_gateway") == "telegram"

    def test_telegram_direct(self):
        assert self.router.target_from_source("telegram") == "telegram"

    def test_max(self):
        assert self.router.target_from_source("max") == "max"

    def test_max_gateway(self):
        assert self.router.target_from_source("max_gateway") == "max"

    def test_empty_defaults_telegram(self):
        assert self.router.target_from_source("") == "telegram"

    def test_unknown_passthrough(self):
        assert self.router.target_from_source("whatsapp") == "whatsapp"

    def test_gateway_in_middle_not_stripped(self):
        """removesuffix only strips suffix, not mid-string occurrences."""
        assert self.router.target_from_source("gateway_proxy") == "gateway_proxy"

    def test_my_gateway_service_not_mangled(self):
        assert self.router.target_from_source("my_gateway_service") == "my_gateway_service"


class TestBackwardCompatibility:
    """classify_input() in owner_bridge must return same results as before."""

    def setup_method(self):
        self.router = InboxRouter()

    def test_classify_returns_tuple(self):
        """InboxRouter.classify returns RouteResult; bridge wraps as tuple."""
        r = self.router.classify("/status", {"fsm_state": "idle"})
        # Simulate what classify_input() does
        input_type, payload = r.input_type, r.payload
        assert input_type == "status"
        assert payload == {}

    def test_approve_returns_empty_payload(self):
        r = self.router.classify("ок", {"fsm_state": "awaiting_owner_reply"})
        assert r.input_type == "approve"
        assert r.payload == {}

    def test_new_task_returns_instruction(self):
        r = self.router.classify("/task fix the bug in gateway",
                                  {"fsm_state": "idle"})
        assert r.input_type == "new_task"
        assert "fix the bug" in r.payload["instruction"]

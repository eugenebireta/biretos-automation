"""
tests/test_guardian_alert_dispatch.py — Deterministic tests for guardian.py
ValidationError -> alert_dispatcher.dispatch() wiring.

Covers:
  - guard_task_intent: invalid payload triggers dispatch with correct args
  - guard_action_snapshot: invalid payload triggers dispatch with correct args
  - Happy path: valid payloads return models, no dispatch

No live API, no unmocked time/randomness.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import alert_dispatcher
import guardian


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_dispatch(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Inject a mock into alert_dispatcher._dispatch_fn for every test."""
    mock = MagicMock()
    monkeypatch.setattr(alert_dispatcher, "_dispatch_fn", mock)
    return mock


@pytest.fixture()
def dispatch_mock(_patch_dispatch: MagicMock) -> MagicMock:
    """Expose the dispatch mock explicitly when a test needs assertions."""
    return _patch_dispatch


# ---------------------------------------------------------------------------
# guard_task_intent — validation error path
# ---------------------------------------------------------------------------

class TestGuardTaskIntentValidationError:
    """Trigger Pydantic ValidationError and assert alert dispatch."""

    def test_missing_required_fields_dispatches_warning(
        self, dispatch_mock: MagicMock
    ) -> None:
        # payload missing required 'task_id' and 'intent_type'
        result = guardian.guard_task_intent({"trace_id": "t-001"})

        assert result is None
        dispatch_mock.assert_called_once()

        kw = dispatch_mock.call_args.kwargs
        assert kw["trace_id"] == "t-001"
        assert kw["level"] == "WARNING"
        assert "intent_type" in kw
        assert "error_summary" in kw
        assert len(kw["error_summary"]) > 0

    def test_wrong_type_dispatches_warning(
        self, dispatch_mock: MagicMock
    ) -> None:
        # payload has non-dict 'payload' field
        result = guardian.guard_task_intent(
            {
                "trace_id": "t-002",
                "task_id": "TSK-1",
                "intent_type": "exec",
                "payload": "not-a-dict",
            }
        )
        assert result is None
        dispatch_mock.assert_called_once()
        assert dispatch_mock.call_args.kwargs["trace_id"] == "t-002"

    def test_no_trace_id_falls_back_to_unknown(
        self, dispatch_mock: MagicMock
    ) -> None:
        result = guardian.guard_task_intent({})
        assert result is None
        dispatch_mock.assert_called_once()
        assert dispatch_mock.call_args.kwargs["trace_id"] == "unknown"


# ---------------------------------------------------------------------------
# guard_action_snapshot — validation error path
# ---------------------------------------------------------------------------

class TestGuardActionSnapshotValidationError:
    """Trigger Pydantic ValidationError and assert alert dispatch."""

    def test_missing_required_fields_dispatches_warning(
        self, dispatch_mock: MagicMock
    ) -> None:
        # missing 'action_type' and 'idempotency_key'
        result = guardian.guard_action_snapshot({"trace_id": "s-001"})

        assert result is None
        dispatch_mock.assert_called_once()

        kw = dispatch_mock.call_args.kwargs
        assert kw["trace_id"] == "s-001"
        assert kw["level"] == "WARNING"
        assert len(kw["error_summary"]) > 0

    def test_wrong_type_dispatches_warning(
        self, dispatch_mock: MagicMock
    ) -> None:
        result = guardian.guard_action_snapshot(
            {
                "trace_id": "s-002",
                "action_type": "mutate",
                "idempotency_key": "k1",
                "payload": 12345,
            }
        )
        assert result is None
        dispatch_mock.assert_called_once()
        assert dispatch_mock.call_args.kwargs["trace_id"] == "s-002"


# ---------------------------------------------------------------------------
# Happy paths — no dispatch on valid input
# ---------------------------------------------------------------------------

class TestHappyPaths:
    """Valid payloads must return models and NOT trigger dispatch."""

    def test_valid_task_intent(self, dispatch_mock: MagicMock) -> None:
        result = guardian.guard_task_intent(
            {
                "trace_id": "t-ok",
                "task_id": "TSK-9",
                "intent_type": "build",
            }
        )
        assert isinstance(result, guardian.TaskIntent)
        assert result.trace_id == "t-ok"
        dispatch_mock.assert_not_called()

    def test_valid_action_snapshot(self, dispatch_mock: MagicMock) -> None:
        result = guardian.guard_action_snapshot(
            {
                "trace_id": "s-ok",
                "action_type": "deploy",
                "idempotency_key": "key-1",
            }
        )
        assert isinstance(result, guardian.ActionSnapshot)
        assert result.trace_id == "s-ok"
        dispatch_mock.assert_not_called()

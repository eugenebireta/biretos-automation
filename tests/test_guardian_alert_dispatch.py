"""
Tests for orchestrator guardian -> alert_dispatcher ValidationError wiring (STAGE-5.3).

trace_id: orch_20260409T170046Z_cfaeb8
idempotency_key: stage-5.3-guardian-alert-dispatch-test-001

Deterministic unit tests — no live API, no DB, no unmocked time/randomness.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure orchestrator/ is importable (guardian.py does `import alert_dispatcher`)
_orch_dir = str(Path(__file__).resolve().parent.parent / "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)

import pytest

import alert_dispatcher
import guardian


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _capture_dispatch():
    """Returns (list, fn) — fn records kwargs into list."""
    captured: list[dict] = []

    def _fn(**kwargs):
        captured.append(kwargs)

    return captured, _fn


# ---------------------------------------------------------------------------
# guard_task_intent — ValidationError dispatches alert
# ---------------------------------------------------------------------------

class TestGuardTaskIntentValidationAlert:
    def setup_method(self):
        self._original = alert_dispatcher._dispatch_fn

    def teardown_method(self):
        alert_dispatcher._dispatch_fn = self._original

    def test_missing_required_fields_dispatches_warning(self):
        """Missing trace_id/task_id/intent_type → ValidationError → alert dispatched."""
        captured, fn = _capture_dispatch()
        alert_dispatcher._dispatch_fn = fn

        result = guardian.guard_task_intent({"payload": {"x": 1}})

        assert result is None
        assert len(captured) == 1
        alert = captured[0]
        assert alert["level"] == "WARNING"
        assert alert["trace_id"] == "unknown"
        assert alert["intent_type"] == "unknown"
        assert alert["error_summary"]  # non-empty

    def test_partial_fields_captures_trace_id(self):
        """If trace_id is present but other fields missing, trace_id passes through."""
        captured, fn = _capture_dispatch()
        alert_dispatcher._dispatch_fn = fn

        result = guardian.guard_task_intent({
            "trace_id": "test-trace-abc",
            "intent_type": "cdek_shipment",
            # missing task_id → ValidationError
        })

        assert result is None
        assert len(captured) == 1
        assert captured[0]["trace_id"] == "test-trace-abc"
        assert captured[0]["intent_type"] == "cdek_shipment"

    def test_valid_dict_no_alert(self):
        """Valid payload → returns TaskIntent, no alert dispatched."""
        captured, fn = _capture_dispatch()
        alert_dispatcher._dispatch_fn = fn

        result = guardian.guard_task_intent({
            "trace_id": "t1",
            "task_id": "STAGE-1",
            "intent_type": "test",
            "payload": {},
        })

        assert result is not None
        assert result.trace_id == "t1"
        assert len(captured) == 0


# ---------------------------------------------------------------------------
# guard_action_snapshot — ValidationError dispatches alert
# ---------------------------------------------------------------------------

class TestGuardActionSnapshotValidationAlert:
    def setup_method(self):
        self._original = alert_dispatcher._dispatch_fn

    def teardown_method(self):
        alert_dispatcher._dispatch_fn = self._original

    def test_missing_required_fields_dispatches_warning(self):
        """Missing fields → ValidationError → alert dispatched."""
        captured, fn = _capture_dispatch()
        alert_dispatcher._dispatch_fn = fn

        result = guardian.guard_action_snapshot({"payload": {"x": 1}})

        assert result is None
        assert len(captured) == 1
        alert = captured[0]
        assert alert["level"] == "WARNING"
        assert alert["trace_id"] == "unknown"
        assert alert["error_summary"]  # non-empty

    def test_partial_fields_captures_trace_and_action_type(self):
        """trace_id and action_type pass through even on validation failure."""
        captured, fn = _capture_dispatch()
        alert_dispatcher._dispatch_fn = fn

        result = guardian.guard_action_snapshot({
            "trace_id": "snap-trace-1",
            "action_type": "shipment_update",
            # missing idempotency_key → ValidationError
        })

        assert result is None
        assert len(captured) == 1
        assert captured[0]["trace_id"] == "snap-trace-1"
        assert captured[0]["intent_type"] == "shipment_update"

    def test_valid_dict_no_alert(self):
        """Valid payload → returns ActionSnapshot, no alert dispatched."""
        captured, fn = _capture_dispatch()
        alert_dispatcher._dispatch_fn = fn

        result = guardian.guard_action_snapshot({
            "trace_id": "t2",
            "action_type": "shipment_update",
            "idempotency_key": "key-001",
            "payload": {},
        })

        assert result is not None
        assert result.trace_id == "t2"
        assert len(captured) == 0

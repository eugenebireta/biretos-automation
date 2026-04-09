"""
Tests for Guardian -> alert_dispatcher ValidationError wiring (STAGE-5.3).

Deterministic unit tests:
  - No live API, no DB, no unmocked time/randomness
  - Injectable _dispatch_alert_fn for assertion
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_import_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_import_paths()

import pytest
from pydantic import ValidationError

from domain import guardian as g


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _capture_dispatch():
    """Returns (list, fn) — fn records alert dicts into list."""
    captured: list = []

    def _fn(alert_dict):
        captured.append(alert_dict)

    return captured, _fn


# ---------------------------------------------------------------------------
# guard_task_intent — ValidationError dispatches alert
# ---------------------------------------------------------------------------


class TestGuardTaskIntentValidationAlert:
    def setup_method(self):
        self._original = g._dispatch_alert_fn

    def teardown_method(self):
        g._dispatch_alert_fn = self._original

    def test_invalid_dict_dispatches_warning_alert(self):
        captured, fn = _capture_dispatch()
        g._dispatch_alert_fn = fn

        # Missing required fields → ValidationError
        with pytest.raises(ValidationError):
            g.guard_task_intent({"action_type": "cdek_shipment"})

        assert len(captured) == 1
        alert = captured[0]
        assert alert["check_code"] == "GUARDIAN-VALIDATION"
        assert alert["severity"] == "WARNING"
        assert alert["entity_type"] == "guardian"
        assert "TaskIntent" in alert["entity_id"]
        assert "cdek_shipment" in alert["entity_id"]
        assert alert["verdict_snapshot"]["reason"]  # non-empty error summary

    def test_invalid_dict_with_trace_id_passes_trace(self):
        captured, fn = _capture_dispatch()
        g._dispatch_alert_fn = fn

        with pytest.raises(ValidationError):
            g.guard_task_intent({
                "trace_id": "test-trace-abc",
                # missing payload, source → ValidationError
            })

        assert captured[0]["sweep_trace_id"] == "test-trace-abc"

    def test_valid_dict_no_alert_dispatched(self):
        captured, fn = _capture_dispatch()
        g._dispatch_alert_fn = fn

        # Valid dict that passes both validation and guard
        g.guard_task_intent({
            "trace_id": "t1",
            "action_type": "cdek_shipment",
            "payload": {},
            "source": "test",
        })

        assert len(captured) == 0

    def test_valid_model_object_still_works(self):
        """Backward compat: passing a TaskIntent model works as before."""
        from domain.cdm_models import TaskIntent

        captured, fn = _capture_dispatch()
        g._dispatch_alert_fn = fn

        intent = TaskIntent(
            trace_id="t2",
            action_type="cdek_shipment",
            payload={},
            source="test",
        )
        g.guard_task_intent(intent)  # no error, no alert
        assert len(captured) == 0

    def test_no_dispatch_fn_still_raises(self):
        """Without _dispatch_alert_fn wired, ValidationError still propagates."""
        g._dispatch_alert_fn = None

        with pytest.raises(ValidationError):
            g.guard_task_intent({"bad": "data"})


# ---------------------------------------------------------------------------
# guard_action_snapshot — ValidationError dispatches alert
# ---------------------------------------------------------------------------


class TestGuardActionSnapshotValidationAlert:
    def setup_method(self):
        self._original = g._dispatch_alert_fn

    def teardown_method(self):
        g._dispatch_alert_fn = self._original

    def test_invalid_dict_dispatches_warning_alert(self):
        captured, fn = _capture_dispatch()
        g._dispatch_alert_fn = fn

        # Missing required fields → ValidationError
        with pytest.raises(ValidationError):
            g.guard_action_snapshot({"schema_version": 99})

        assert len(captured) == 1
        alert = captured[0]
        assert alert["check_code"] == "GUARDIAN-VALIDATION"
        assert alert["severity"] == "WARNING"
        assert alert["entity_type"] == "guardian"
        assert "ActionSnapshot" in alert["entity_id"]

    def test_valid_dict_no_alert_dispatched(self):
        captured, fn = _capture_dispatch()
        g._dispatch_alert_fn = fn

        g.guard_action_snapshot({
            "schema_version": 1,
            "leaf_worker_type": "cdek_shipment",
            "leaf_payload": {"order_id": 1},
            "external_idempotency_key": "key-123",
        })

        assert len(captured) == 0

    def test_valid_model_object_still_works(self):
        from domain.cdm_models import ActionSnapshot

        captured, fn = _capture_dispatch()
        g._dispatch_alert_fn = fn

        snapshot = ActionSnapshot(
            schema_version=1,
            leaf_worker_type="cdek_shipment",
            leaf_payload={"order_id": 1},
            external_idempotency_key="key-456",
        )
        g.guard_action_snapshot(snapshot)
        assert len(captured) == 0

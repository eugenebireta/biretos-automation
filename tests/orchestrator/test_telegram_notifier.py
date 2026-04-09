"""
test_telegram_notifier.py — Tests for telegram_notifier.py.

Uses injectable _send_fn to avoid real HTTP calls.
Covers: send, notify_park, notify_decision, config-missing no-op.
"""
from __future__ import annotations

import json
import os
import sys


_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)

import telegram_notifier as tn  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Capture:
    """Captures all send calls for assertions."""

    def __init__(self, return_value=True):
        self.calls: list[str] = []
        self._ret = return_value

    def __call__(self, text: str) -> bool:
        self.calls.append(text)
        return self._ret


def _inject(capture: _Capture):
    tn._send_fn = capture


def _reset():
    tn._send_fn = None


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------

class TestSend:
    def setup_method(self):
        _reset()

    def teardown_method(self):
        _reset()

    def test_injectable_called(self):
        cap = _Capture(return_value=True)
        _inject(cap)
        result = tn.send("hello")
        assert result is True
        assert cap.calls == ["hello"]

    def test_injectable_failure_propagated(self):
        cap = _Capture(return_value=False)
        _inject(cap)
        assert tn.send("x") is False

    def test_no_config_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tn, "ENV_PATH", tmp_path / "nonexistent.env")
        result = tn.send("test")
        assert result is False


# ---------------------------------------------------------------------------
# notify_park
# ---------------------------------------------------------------------------

class TestNotifyPark:
    def setup_method(self):
        _reset()

    def teardown_method(self):
        _reset()

    def test_park_sends_message(self):
        cap = _Capture()
        _inject(cap)
        result = tn.notify_park("parked_budget_daily", "#budget_daily", task_id="t-1")
        assert result is True
        assert len(cap.calls) == 1
        msg = cap.calls[0]
        assert len(msg) > 0

    def test_park_message_is_russian(self):
        cap = _Capture()
        _inject(cap)
        tn.notify_park("blocked", "#blocker: audit failed")
        msg = cap.calls[0]
        # Should contain Cyrillic characters
        assert any("\u0400" <= c <= "\u04ff" for c in msg)

    def test_park_includes_task_id(self):
        cap = _Capture()
        _inject(cap)
        tn.notify_park("awaiting_owner_reply", "#blocker_loop: after 2 retries", task_id="fix-abc")
        assert "fix-abc" in cap.calls[0]

    def test_park_with_send_failure(self):
        cap = _Capture(return_value=False)
        _inject(cap)
        result = tn.notify_park("blocked", "#blocker")
        assert result is False

    def test_park_translate_fallback_on_import_error(self, monkeypatch):
        """If decision_translator is broken, still sends a fallback message."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "decision_translator":
                raise ImportError("simulated missing module")
            return real_import(name, *args, **kwargs)

        cap = _Capture()
        _inject(cap)
        monkeypatch.setattr(builtins, "__import__", mock_import)
        result = tn.notify_park("blocked", "#blocker: test", task_id="t-1")
        assert result is True
        assert len(cap.calls) == 1


# ---------------------------------------------------------------------------
# notify_decision
# ---------------------------------------------------------------------------

class TestNotifyDecision:
    def setup_method(self):
        _reset()

    def teardown_method(self):
        _reset()

    def test_decision_sends_formatted_options(self):
        cap = _Capture()
        _inject(cap)
        result = tn.notify_decision(
            "Что делать?",
            {"A": "Вариант А", "B": "Вариант Б"},
            save_to_manifest=False,
        )
        assert result is True
        msg = cap.calls[0]
        assert "A" in msg
        assert "B" in msg

    def test_decision_saves_to_manifest(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({"fsm_state": "ready"}), encoding="utf-8")

        cap = _Capture()
        _inject(cap)
        import telegram_notifier as _tn
        orig = _tn.MANIFEST_PATH
        _tn.MANIFEST_PATH = manifest_path
        try:
            _tn.notify_decision(
                "Вопрос?",
                {"A": "Да", "B": "Нет"},
                save_to_manifest=True,
            )
        finally:
            _tn.MANIFEST_PATH = orig

        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "pending_decision" in saved
        assert saved["pending_decision"]["question"] == "Вопрос?"
        assert saved["pending_decision"]["options"] == {"A": "Да", "B": "Нет"}

    def test_decision_skip_manifest_save(self, tmp_path):
        """save_to_manifest=False must not touch manifest."""
        manifest_path = tmp_path / "manifest.json"
        original = {"fsm_state": "ready"}
        manifest_path.write_text(json.dumps(original), encoding="utf-8")

        cap = _Capture()
        _inject(cap)
        tn.notify_decision("Q?", {"A": "yes"}, save_to_manifest=False)

        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "pending_decision" not in saved

    def test_decision_missing_manifest_no_crash(self, tmp_path, monkeypatch):
        """If manifest.json does not exist, save_to_manifest should not raise."""
        monkeypatch.setattr(tn, "MANIFEST_PATH", tmp_path / "nonexistent.json")
        cap = _Capture()
        _inject(cap)
        result = tn.notify_decision("Q?", {"A": "y"}, save_to_manifest=True)
        assert result is True  # send still works via injectable

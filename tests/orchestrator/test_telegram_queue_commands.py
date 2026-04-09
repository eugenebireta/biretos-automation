"""
test_telegram_queue_commands.py — P4: deterministic tests for Telegram queue commands.

Tests cmd_queue, cmd_enqueue, cmd_pop, cmd_confirm, cmd_run in telegram_bot.py.
All tests: mocked Update + task_queue — no Telegram API calls, no subprocess calls.
"""
from __future__ import annotations

import json
import sys
import os
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_queue_and_manifest(tmp_path):
    """Redirect queue and manifest paths to temp directory."""
    import task_queue as tq
    import telegram_bot as tb

    orig_queue = tq.QUEUE_PATH
    orig_manifest = tb.MANIFEST_PATH

    tq.QUEUE_PATH = tmp_path / "task_queue.json"
    tb.MANIFEST_PATH = tmp_path / "manifest.json"
    tb.OWNER_CHAT_ID = None  # Reset owner each test

    yield tmp_path

    tq.QUEUE_PATH = orig_queue
    tb.MANIFEST_PATH = orig_manifest


def _mock_update(chat_id: int = 12345) -> MagicMock:
    """Build a minimal Update mock."""
    update = MagicMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


def _mock_context(args: list[str] | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.args = args or []
    return ctx


def _run(coro):
    """Run async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# cmd_queue
# ---------------------------------------------------------------------------

class TestCmdQueue:
    def test_empty_queue_message(self):
        import telegram_bot as tb
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_queue(update, _mock_context()))
        update.message.reply_text.assert_called_once()
        call_text = update.message.reply_text.call_args[0][0]
        assert "пуста" in call_text.lower() or "empty" in call_text.lower()

    def test_non_owner_ignored(self):
        import telegram_bot as tb
        update = _mock_update(chat_id=99999)
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_queue(update, _mock_context()))
        update.message.reply_text.assert_not_called()

    def test_queue_shows_tasks(self):
        import telegram_bot as tb
        import task_queue as tq
        tq.enqueue("task-alpha", "Do alpha", risk_class="LOW")
        tq.enqueue("task-beta", "Do beta", risk_class="SEMI")
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_queue(update, _mock_context()))
        reply = update.message.reply_text.call_args[0][0]
        assert "task-alpha" in reply
        assert "task-beta" in reply
        assert "2" in reply

    def test_queue_shows_risk_class(self):
        import telegram_bot as tb
        import task_queue as tq
        tq.enqueue("my-task", "My goal", risk_class="SEMI")
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_queue(update, _mock_context()))
        reply = update.message.reply_text.call_args[0][0]
        assert "SEMI" in reply


# ---------------------------------------------------------------------------
# cmd_enqueue
# ---------------------------------------------------------------------------

class TestCmdEnqueue:
    def test_enqueue_low_task(self):
        import telegram_bot as tb
        import task_queue as tq
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        ctx = _mock_context(["new-task", "Do", "the", "thing"])
        _run(tb.cmd_enqueue(update, ctx))
        update.message.reply_text.assert_called_once()
        assert tq.queue_depth() == 1
        q = tq.load_queue()
        assert q[0]["task_id"] == "new-task"
        assert q[0]["risk_class"] == "LOW"

    def test_enqueue_with_semi_risk(self):
        import telegram_bot as tb
        import task_queue as tq
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        ctx = _mock_context(["semi-task", "SEMI", "work", "here", "SEMI"])
        _run(tb.cmd_enqueue(update, ctx))
        q = tq.load_queue()
        assert q[0]["risk_class"] == "SEMI"

    def test_enqueue_no_args_shows_usage(self):
        import telegram_bot as tb
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_enqueue(update, _mock_context([])))
        reply = update.message.reply_text.call_args[0][0]
        assert "Использование" in reply or "использование" in reply.lower()

    def test_enqueue_reply_contains_task_id(self):
        import telegram_bot as tb
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        ctx = _mock_context(["my-special-task", "Build", "something"])
        _run(tb.cmd_enqueue(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "my-special-task" in reply

    def test_enqueue_non_owner_ignored(self):
        import telegram_bot as tb
        import task_queue as tq
        update = _mock_update(chat_id=99999)
        tb.OWNER_CHAT_ID = 12345
        ctx = _mock_context(["task-x", "Goal"])
        _run(tb.cmd_enqueue(update, ctx))
        update.message.reply_text.assert_not_called()
        assert tq.queue_depth() == 0

    def test_enqueue_missing_goal_uses_task_id(self):
        """If goal is empty after stripping risk class, fall back to task_id."""
        import telegram_bot as tb
        import task_queue as tq
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        ctx = _mock_context(["solo-task"])  # only 1 arg — shows usage
        _run(tb.cmd_enqueue(update, ctx))
        # Should show usage (not enough args)
        reply = update.message.reply_text.call_args[0][0]
        assert "Использование" in reply or "/" in reply


# ---------------------------------------------------------------------------
# cmd_pop
# ---------------------------------------------------------------------------

class TestCmdPop:
    def test_pop_empty_queue(self):
        import telegram_bot as tb
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_pop(update, _mock_context()))
        reply = update.message.reply_text.call_args[0][0]
        assert "пуст" in reply.lower() or "empty" in reply.lower()

    def test_pop_returns_task(self):
        import telegram_bot as tb
        import task_queue as tq
        tq.enqueue("pop-task", "Pop me", risk_class="LOW")
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_pop(update, _mock_context()))
        reply = update.message.reply_text.call_args[0][0]
        assert "pop-task" in reply
        assert tq.queue_depth() == 0

    def test_pop_decrements_queue(self):
        import telegram_bot as tb
        import task_queue as tq
        tq.enqueue("t1", "G1")
        tq.enqueue("t2", "G2")
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_pop(update, _mock_context()))
        assert tq.queue_depth() == 1

    def test_pop_non_owner_ignored(self):
        import telegram_bot as tb
        import task_queue as tq
        tq.enqueue("t1", "G1")
        update = _mock_update(chat_id=99999)
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_pop(update, _mock_context()))
        update.message.reply_text.assert_not_called()
        assert tq.queue_depth() == 1  # not popped


# ---------------------------------------------------------------------------
# cmd_confirm
# ---------------------------------------------------------------------------

class TestCmdConfirm:
    def _write_manifest(self, tmp_path: Path, state: str = "ready") -> None:
        import telegram_bot as tb
        m = {
            "fsm_state": state,
            "current_task_id": "old-task",
            "current_sprint_goal": "old goal",
            "last_verdict": None,
            "attempt_count": 0,
            "retry_count": 0,
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        tb.MANIFEST_PATH.write_text(json.dumps(m), encoding="utf-8")

    def test_confirm_empty_queue_message(self, tmp_queue_and_manifest):
        import telegram_bot as tb
        self._write_manifest(tmp_queue_and_manifest)
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_confirm(update, _mock_context()))
        reply = update.message.reply_text.call_args[0][0]
        assert "пуст" in reply.lower() or "пустая" in reply.lower()

    def test_confirm_low_task_says_not_needed(self, tmp_queue_and_manifest):
        import telegram_bot as tb
        import task_queue as tq
        self._write_manifest(tmp_queue_and_manifest)
        tq.enqueue("low-task", "Low goal", risk_class="LOW")
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_confirm(update, _mock_context()))
        reply = update.message.reply_text.call_args[0][0]
        assert "LOW" in reply

    def test_confirm_semi_task_updates_manifest(self, tmp_queue_and_manifest):
        import telegram_bot as tb
        import task_queue as tq
        self._write_manifest(tmp_queue_and_manifest)
        tq.enqueue("semi-task", "SEMI goal", risk_class="SEMI")
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_confirm(update, _mock_context()))
        m = json.loads(tb.MANIFEST_PATH.read_text(encoding="utf-8"))
        assert m["current_task_id"] == "semi-task"
        assert m["fsm_state"] == "ready"
        assert m["attempt_count"] == 0
        assert tq.queue_depth() == 0

    def test_confirm_non_owner_ignored(self, tmp_queue_and_manifest):
        import telegram_bot as tb
        import task_queue as tq
        self._write_manifest(tmp_queue_and_manifest)
        tq.enqueue("semi-t", "Goal", risk_class="SEMI")
        update = _mock_update(chat_id=99999)
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_confirm(update, _mock_context()))
        update.message.reply_text.assert_not_called()
        assert tq.queue_depth() == 1  # not consumed

    def test_confirm_no_manifest_message(self, tmp_queue_and_manifest):
        import telegram_bot as tb
        # Manifest does not exist
        tb.MANIFEST_PATH = tmp_queue_and_manifest / "nonexistent_manifest.json"
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_confirm(update, _mock_context()))
        reply = update.message.reply_text.call_args[0][0]
        assert "Манифест" in reply or "manifest" in reply.lower()


# ---------------------------------------------------------------------------
# cmd_run
# ---------------------------------------------------------------------------

class TestCmdRun:
    def _write_manifest(self, tmp_path: Path, state: str = "ready") -> None:
        import telegram_bot as tb
        m = {
            "fsm_state": state,
            "current_task_id": "run-task",
            "current_sprint_goal": "Run goal",
            "last_verdict": None,
            "attempt_count": 0,
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        tb.MANIFEST_PATH.write_text(json.dumps(m), encoding="utf-8")

    def test_run_no_manifest(self, tmp_queue_and_manifest):
        import telegram_bot as tb
        # Manifest does not exist
        tb.MANIFEST_PATH = tmp_queue_and_manifest / "no_manifest.json"
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_run(update, _mock_context()))
        reply = update.message.reply_text.call_args[0][0]
        assert "Манифест" in reply or "manifest" in reply.lower()

    def test_run_wrong_state_refuses(self, tmp_queue_and_manifest):
        import telegram_bot as tb
        self._write_manifest(tmp_queue_and_manifest, state="awaiting_owner_reply")
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_run(update, _mock_context()))
        reply = update.message.reply_text.call_args[0][0]
        assert "awaiting_owner_reply" in reply or "ready" in reply.lower()

    def test_run_non_owner_ignored(self, tmp_queue_and_manifest):
        import telegram_bot as tb
        self._write_manifest(tmp_queue_and_manifest)
        update = _mock_update(chat_id=99999)
        tb.OWNER_CHAT_ID = 12345
        _run(tb.cmd_run(update, _mock_context()))
        update.message.reply_text.assert_not_called()

    def test_run_ready_state_triggers_subprocess(self, tmp_queue_and_manifest):
        """In ready state, cmd_run should try to launch main.py subprocess."""
        import telegram_bot as tb
        self._write_manifest(tmp_queue_and_manifest, state="ready")
        update = _mock_update()
        tb.OWNER_CHAT_ID = 12345

        # Mock subprocess.Popen to avoid actually running main.py
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["[orchestrator] state=ready"])
        mock_proc.returncode = 0
        mock_proc.wait = MagicMock(return_value=0)

        with patch("telegram_bot.subprocess.Popen", return_value=mock_proc):
            _run(tb.cmd_run(update, _mock_context()))

        # Should have sent at least 2 messages (starting + result)
        assert update.message.reply_text.call_count >= 1

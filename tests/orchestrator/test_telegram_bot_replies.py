"""
test_telegram_bot_replies.py — Integration tests for telegram_bot reply handling.

Mocks the Telegram Update/Message objects and calls handlers directly.
Tests the REAL code path: user message → manifest mutation → reply sent.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)

import telegram_bot as bot  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_update(text: str, chat_id: int = 123) -> MagicMock:
    """Build a mock Telegram Update with a text message."""
    update = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = chat_id
    return update


def _write_manifest(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def _read_manifest(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))


def _run(coro):
    """Run async function synchronously — creates fresh loop to avoid contamination."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# _handle_owner_reply — ок/нет
# ---------------------------------------------------------------------------

class TestOwnerReplyOkNo:
    """Basic ок/нет replies in park states."""

    def test_ok_resumes_to_ready(self, tmp_path):
        mp = _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "park_reason": "#blocker_loop: failed 3 times",
            "current_task_id": "fix-auth",
        })
        update = _make_update("ок")
        with patch.object(bot, "MANIFEST_PATH", mp), \
             patch.object(bot, "_run_cycle", new_callable=AsyncMock):
            result = _run(bot._handle_owner_reply(update, "ок"))

        assert result is True
        m = _read_manifest(tmp_path)
        assert m["fsm_state"] == "ready"
        assert m.get("park_reason") is None
        assert "Принято" in update.message.reply_text.call_args_list[0][0][0]

    def test_no_keeps_parked(self, tmp_path):
        mp = _write_manifest(tmp_path, {
            "fsm_state": "blocked",
            "park_reason": "#blocker: auditor blocked",
        })
        update = _make_update("нет")
        with patch.object(bot, "MANIFEST_PATH", mp):
            result = _run(bot._handle_owner_reply(update, "нет"))

        assert result is True
        m = _read_manifest(tmp_path)
        assert m["fsm_state"] == "blocked"  # unchanged
        assert "паузе" in update.message.reply_text.call_args[0][0]

    def test_non_park_state_ignored(self, tmp_path):
        mp = _write_manifest(tmp_path, {"fsm_state": "ready"})
        update = _make_update("ок")
        with patch.object(bot, "MANIFEST_PATH", mp):
            result = _run(bot._handle_owner_reply(update, "ок"))

        assert result is False  # not handled

    def test_prodolzhay_resumes_and_runs(self, tmp_path):
        """'продолжай' should resume and trigger auto-run."""
        mp = _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "park_reason": "#blocker_loop: failed",
        })
        update = _make_update("продолжай")
        mock_run = AsyncMock()
        with patch.object(bot, "MANIFEST_PATH", mp), \
             patch.object(bot, "_run_cycle", mock_run):
            result = _run(bot._handle_owner_reply(update, "продолжай"))

        assert result is True
        assert _read_manifest(tmp_path)["fsm_state"] == "ready"
        mock_run.assert_called_once_with(update)

    def test_ok_triggers_auto_run(self, tmp_path):
        """After 'ок', _run_cycle should be called automatically."""
        mp = _write_manifest(tmp_path, {
            "fsm_state": "blocked",
            "park_reason": "#blocker: test",
        })
        update = _make_update("ок")
        mock_run = AsyncMock()
        with patch.object(bot, "MANIFEST_PATH", mp), \
             patch.object(bot, "_run_cycle", mock_run):
            result = _run(bot._handle_owner_reply(update, "ок"))

        assert result is True
        mock_run.assert_called_once_with(update)

    def test_all_park_states_accept_ok(self, tmp_path):
        for state in ("awaiting_owner_reply", "blocked", "blocked_by_consensus",
                       "parked_budget_daily", "parked_budget_run", "parked_api_outage"):
            mp = _write_manifest(tmp_path, {"fsm_state": state})
            update = _make_update("ok")
            with patch.object(bot, "MANIFEST_PATH", mp), \
                 patch.object(bot, "_run_cycle", new_callable=AsyncMock):
                result = _run(bot._handle_owner_reply(update, "ok"))
            assert result is True, f"State {state} did not accept 'ok'"
            assert _read_manifest(tmp_path)["fsm_state"] == "ready"


# ---------------------------------------------------------------------------
# _handle_owner_reply — A/B/C decisions
# ---------------------------------------------------------------------------

class TestOwnerReplyDecision:
    """Structured A/B/C decision replies."""

    def test_decision_a(self, tmp_path):
        mp = _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "pending_decision": {
                "question": "Что делать?",
                "options": {"A": "Добавить товары", "B": "Исправить категории"},
            },
        })
        update = _make_update("A")
        with patch.object(bot, "MANIFEST_PATH", mp), \
             patch.object(bot, "_run_cycle", new_callable=AsyncMock):
            result = _run(bot._handle_owner_reply(update, "A"))

        assert result is True
        m = _read_manifest(tmp_path)
        assert m["owner_decision"] == "A"
        assert m["owner_decision_text"] == "Добавить товары"
        assert m["fsm_state"] == "ready"
        assert "pending_decision" not in m

    def test_decision_lowercase(self, tmp_path):
        mp = _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "pending_decision": {
                "question": "?",
                "options": {"A": "Yes", "B": "No"},
            },
        })
        update = _make_update("b")
        with patch.object(bot, "MANIFEST_PATH", mp), \
             patch.object(bot, "_run_cycle", new_callable=AsyncMock):
            result = _run(bot._handle_owner_reply(update, "b"))

        assert result is True
        assert _read_manifest(tmp_path)["owner_decision"] == "B"

    def test_invalid_option_not_handled(self, tmp_path):
        """Invalid single letter falls through — too short for free-text."""
        mp = _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "pending_decision": {
                "question": "?",
                "options": {"A": "Yes", "B": "No"},
            },
        })
        update = _make_update("C")
        with patch.object(bot, "MANIFEST_PATH", mp), \
             patch.object(bot, "_run_cycle", new_callable=AsyncMock):
            result = _run(bot._handle_owner_reply(update, "C"))

        # "C" is 1 char, not in options, not ок/нет, <5 chars → not handled
        assert result is False


# ---------------------------------------------------------------------------
# _handle_owner_reply — free-text instructions
# ---------------------------------------------------------------------------

class TestOwnerReplyFreeText:
    """Free-text replies saved as owner_instruction."""

    def test_free_text_saves_instruction(self, tmp_path):
        mp = _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "park_reason": "#blocker: failed",
            "current_task_id": "fix-it",
        })
        text = "попробуй другой подход — используй gemini"
        update = _make_update(text)
        with patch.object(bot, "MANIFEST_PATH", mp), \
             patch.object(bot, "_run_cycle", new_callable=AsyncMock):
            result = _run(bot._handle_owner_reply(update, text))

        assert result is True
        m = _read_manifest(tmp_path)
        assert m["owner_instruction"] == text
        assert m["fsm_state"] == "ready"
        assert m.get("park_reason") is None
        reply = update.message.reply_text.call_args_list[0][0][0]
        assert "инструкцию" in reply.lower()

    def test_free_text_long_instruction(self, tmp_path):
        mp = _write_manifest(tmp_path, {
            "fsm_state": "blocked_by_consensus",
        })
        text = "Отмени текущий подход. Вместо этого: 1) прочитай файл X, 2) измени функцию Y, 3) запусти тесты"
        update = _make_update(text)
        with patch.object(bot, "MANIFEST_PATH", mp), \
             patch.object(bot, "_run_cycle", new_callable=AsyncMock):
            result = _run(bot._handle_owner_reply(update, text))

        assert result is True
        m = _read_manifest(tmp_path)
        assert m["owner_instruction"] == text
        assert m["fsm_state"] == "ready"

    def test_short_text_not_handled(self, tmp_path):
        """Text <5 chars that is not ок/нет should NOT be handled."""
        mp = _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
        })
        update = _make_update("хм")
        with patch.object(bot, "MANIFEST_PATH", mp):
            result = _run(bot._handle_owner_reply(update, "хм"))

        assert result is False  # not handled

    def test_free_text_not_in_ready_state(self, tmp_path):
        """Free text when FSM is ready should NOT be handled by reply handler."""
        mp = _write_manifest(tmp_path, {
            "fsm_state": "ready",
        })
        text = "сделай что-нибудь полезное"
        update = _make_update(text)
        with patch.object(bot, "MANIFEST_PATH", mp):
            result = _run(bot._handle_owner_reply(update, text))

        assert result is False  # not in park state


# ---------------------------------------------------------------------------
# handle_message — free text as new task (idle/ready state)
# ---------------------------------------------------------------------------

class TestHandleMessageFreeText:
    """Any text without prefix treated as new task via strojka."""

    def test_free_text_triggers_strojka(self, tmp_path):
        """Text without 'Стройка:' prefix should still trigger strojka."""
        mp = _write_manifest(tmp_path, {"fsm_state": "ready"})
        update = _make_update("добавь логирование в advisor.py")
        ctx = MagicMock()

        with patch.object(bot, "MANIFEST_PATH", mp), \
             patch.object(bot, "OWNER_CHAT_ID", None), \
             patch("telegram_bot.subprocess") as mock_sp, \
             patch("telegram_bot._load_env", return_value=os.environ.copy()), \
             patch("telegram_bot._build_telegram_message", return_value="done"):

            mock_proc = MagicMock()
            mock_proc.stdout = iter([])
            mock_proc.returncode = 0
            mock_proc.wait = MagicMock()
            mock_sp.Popen.return_value = mock_proc

            _run(bot.handle_message(update, ctx))

        # Should have started subprocess (strojka)
        mock_sp.Popen.assert_called_once()
        call_args = mock_sp.Popen.call_args[0][0]
        assert "strojka.py" in call_args[1]
        assert "добавь логирование в advisor.py" in call_args[2]

    def test_prefixed_text_also_works(self, tmp_path):
        """'Стройка: <task>' still works as before."""
        mp = _write_manifest(tmp_path, {"fsm_state": "ready"})
        update = _make_update("Стройка: обнови версию")
        ctx = MagicMock()

        with patch.object(bot, "MANIFEST_PATH", mp), \
             patch.object(bot, "OWNER_CHAT_ID", None), \
             patch("telegram_bot.subprocess") as mock_sp, \
             patch("telegram_bot._load_env", return_value=os.environ.copy()), \
             patch("telegram_bot._build_telegram_message", return_value="done"):

            mock_proc = MagicMock()
            mock_proc.stdout = iter([])
            mock_proc.returncode = 0
            mock_proc.wait = MagicMock()
            mock_sp.Popen.return_value = mock_proc

            _run(bot.handle_message(update, ctx))

        mock_sp.Popen.assert_called_once()
        call_args = mock_sp.Popen.call_args[0][0]
        assert "обнови версию" in call_args[2]


# ---------------------------------------------------------------------------
# End-to-end: park → free-text → directive includes instruction
# ---------------------------------------------------------------------------

class TestEndToEndFreeTextToDirective:
    """Full chain: park state → owner free-text → directive has OWNER INSTRUCTION."""

    def test_full_chain(self, tmp_path):
        # 1. Set up parked manifest
        mp = _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "park_reason": "#blocker_loop: audit failed after 3 retries",
            "current_task_id": "fix-auth",
            "current_sprint_goal": "Fix auth module",
            "attempt_count": 1,
            "retry_count": 0,
        })

        # 2. Owner sends free-text instruction
        instruction = "не трогай файл guardian.py, исправь только в advisor.py"
        update = _make_update(instruction)
        with patch.object(bot, "MANIFEST_PATH", mp), \
             patch.object(bot, "_run_cycle", new_callable=AsyncMock):
            result = _run(bot._handle_owner_reply(update, instruction))
        assert result is True

        # 3. Verify manifest has instruction + ready state
        m = _read_manifest(tmp_path)
        assert m["fsm_state"] == "ready"
        assert m["owner_instruction"] == instruction

        # 4. Build directive — verify instruction appears
        sys.path.insert(0, _orch_dir)
        import main

        bundle = MagicMock()
        bundle.dna_constraints = ["no Core touch"]
        classification = MagicMock()
        classification.risk_class = "LOW"
        classification.governance_route = "none"
        verdict = MagicMock()
        verdict.risk_assessment = "LOW"
        verdict.governance_route = "none"
        verdict.next_step = "Fix auth"
        verdict.rationale = "Because"
        verdict.scope = ["orchestrator/advisor.py"]
        synth = MagicMock()
        synth.approved_scope = ["orchestrator/advisor.py"]
        synth.action = "PROCEED"
        synth.rule_trace = "test"
        synth.final_risk = "LOW"

        directive = main._build_directive(
            m, "test-trace", bundle, classification, verdict, synth
        )

        assert "OWNER INSTRUCTION" in directive
        assert "не трогай файл guardian.py" in directive
        assert "исправь только в advisor.py" in directive

        # 5. Verify instruction is consumed (main.py pops it)
        m.pop("owner_instruction", None)
        assert "owner_instruction" not in m

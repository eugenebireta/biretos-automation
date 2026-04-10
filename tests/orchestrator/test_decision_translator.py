"""
test_decision_translator.py — Tests for decision_translator.py.

Covers translate_park for all FSM park states + generic fallback,
and translate_decision formatting.
"""
from __future__ import annotations

import os
import sys

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)

import decision_translator as dt  # noqa: E402


class TestTranslatePark:
    def test_parked_budget_daily(self):
        msg = dt.translate_park("parked_budget_daily", "#budget_daily: $5.00/$5.00")
        assert "бюджет" in msg.lower() or "исчерпан" in msg.lower()
        assert "завтра" in msg

    def test_parked_budget_daily_with_task(self):
        msg = dt.translate_park("parked_budget_daily", "#budget_daily", task_id="task-42")
        assert "task-42" in msg

    def test_parked_budget_run(self):
        msg = dt.translate_park("parked_budget_run", "#budget_run: $0.55/$0.50")
        assert "дорог" in msg.lower() or "лимит" in msg.lower() or "задача" in msg.lower()

    def test_parked_api_outage(self):
        msg = dt.translate_park("parked_api_outage", "external API timeout")
        assert "сервис" in msg.lower() or "отвечает" in msg.lower()

    def test_awaiting_blocker_loop(self):
        msg = dt.translate_park("awaiting_owner_reply", "#blocker_loop: audit failed after 3 retries")
        assert "3" in msg
        assert "попыт" in msg.lower()

    def test_awaiting_blocker_loop_no_count(self):
        msg = dt.translate_park("awaiting_owner_reply", "#blocker_loop: general fail")
        assert "застрял" in msg.lower() or "попыт" in msg.lower()

    def test_awaiting_stalled(self):
        msg = dt.translate_park("awaiting_owner_reply", "#stalled: owner did not respond")
        assert "ждёт" in msg.lower() or "долго" in msg.lower()

    def test_awaiting_generic(self):
        msg = dt.translate_park("awaiting_owner_reply", "some reason")
        assert "ок" in msg.lower()

    def test_blocked(self):
        msg = dt.translate_park("blocked", "#blocker: auditor flagged")
        assert "заблокирована" in msg.lower() or "проблем" in msg.lower()

    def test_timeout_in_state(self):
        msg = dt.translate_park("task_timeout", "some reason")
        assert "долго" in msg.lower() or "остановлен" in msg.lower()

    def test_timeout_in_reason(self):
        msg = dt.translate_park("unknown_state", "TIMEOUT exceeded")
        assert "долго" in msg.lower() or "остановлен" in msg.lower()

    def test_generic_fallback(self):
        msg = dt.translate_park("some_random_state", "some_reason")
        assert "паузу" in msg.lower() or "причина" in msg.lower()

    def test_task_id_none(self):
        msg = dt.translate_park("blocked", "#blocker", task_id=None)
        assert "Задача:" not in msg

    def test_park_reason_truncated(self):
        long_reason = "x" * 500
        msg = dt.translate_park("some_state", long_reason)
        # Should not crash and should produce reasonable output
        assert len(msg) < 1000


class TestTranslateDecision:
    def test_basic_ab(self):
        msg = dt.translate_decision(
            "Что делать?",
            {"A": "Вариант А", "B": "Вариант Б"},
        )
        assert "A — Вариант А" in msg
        assert "B — Вариант Б" in msg
        assert "A / B" in msg

    def test_question_included(self):
        msg = dt.translate_decision("Продолжить?", {"A": "Да", "B": "Нет"})
        assert "Продолжить?" in msg

    def test_single_option(self):
        msg = dt.translate_decision("Ок?", {"A": "Да"})
        assert "A — Да" in msg
        assert "Ответь: A" in msg

    def test_three_options(self):
        msg = dt.translate_decision(
            "Выбери:",
            {"A": "Первый", "B": "Второй", "C": "Третий"},
        )
        assert "A / B / C" in msg

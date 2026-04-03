"""
Day 1 Smoke Tests — NLU Wire (Stage 8.1)

Verifies the three critical user-facing scenarios without live API or DB:
  1. Slash command path (unchanged by Day 1)
  2. Free-text NLU path (new) — confirmation button returned
  3. Garbage text (graceful fallback)
  4. shadow_rag_log write_nlu_shadow_entry is called on successful parse

Run:  pytest tests/test_smoke_day1.py -v
"""
from __future__ import annotations

import os
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_paths() -> None:
    root = _root()
    for p in [str(root), str(root / "ru_worker")]:
        if p not in sys.path:
            sys.path.insert(0, p)


_ensure_paths()


# ---------------------------------------------------------------------------
# Config stub — mirrors _ConfigStub from test_governance_workflow.py
# ---------------------------------------------------------------------------

@dataclass
class _ConfigStub:
    execution_mode: str = "DRY_RUN"

    def __getattr__(self, _: str) -> Any:
        return None


# ---------------------------------------------------------------------------
# Stub DB
# ---------------------------------------------------------------------------

import uuid as _uuid_mod


class _Cursor:
    """Minimal DB cursor stub that handles INSERT RETURNING for confirmation store."""

    def __init__(self, conn: "_DB") -> None:
        self._conn = conn

    def execute(self, sql, params=None) -> None:
        q = sql.strip().lower()
        if "returning" in q and "insert" in q:
            # INSERT ... RETURNING confirmation_id
            self._conn._last = (str(_uuid_mod.uuid4()),)
        elif "update" in q and "returning" in q:
            self._conn._last = None
        else:
            self._conn._last = None

    def fetchone(self):
        return self._conn._last

    def fetchall(self):
        return []

    @property
    def rowcount(self):
        return 0

    def close(self):
        pass


class _DB:
    def __init__(self) -> None:
        self._last = None

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass


# ---------------------------------------------------------------------------
# Telegram update builder
# ---------------------------------------------------------------------------

def _update(text: str, user_id: int = 999, chat_id: int = 111) -> Dict[str, Any]:
    return {
        "update_id": 1001,
        "message": {
            "message_id": 42,
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "private"},
            "text": text,
        },
    }


# ---------------------------------------------------------------------------
# Scenario 1: slash command not broken
# ---------------------------------------------------------------------------

def test_slash_invoice_routes_to_tbank_action(monkeypatch):
    """
    /invoice command must NOT go through NLU.
    route_update must return action_type=tbank_invoice_status.
    """
    import config as cfg_pkg
    monkeypatch.setattr(cfg_pkg, "get_config", lambda: _ConfigStub(), raising=True)

    # Re-import with patched config
    for mod in list(sys.modules.keys()):
        if "telegram_router" in mod:
            del sys.modules[mod]

    from ru_worker import telegram_router
    monkeypatch.setattr(telegram_router, "ALLOWED_USER_IDS", {999})

    _, action = telegram_router.route_update(_update("/invoice INV-999"))

    assert action is not None, "Expected action for /invoice"
    assert action.get("action_type") == "tbank_invoice_status", (
        "Got: %s" % action.get("action_type")
    )


# ---------------------------------------------------------------------------
# Scenario 2: free-text produces nlu_parse action
# ---------------------------------------------------------------------------

def test_free_text_produces_nlu_parse_action(monkeypatch):
    """
    Free-text message must produce action_type=nlu_parse via route_update.
    """
    import config as cfg_pkg
    monkeypatch.setattr(cfg_pkg, "get_config", lambda: _ConfigStub(), raising=True)

    for mod in list(sys.modules.keys()):
        if "telegram_router" in mod:
            del sys.modules[mod]

    from ru_worker import telegram_router
    monkeypatch.setattr(telegram_router, "ALLOWED_USER_IDS", {999})

    _, action = telegram_router.route_update(_update("проверь оплату INV-123"))

    assert action is not None
    assert action.get("action_type") == "nlu_parse", (
        "Free-text must be nlu_parse, got: %s" % action.get("action_type")
    )
    assert action["payload"].get("text") == "проверь оплату INV-123"


# ---------------------------------------------------------------------------
# Scenario 3: NLU parse returns needs_confirmation
# ---------------------------------------------------------------------------

def test_nlu_parse_check_payment_returns_confirmation():
    """
    route_assistant_intent with check_payment text returns needs_confirmation
    with reply_markup.
    """
    os.environ["NLU_ENABLED"] = "true"
    os.environ["NLU_SHADOW_MODE"] = "false"
    os.environ["NLU_DEGRADATION_LEVEL"] = "0"

    from ru_worker.assistant_router import route_assistant_intent

    result = route_assistant_intent(
        {
            "trace_id": "smoke-001",
            "employee_id": "999",
            "employee_role": "operator",
            "text": "проверить оплату INV-123",
        },
        _DB(),
    )

    assert result["status"] == "needs_confirmation", (
        "Expected needs_confirmation, got: %s" % result
    )
    assert "confirmation_id" in result
    assert "reply_markup" in result
    assert result.get("intent_type") == "check_payment"
    kb = result["reply_markup"].get("inline_keyboard", [])
    assert len(kb) > 0, "reply_markup must have buttons"
    first_row = kb[0]
    confirm_btn = next((b for b in first_row if "nlu_confirm" in b.get("callback_data", "")), None)
    assert confirm_btn is not None, "Must have nlu_confirm button"


# ---------------------------------------------------------------------------
# Scenario 4: garbage text → graceful fallback
# ---------------------------------------------------------------------------

def test_garbage_text_returns_fallback():
    """
    Unrecognized text must return fallback status (not crash, not error).
    """
    os.environ["NLU_ENABLED"] = "true"
    os.environ["NLU_SHADOW_MODE"] = "false"
    os.environ["NLU_DEGRADATION_LEVEL"] = "0"

    from ru_worker.assistant_router import route_assistant_intent

    result = route_assistant_intent(
        {
            "trace_id": "smoke-002",
            "employee_id": "999",
            "employee_role": "operator",
            "text": "qwerty asdfgh lorem ipsum random garbage xyz",
        },
        _DB(),
    )

    assert result["status"] == "fallback", (
        "Garbage must return fallback, got: %s" % result["status"]
    )


# ---------------------------------------------------------------------------
# Scenario 5: shadow_rag_log is written on successful parse
# ---------------------------------------------------------------------------

def test_shadow_log_written_on_ok_parse():
    """
    write_nlu_shadow_entry must be called on successful NLU parse (needs_confirmation).
    This ensures Stage 8.3 data collection works.
    """
    os.environ["NLU_ENABLED"] = "true"
    os.environ["NLU_SHADOW_MODE"] = "false"
    os.environ["NLU_DEGRADATION_LEVEL"] = "0"

    from ru_worker import assistant_router

    shadow_calls: list = []

    original = assistant_router.write_nlu_shadow_entry

    def _capture(db_conn, **kwargs):
        shadow_calls.append(kwargs)

    with mock.patch.object(assistant_router, "write_nlu_shadow_entry", side_effect=_capture):
        result = assistant_router.route_assistant_intent(
            {
                "trace_id": "smoke-003",
                "employee_id": "999",
                "employee_role": "operator",
                "text": "проверить оплату INV-123",
            },
            _DB(),
        )

    assert result["status"] == "needs_confirmation", (
        "Parse must succeed before shadow check: %s" % result
    )
    assert len(shadow_calls) >= 1, (
        "write_nlu_shadow_entry must be called on successful parse, got %d calls" % len(shadow_calls)
    )
    assert shadow_calls[0].get("intent_type") == "check_payment"
    assert shadow_calls[0].get("trace_id") == "smoke-003"


# ---------------------------------------------------------------------------
# Scenario 6: format_action_result nlu_parse needs_confirmation → text + markup
# ---------------------------------------------------------------------------

def test_format_action_result_nlu_parse_needs_confirmation(monkeypatch):
    """
    format_action_result for nlu_parse/needs_confirmation must return
    non-empty text and reply_markup (for inline buttons).
    """
    import config as cfg_pkg
    monkeypatch.setattr(cfg_pkg, "get_config", lambda: _ConfigStub(), raising=True)

    import importlib.util
    module_name = "_ru_worker_fmt_smoke"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(
        module_name, _root() / "ru_worker" / "ru_worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    action = {"action_type": "nlu_parse", "payload": {}, "metadata": {}}
    result = {
        "status": "needs_confirmation",
        "intent_type": "check_payment",
        "intent_label": "Проверить оплату",
        "entities": {"invoice_id": "INV-123"},
        "confirmation_id": "test-uuid",
        "reply_markup": {"inline_keyboard": [[{"text": "Да", "callback_data": "nlu_confirm:test-uuid"}]]},
    }

    text, markup = module.format_action_result(action, result)
    assert text is not None and len(text) > 0, "Must return non-empty text, got: %r" % text
    assert markup is not None, "Must return reply_markup"


def test_format_action_result_nlu_parse_fallback(monkeypatch):
    """format_action_result for nlu_parse/fallback must mention /help."""
    import config as cfg_pkg
    monkeypatch.setattr(cfg_pkg, "get_config", lambda: _ConfigStub(), raising=True)

    import importlib.util
    module_name = "_ru_worker_fmt_smoke2"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(
        module_name, _root() / "ru_worker" / "ru_worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    action = {"action_type": "nlu_parse", "payload": {}, "metadata": {}}
    result = {"status": "fallback", "trace_id": "x"}

    text, markup = module.format_action_result(action, result)
    assert text is not None and "/help" in text, "Fallback must mention /help, got: %r" % text
    assert markup is None


def test_format_action_result_nlu_confirm_waybill_transient(monkeypatch):
    """Waybill transient errors must be mapped to a human-friendly Telegram reply."""
    import config as cfg_pkg
    monkeypatch.setattr(cfg_pkg, "get_config", lambda: _ConfigStub(), raising=True)

    import importlib.util
    module_name = "_ru_worker_fmt_smoke3"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(
        module_name, _root() / "ru_worker" / "ru_worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    action = {
        "action_type": "nlu_confirm",
        "payload": {"carrier_external_id": "10248510566"},
        "metadata": {},
    }
    result = {
        "status": "error",
        "intent_type": "get_waybill",
        "error_class": "TRANSIENT",
        "carrier_external_id": "10248510566",
        "error": "CDEK print task 9ce85ee5-13b6-41c1-a64c-ee8c754b3982 did not produce PDF within timeout",
    }

    text, markup = module.format_action_result(action, result)
    assert text is not None and "СДЭК" in text
    assert "CDEK print task" not in text
    assert "timeout" not in text.lower()
    assert markup is None

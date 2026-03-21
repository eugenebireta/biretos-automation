"""
Tests for side_effects/alert_dispatcher.py — Phase 4 Alerting.

Pure unit tests:
  - No live Telegram API (stub _send_fn injected)
  - No DB
  - No unmocked time / randomness
  - All deterministic
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
import httpx

from side_effects.alert_dispatcher import (
    AlertDispatchError,
    dispatch_alert,
    format_alert_message,
    route_alert,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok_sender(captured: list):
    """Stub sender that records calls and returns silently."""
    def _send(*, bot_token: str, chat_id: int, text: str) -> None:
        captured.append({"bot_token": bot_token, "chat_id": chat_id, "text": text})
    return _send


def _alert(
    check_code="IC-001",
    entity_type="order",
    entity_id="ord-001",
    severity="CRITICAL",
    verdict=None,
    trace_id="aaaa0000-0000-0000-0000-000000000000",
):
    return {
        "check_code": check_code,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "severity": severity,
        "verdict_snapshot": verdict or {},
        "sweep_trace_id": trace_id,
    }


# ---------------------------------------------------------------------------
# format_alert_message — 4.1 IC/RC violations
# ---------------------------------------------------------------------------

def test_format_critical_ic_violation():
    msg = format_alert_message(
        _alert(
            check_code="IC-001",
            severity="CRITICAL",
            verdict={"expected": 1000, "actual": 900, "diff": -100},
            trace_id="abcdef12-0000-0000-0000-000000000000",
        )
    )
    assert "\U0001f534" in msg       # 🔴
    assert "CRITICAL" in msg
    assert "IC-001" in msg
    assert "ord-001" in msg
    assert "expected: 1000" in msg
    assert "actual: 900" in msg
    assert "diff: -100" in msg
    assert "abcdef12" in msg         # trace prefix


def test_format_rc2_warning():
    msg = format_alert_message(
        _alert(
            check_code="RC-2",
            entity_type="shipment",
            entity_id="ship-42",
            severity="WARNING",
            verdict={"reason": "cache expired"},
        )
    )
    assert "\U0001f7e1" in msg       # 🟡
    assert "WARNING" in msg
    assert "RC-2" in msg
    assert "ship-42" in msg
    assert "reason: cache expired" in msg


# ---------------------------------------------------------------------------
# format_alert_message — 4.2 FSM staleness + zombie reservations
# ---------------------------------------------------------------------------

def test_format_fsm_stale():
    msg = format_alert_message(
        _alert(
            check_code="FSM-STALE",
            entity_type="order",
            entity_id="ord-stuck",
            severity="WARNING",
            verdict={"stuck_since": "72h"},
            trace_id="",
        )
    )
    assert "\U0001f7e1" in msg       # 🟡
    assert "FSM-STALE" in msg
    assert "Order stuck in FSM state" in msg
    assert "stuck_since: 72h" in msg


def test_format_zombie_reservation():
    msg = format_alert_message(
        _alert(
            check_code="FSM-ZOMBIE",
            entity_type="reservation",
            entity_id="res-dead",
            severity="WARNING",
            verdict={"age_hours": 96},
            trace_id="",
        )
    )
    assert "FSM-ZOMBIE" in msg
    assert "Zombie reservation detected" in msg
    assert "age_hours: 96" in msg


# ---------------------------------------------------------------------------
# format_alert_message — edge cases
# ---------------------------------------------------------------------------

def test_format_info_uses_blue_emoji():
    msg = format_alert_message(_alert(severity="INFO"))
    assert "\U0001f535" in msg       # 🔵


def test_format_unknown_severity_uses_white_circle():
    msg = format_alert_message(_alert(severity="BOGUS"))
    assert "\u26aa" in msg           # ⚪


def test_format_verdict_as_json_string():
    """verdict_snapshot may arrive as a JSON string from the DB."""
    a = _alert(verdict='{"diff": -50}', severity="CRITICAL")
    msg = format_alert_message(a)
    assert "diff: -50" in msg


def test_format_verdict_invalid_json_string_shows_raw():
    a = _alert(verdict="not-json", severity="WARNING")
    msg = format_alert_message(a)
    assert "not-json" in msg


def test_format_no_trace_id_omits_sweep_line():
    a = _alert(trace_id="")
    msg = format_alert_message(a)
    assert "Sweep:" not in msg


def test_format_unknown_check_code_shows_code_as_label():
    a = _alert(check_code="CUSTOM-99", severity="INFO")
    msg = format_alert_message(a)
    assert "CUSTOM-99" in msg


def test_format_batch_alert():
    a = _alert(
        check_code="L3-D",
        entity_type="batch",
        severity="MEDIUM",
        verdict={"total_count": 15},
    )
    msg = format_alert_message(a)
    assert "L3-D" in msg
    assert "total_count: 15" in msg


# ---------------------------------------------------------------------------
# route_alert — 4.3 severity routing
# ---------------------------------------------------------------------------

def test_route_critical_to_alert_chat():
    assert route_alert("CRITICAL", default_chat_id=111, alert_chat_id=999) == 999


def test_route_high_to_alert_chat():
    assert route_alert("HIGH", default_chat_id=111, alert_chat_id=999) == 999


def test_route_warning_to_alert_chat():
    assert route_alert("WARNING", default_chat_id=111, alert_chat_id=999) == 999


def test_route_medium_to_alert_chat():
    assert route_alert("MEDIUM", default_chat_id=111, alert_chat_id=999) == 999


def test_route_info_to_default_chat():
    assert route_alert("INFO", default_chat_id=111, alert_chat_id=999) == 111


def test_route_low_to_default_chat():
    assert route_alert("LOW", default_chat_id=111, alert_chat_id=999) == 111


def test_route_none_alert_chat_falls_back_for_critical():
    """alert_chat_id=None → all severities go to default_chat_id."""
    assert route_alert("CRITICAL", default_chat_id=111, alert_chat_id=None) == 111
    assert route_alert("WARNING", default_chat_id=111, alert_chat_id=None) == 111


def test_route_zero_alert_chat_falls_back():
    """alert_chat_id=0 is falsy → falls back to default."""
    assert route_alert("CRITICAL", default_chat_id=111, alert_chat_id=0) == 111


def test_route_case_insensitive():
    assert route_alert("critical", default_chat_id=111, alert_chat_id=999) == 999
    assert route_alert("info", default_chat_id=111, alert_chat_id=999) == 111


# ---------------------------------------------------------------------------
# dispatch_alert — 4.4 dedicated alert chat routing
# ---------------------------------------------------------------------------

def test_dispatch_critical_routes_to_alert_chat():
    calls: list = []
    result = dispatch_alert(
        _alert(severity="CRITICAL"),
        bot_token="tok-test",
        default_chat_id=100,
        alert_chat_id=200,
        _send_fn=_ok_sender(calls),
    )
    assert result["sent"] is True
    assert result["chat_id"] == 200
    assert len(calls) == 1
    assert calls[0]["chat_id"] == 200
    assert calls[0]["bot_token"] == "tok-test"


def test_dispatch_warning_routes_to_alert_chat():
    calls: list = []
    result = dispatch_alert(
        _alert(severity="WARNING"),
        bot_token="tok-w",
        default_chat_id=100,
        alert_chat_id=200,
        _send_fn=_ok_sender(calls),
    )
    assert result["chat_id"] == 200


def test_dispatch_info_routes_to_default_chat():
    calls: list = []
    result = dispatch_alert(
        _alert(severity="INFO"),
        bot_token="tok-i",
        default_chat_id=100,
        alert_chat_id=200,
        _send_fn=_ok_sender(calls),
    )
    assert result["sent"] is True
    assert result["chat_id"] == 100


def test_dispatch_no_alert_chat_all_go_to_default():
    calls: list = []
    result = dispatch_alert(
        _alert(severity="WARNING"),
        bot_token="tok-n",
        default_chat_id=100,
        alert_chat_id=None,
        _send_fn=_ok_sender(calls),
    )
    assert result["chat_id"] == 100


def test_dispatch_result_contains_check_code_and_severity():
    calls: list = []
    result = dispatch_alert(
        _alert(check_code="RC-6", severity="WARNING"),
        bot_token="tok-r",
        default_chat_id=100,
        alert_chat_id=200,
        _send_fn=_ok_sender(calls),
    )
    assert result["check_code"] == "RC-6"
    assert result["severity"] == "WARNING"
    assert "text_preview" in result


def test_dispatch_text_preview_capped_at_80_chars():
    calls: list = []
    result = dispatch_alert(
        _alert(verdict={k: "x" * 40 for k in ("reason", "expected", "actual")}),
        bot_token="tok-p",
        default_chat_id=100,
        alert_chat_id=None,
        _send_fn=_ok_sender(calls),
    )
    assert len(result["text_preview"]) <= 80


# ---------------------------------------------------------------------------
# dispatch_alert — error handling (TRANSIENT / PERMANENT)
# ---------------------------------------------------------------------------

def _http_error_sender(status_code: int):
    def _send(*, bot_token: str, chat_id: int, text: str) -> None:
        req = httpx.Request("POST", "https://api.telegram.org/bot***/sendMessage")
        resp = httpx.Response(status_code, request=req)
        raise httpx.HTTPStatusError(
            f"HTTP {status_code}", request=req, response=resp
        )
    return _send


def test_dispatch_4xx_raises_permanent_non_retriable():
    with pytest.raises(AlertDispatchError) as exc_info:
        dispatch_alert(
            _alert(),
            bot_token="bad-tok",
            default_chat_id=100,
            alert_chat_id=200,
            _send_fn=_http_error_sender(403),
        )
    err = exc_info.value
    assert err.error_class == "PERMANENT"
    assert err.retriable is False
    assert err.trace_id == "aaaa0000-0000-0000-0000-000000000000"


def test_dispatch_5xx_raises_transient_retriable():
    with pytest.raises(AlertDispatchError) as exc_info:
        dispatch_alert(
            _alert(trace_id="bbbb1111"),
            bot_token="tok-ok",
            default_chat_id=100,
            alert_chat_id=200,
            _send_fn=_http_error_sender(503),
        )
    err = exc_info.value
    assert err.error_class == "TRANSIENT"
    assert err.retriable is True
    assert err.trace_id == "bbbb1111"


def test_dispatch_network_error_raises_transient_retriable():
    def _timeout_sender(*, bot_token, chat_id, text):
        raise ConnectionError("network timeout")

    with pytest.raises(AlertDispatchError) as exc_info:
        dispatch_alert(
            _alert(trace_id="cccc2222"),
            bot_token="tok-ok",
            default_chat_id=100,
            alert_chat_id=200,
            _send_fn=_timeout_sender,
        )
    err = exc_info.value
    assert err.error_class == "TRANSIENT"
    assert err.retriable is True


def test_alert_dispatch_error_to_log_dict_no_secrets():
    """to_log_dict() must not expose bot_token."""
    err = AlertDispatchError(
        "boom",
        error_class="PERMANENT",
        severity_level="ERROR",
        retriable=False,
        trace_id="trace-xyz",
    )
    d = err.to_log_dict()
    assert d["error_class"] == "PERMANENT"
    assert d["retriable"] is False
    assert d["trace_id"] == "trace-xyz"
    # No raw token field present
    for v in d.values():
        assert "bot" not in str(v).lower()

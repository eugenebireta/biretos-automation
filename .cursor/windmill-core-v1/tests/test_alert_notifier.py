from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import requests


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _import_alert_notifier():
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module("alert_notifier")


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows = []

    def execute(self, query: str, params=()):
        normalized = " ".join(query.strip().lower().split())

        if normalized.startswith("insert into alert_telegram_log"):
            cooldown_key = str(params[7])
            if cooldown_key in self._conn.cooldown_to_id:
                self._rows = []
                return
            alert_id = f"00000000-0000-0000-0000-{self._conn.seq:012d}"
            self._conn.seq += 1
            self._conn.cooldown_to_id[cooldown_key] = alert_id
            self._conn.alert_rows[alert_id] = {
                "id": alert_id,
                "check_code": str(params[0]),
                "entity_id": str(params[1]),
                "telegram_message_id": None,
                "cooldown_key": cooldown_key,
                "sent": False,
            }
            self._rows = [(alert_id,)]
            return

        if normalized.startswith("update alert_telegram_log set telegram_message_id ="):
            telegram_message_id, alert_id = params
            row = self._conn.alert_rows.get(str(alert_id))
            if row is not None:
                row["telegram_message_id"] = telegram_message_id
                row["sent"] = True
            self._rows = []
            return

        if normalized.startswith("delete from alert_telegram_log where id ="):
            alert_id = str(params[0])
            row = self._conn.alert_rows.pop(alert_id, None)
            if row:
                self._conn.cooldown_to_id.pop(row["cooldown_key"], None)
            self._rows = []
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self):
        return None


class _Conn:
    def __init__(self) -> None:
        self.seq = 1
        self.alert_rows: Dict[str, Dict[str, Any]] = {}
        self.cooldown_to_id: Dict[str, str] = {}
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _Response:
    def __init__(self, *, ok: bool = True, status_code: int = 200, message_id: int = 101) -> None:
        self.status_code = status_code
        self._ok = ok
        self._message_id = message_id

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self._ok:
            return {"ok": True, "result": {"message_id": self._message_id}}
        return {"ok": False, "error_code": 400, "description": "bad request"}


def _sample_verdict() -> Dict[str, Any]:
    return {
        "check_name": "IC-9",
        "entity_type": "payment_transaction",
        "entity_id": "global",
        "verdict": "STALE",
        "severity": "CRITICAL",
        "details": {"count": 2},
    }


def test_format_alert_message_contains_core_fields():
    notifier = _import_alert_notifier()
    verdict = _sample_verdict()
    msg = notifier._format_alert_message(verdict, trace_id="trace-1")
    assert "IC-9 = STALE" in msg
    assert "CRITICAL IC/RC Alert" in msg
    assert "Entity: payment_transaction global" in msg
    assert "Severity: CRITICAL" in msg
    assert "Trace: trace-1" in msg


def test_build_cooldown_key_uses_hour_bucket():
    notifier = _import_alert_notifier()
    now_ts = datetime(2026, 3, 2, 14, 35, 0, tzinfo=timezone.utc)
    key = notifier._build_cooldown_key("IC-9", "global", now_ts)
    assert key == "IC-9:global:2026-03-02-14"


def test_reserve_before_send_dedups_second_call(monkeypatch):
    notifier = _import_alert_notifier()
    conn = _Conn()
    verdict = _sample_verdict()
    now_ts = datetime(2026, 3, 2, 14, 10, 0, tzinfo=timezone.utc)

    calls = {"count": 0}

    def _ok_post(*_args, **_kwargs):
        calls["count"] += 1
        return _Response(ok=True, message_id=777)

    monkeypatch.setattr(notifier.requests, "post", _ok_post)

    first = notifier._deliver_verdict_alert(
        conn,
        verdict,
        chat_id=123456789,
        bot_token="token",
        trace_id="trace-a",
        now_ts=now_ts,
    )
    second = notifier._deliver_verdict_alert(
        conn,
        verdict,
        chat_id=123456789,
        bot_token="token",
        trace_id="trace-a",
        now_ts=now_ts,
    )

    assert first["status"] == "sent"
    assert second["status"] == "deduped"
    assert calls["count"] == 1


def test_success_updates_telegram_message_id(monkeypatch):
    notifier = _import_alert_notifier()
    conn = _Conn()
    verdict = _sample_verdict()
    now_ts = datetime(2026, 3, 2, 15, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(
        notifier.requests,
        "post",
        lambda *_args, **_kwargs: _Response(ok=True, message_id=9001),
    )

    result = notifier._deliver_verdict_alert(
        conn,
        verdict,
        chat_id=123456789,
        bot_token="token",
        trace_id="trace-b",
        now_ts=now_ts,
    )

    assert result["status"] == "sent"
    assert conn.commits == 1
    row = next(iter(conn.alert_rows.values()))
    assert row["telegram_message_id"] == 9001
    assert row["sent"] is True


def test_send_failure_deletes_reservation_and_allows_retry(monkeypatch):
    notifier = _import_alert_notifier()
    conn = _Conn()
    verdict = _sample_verdict()
    now_ts = datetime(2026, 3, 2, 16, 0, 0, tzinfo=timezone.utc)

    calls = {"count": 0}

    def _flaky_post(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise requests.RequestException("network down")
        return _Response(ok=True, message_id=42)

    monkeypatch.setattr(notifier.requests, "post", _flaky_post)

    first = notifier._deliver_verdict_alert(
        conn,
        verdict,
        chat_id=123456789,
        bot_token="token",
        trace_id="trace-c",
        now_ts=now_ts,
    )
    assert first["status"] == "send_error"
    assert conn.alert_rows == {}
    assert conn.cooldown_to_id == {}

    second = notifier._deliver_verdict_alert(
        conn,
        verdict,
        chat_id=123456789,
        bot_token="token",
        trace_id="trace-c",
        now_ts=now_ts,
    )
    assert second["status"] == "sent"
    assert calls["count"] == 2


def test_should_send_respects_threshold():
    notifier = _import_alert_notifier()
    assert notifier._should_send("WARNING", "WARNING") is True
    assert notifier._should_send("INFO", "WARNING") is False
    assert notifier._should_send("CRITICAL", "WARNING") is True
    assert notifier._should_send("CRITICAL", "CRITICAL") is True
    assert notifier._should_send("WARNING", "CRITICAL") is False


def test_resolve_chat_id_critical_override():
    notifier = _import_alert_notifier()
    chat_id = notifier._resolve_chat_id(
        "CRITICAL",
        default_chat_id=123,
        critical_chat_id=999,
        warning_chat_id=456,
    )
    assert chat_id == 999


def test_resolve_chat_id_fallback_to_default():
    notifier = _import_alert_notifier()
    chat_id = notifier._resolve_chat_id(
        "CRITICAL",
        default_chat_id=123,
        critical_chat_id=None,
        warning_chat_id=456,
    )
    assert chat_id == 123


def test_resolve_chat_id_returns_none_when_all_none():
    notifier = _import_alert_notifier()
    chat_id = notifier._resolve_chat_id(
        "WARNING",
        default_chat_id=None,
        critical_chat_id=None,
        warning_chat_id=None,
    )
    assert chat_id is None


def test_format_message_includes_severity_emoji():
    notifier = _import_alert_notifier()
    critical_msg = notifier._format_alert_message(_sample_verdict(), trace_id="trace-critical")
    warning_verdict = dict(_sample_verdict())
    warning_verdict["severity"] = "WARNING"
    warning_msg = notifier._format_alert_message(warning_verdict, trace_id="trace-warning")
    assert "\U0001f534" in critical_msg
    assert "\u26a0\ufe0f" in warning_msg

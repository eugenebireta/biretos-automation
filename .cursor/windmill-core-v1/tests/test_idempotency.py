from __future__ import annotations

import importlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ru_worker_dir() -> Path:
    return _project_root() / "ru_worker"


if str(_ru_worker_dir()) not in sys.path:
    sys.path.insert(0, str(_ru_worker_dir()))
if str(_project_root()) not in sys.path:
    sys.path.insert(0, str(_project_root()))

# Ensure config validation passes during module import (dispatch_action imports get_config() at import time).
# Dummy values only; no secrets required for unit tests.
_TEST_ENV_DEFAULTS = {
    "TELEGRAM_BOT_TOKEN": "test-token",
    "TELEGRAM_WEBHOOK_SECRET": "test-secret",
    "TBANK_API_TOKEN": "test-token",
    "TBANK_API_BASE": "https://example.test",
    "CDEK_CLIENT_ID": "test-id",
    "CDEK_CLIENT_SECRET": "test-secret",
    "POSTGRES_PASSWORD": "test-password",
    # Optional paths referenced by integration helpers.
    "TBANK_INVOICE_STATUS_PATH": "/invoice/{invoice_id}/status",
    "TBANK_INVOICES_LIST_PATH": "/invoice/list",
}
for _k, _v in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(_k, _v)

idempotency = importlib.import_module("idempotency")
dispatch_action_module = importlib.import_module("dispatch_action")


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows = []
        self.rowcount = 0

    def execute(self, query: str, params=None):
        params = params or ()
        normalized = " ".join(query.strip().lower().split())
        self.rowcount = 0
        self._rows = []

        if normalized.startswith("insert into action_idempotency_log"):
            key, action_type, request_hash, lease_token, ttl_seconds, trace_id = params
            if key in self._conn.rows:
                self.rowcount = 0
                return
            ttl_int = int(ttl_seconds)
            self._conn.rows[key] = {
                "idempotency_key": key,
                "action_type": action_type,
                "request_hash": request_hash,
                "status": "processing",
                "lease_token": str(lease_token),
                "acquired_at": self._conn.now,
                "expires_at": self._conn.now + timedelta(seconds=ttl_int),
                "attempt_count": 1,
                "last_error": None,
                "result_ref": None,
                "trace_id": str(trace_id) if trace_id is not None else None,
                "created_at": self._conn.now,
                "updated_at": self._conn.now,
            }
            self.rowcount = 1
            return

        if normalized.startswith("select status, expires_at, result_ref, last_error, attempt_count from action_idempotency_log"):
            key = params[0]
            row = self._conn.rows.get(key)
            if row is None:
                self._rows = []
            else:
                self._rows = [
                    (
                        row["status"],
                        row["expires_at"],
                        row["result_ref"],
                        row["last_error"],
                        row["attempt_count"],
                    )
                ]
            return

        if normalized.startswith("select now()"):
            self._rows = [(self._conn.now,)]
            return

        if normalized.startswith("update action_idempotency_log set lease_token = %s::uuid"):
            new_lease_token, ttl_seconds, next_attempt, request_hash, trace_id, key = params
            row = self._conn.rows.get(key)
            if row and row["status"] == "processing":
                row["lease_token"] = str(new_lease_token)
                row["expires_at"] = self._conn.now + timedelta(seconds=int(ttl_seconds))
                row["attempt_count"] = int(next_attempt)
                row["request_hash"] = request_hash
                row["trace_id"] = str(trace_id) if trace_id is not None else None
                row["updated_at"] = self._conn.now
                self.rowcount = 1
            return

        if normalized.startswith("update action_idempotency_log set status = %s, result_ref = %s::jsonb"):
            status, result_ref_json, last_error, key, lease_token = params
            row = self._conn.rows.get(key)
            if row and row["status"] == "processing" and row["lease_token"] == str(lease_token):
                row["status"] = status
                row["result_ref"] = json.loads(result_ref_json) if result_ref_json is not None else None
                row["last_error"] = last_error
                row["expires_at"] = datetime(1970, 1, 1, tzinfo=timezone.utc)
                row["updated_at"] = self._conn.now
                self.rowcount = 1
            return

        if normalized.startswith("update action_idempotency_log set status = 'failed', last_error = 'lock_expired_by_sweeper'"):
            returned = []
            for row in self._conn.rows.values():
                if row["status"] == "processing" and row["expires_at"] < self._conn.now:
                    row["status"] = "failed"
                    row["last_error"] = "lock_expired_by_sweeper"
                    row["lease_token"] = str(uuid4())
                    row["updated_at"] = self._conn.now
                    returned.append(
                        (
                            row["idempotency_key"],
                            row["action_type"],
                            row["attempt_count"],
                            row["trace_id"],
                        )
                    )
            self._rows = returned
            self.rowcount = len(returned)
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows = self._rows
        self._rows = []
        return rows

    def close(self):
        return None


class _Conn:
    def __init__(self) -> None:
        self.rows = {}
        self.now = datetime.now(timezone.utc)
        self.commit_calls = 0
        self.rollback_calls = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def advance(self, seconds: int):
        self.now = self.now + timedelta(seconds=seconds)


def _guarded_ship_action(invoice_id: str = "INV-001"):
    return {
        "action_type": "ship_paid",
        "payload": {"invoice_id": invoice_id},
        "source": "test",
        "metadata": {"user_id": 1, "chat_id": 2},
    }


def test_t1_generate_key_ship_paid():
    assert idempotency.generate_idempotency_key(_guarded_ship_action("INV-777")) == "ship_paid:INV-777"


def test_t2_generate_key_ship_paid_missing_invoice():
    action = _guarded_ship_action("")
    assert idempotency.generate_idempotency_key(action) is None


def test_t3_read_only_action_has_no_key():
    action = {"action_type": "tbank_invoice_status", "payload": {"invoice_id": "INV-1"}}
    assert idempotency.generate_idempotency_key(action) is None


def test_t4_auto_ship_all_paid_has_no_key():
    action = {"action_type": "auto_ship_all_paid", "payload": {}}
    assert idempotency.generate_idempotency_key(action) is None


def test_t5_tbank_payment_key_coarse_is_supported():
    action = {
        "action_type": "tbank_payment",
        "payload": {"amount": 1500, "currency": "rub"},
    }
    assert idempotency.generate_idempotency_key(action) == "tbank_payment:1500:RUB"


def test_t6_hash_stable_for_same_payload():
    payload = {"invoice_id": "INV-1", "metadata": {"timestamp": 123}}
    h1 = idempotency.compute_request_hash("ship_paid", payload)
    h2 = idempotency.compute_request_hash("ship_paid", payload)
    assert h1 == h2


def test_t7_hash_excludes_non_business_fields():
    payload_a = {
        "to_location": {"code": "MSK"},
        "packages": [{"weight": 1}],
        "metadata": {"chat_id": 1, "timestamp": 111},
        "trace_id": "t1",
    }
    payload_b = {
        "to_location": {"code": "MSK"},
        "packages": [{"weight": 1}],
        "metadata": {"chat_id": 999, "timestamp": 222},
        "trace_id": "t2",
    }
    assert idempotency.compute_request_hash("cdek_shipment", payload_a) == idempotency.compute_request_hash(
        "cdek_shipment", payload_b
    )


def test_t8_hash_is_sha256_shape():
    payload = {"amount": 100, "currency": "RUB"}
    digest = idempotency.compute_request_hash("tbank_payment", payload)
    assert len(digest) == 64
    assert all(ch in "0123456789abcdef" for ch in digest)


def test_t9_real_without_db_conn_raises():
    # trace_id required by B1 (Task 5.2); pass it so we reach the RuntimeError
    with pytest.raises(RuntimeError):
        dispatch_action_module.dispatch_action(
            _guarded_ship_action("INV-100"), mode="REAL", db_conn=None, trace_id="t-t9"
        )


def test_t9b_idempotency_ttl_default_used_when_env_missing_or_invalid(monkeypatch):
    captured = {}

    def _fake_acquire_action_lock(**kwargs):
        captured["ttl_seconds"] = kwargs.get("ttl_seconds")
        return {"status": "DUPLICATE_PROCESSING", "attempt_count": 1}

    monkeypatch.setattr(dispatch_action_module, "acquire_action_lock", _fake_acquire_action_lock)

    for value in (None, "not-an-int", ""):
        captured.clear()
        if value is None:
            monkeypatch.delenv("ACTION_IDEMPOTENCY_TTL_SECONDS", raising=False)
        else:
            monkeypatch.setenv("ACTION_IDEMPOTENCY_TTL_SECONDS", value)

        result = dispatch_action_module.dispatch_action(
            _guarded_ship_action("INV-TTL-DEFAULT"),
            mode="REAL",
            db_conn=object(),
            trace_id="t-default",
        )
        assert result["status"] == "duplicate"
        assert result["duplicate_status"] == "processing"
        assert captured["ttl_seconds"] == 300


def test_t9c_idempotency_ttl_env_override_used(monkeypatch):
    captured = {}

    def _fake_acquire_action_lock(**kwargs):
        captured["ttl_seconds"] = kwargs.get("ttl_seconds")
        return {"status": "DUPLICATE_PROCESSING", "attempt_count": 1}

    monkeypatch.setattr(dispatch_action_module, "acquire_action_lock", _fake_acquire_action_lock)
    monkeypatch.setenv("ACTION_IDEMPOTENCY_TTL_SECONDS", "600")

    result = dispatch_action_module.dispatch_action(
        _guarded_ship_action("INV-TTL-OVERRIDE"),
        mode="REAL",
        db_conn=object(),
        trace_id="t-override",
    )
    assert result["status"] == "duplicate"
    assert result["duplicate_status"] == "processing"
    assert captured["ttl_seconds"] == 600


def test_t10_acquire_new_lock():
    conn = _Conn()
    result = idempotency.acquire_action_lock(conn, "ship_paid:INV-1", "ship_paid", "h1", None)
    assert result["status"] == "ACQUIRED"
    assert "lease_token" in result


def test_t11_duplicate_succeeded_returns_cached_result():
    conn = _Conn()
    first = idempotency.acquire_action_lock(conn, "ship_paid:INV-2", "ship_paid", "h2", None)
    assert first["status"] == "ACQUIRED"
    ok = idempotency.complete_action(
        conn,
        "ship_paid:INV-2",
        first["lease_token"],
        "succeeded",
        {"status": "success", "action_type": "ship_paid", "result": {"tracking_number": "TRK-1"}},
    )
    assert ok is True
    second = idempotency.acquire_action_lock(conn, "ship_paid:INV-2", "ship_paid", "h2", None)
    assert second["status"] == "DUPLICATE_SUCCEEDED"
    assert second["result_ref"]["result"]["tracking_number"] == "TRK-1"


def test_t12_duplicate_processing_detected():
    conn = _Conn()
    first = idempotency.acquire_action_lock(conn, "ship_paid:INV-3", "ship_paid", "h3", None)
    assert first["status"] == "ACQUIRED"
    second = idempotency.acquire_action_lock(conn, "ship_paid:INV-3", "ship_paid", "h3", None)
    assert second["status"] == "DUPLICATE_PROCESSING"


def test_t13_stale_takeover():
    conn = _Conn()
    first = idempotency.acquire_action_lock(conn, "ship_paid:INV-4", "ship_paid", "h4", None, ttl_seconds=10)
    assert first["status"] == "ACQUIRED"
    conn.advance(11)
    second = idempotency.acquire_action_lock(conn, "ship_paid:INV-4", "ship_paid", "h4", None, ttl_seconds=10)
    assert second["status"] == "STALE_TAKEOVER"
    assert second["lease_token"] != first["lease_token"]


def test_t14_complete_with_correct_token():
    conn = _Conn()
    lock = idempotency.acquire_action_lock(conn, "ship_paid:INV-5", "ship_paid", "h5", None)
    ok = idempotency.complete_action(conn, "ship_paid:INV-5", lock["lease_token"], "succeeded", {"status": "success"})
    assert ok is True
    assert conn.rows["ship_paid:INV-5"]["status"] == "succeeded"


def test_t15_complete_with_wrong_token_rejected():
    conn = _Conn()
    lock = idempotency.acquire_action_lock(conn, "ship_paid:INV-6", "ship_paid", "h6", None)
    ok = idempotency.complete_action(conn, "ship_paid:INV-6", "deadbeef-dead-beef-dead-beefdeadbeef", "succeeded")
    assert ok is False
    assert conn.rows["ship_paid:INV-6"]["status"] == "processing"
    assert conn.rows["ship_paid:INV-6"]["lease_token"] == lock["lease_token"]


def test_t16_complete_after_sweeper_rejected():
    conn = _Conn()
    lock = idempotency.acquire_action_lock(conn, "ship_paid:INV-7", "ship_paid", "h7", None, ttl_seconds=5)
    conn.advance(10)
    swept = idempotency.sweep_expired_locks(conn)
    assert swept == 1
    ok = idempotency.complete_action(conn, "ship_paid:INV-7", lock["lease_token"], "succeeded")
    assert ok is False
    assert conn.rows["ship_paid:INV-7"]["status"] == "failed"


def test_t17_sweeper_marks_expired_as_failed():
    conn = _Conn()
    idempotency.acquire_action_lock(conn, "ship_paid:INV-8", "ship_paid", "h8", None, ttl_seconds=1)
    conn.advance(2)
    swept = idempotency.sweep_expired_locks(conn)
    assert swept == 1
    assert conn.rows["ship_paid:INV-8"]["status"] == "failed"
    assert conn.rows["ship_paid:INV-8"]["last_error"] == "lock_expired_by_sweeper"


def test_t18_sweeper_is_idempotent():
    conn = _Conn()
    idempotency.acquire_action_lock(conn, "ship_paid:INV-9", "ship_paid", "h9", None, ttl_seconds=1)
    conn.advance(2)
    first = idempotency.sweep_expired_locks(conn)
    second = idempotency.sweep_expired_locks(conn)
    assert first == 1
    assert second == 0


def test_t19_double_ship_paid_single_side_effect(monkeypatch):
    conn = _Conn()
    calls = {"cdek": 0}

    def _invoice_status(_config, _payload):
        return {"status": "success", "result_status": "paid", "response": {"invoice_id": "INV-10"}}

    def _mapper(_config, invoice_id, _invoice_response):
        return ({"invoice_id": invoice_id, "payload": "mapped"}, None)

    def _cdek(_config, payload):
        calls["cdek"] += 1
        return {"status": "success", "response": {"uuid": f"TRK-{payload.get('invoice_id', 'X')}"}}

    monkeypatch.setattr(dispatch_action_module, "execute_tbank_invoice_status", _invoice_status)
    monkeypatch.setattr(dispatch_action_module, "map_tbank_invoice_to_cdek_payload", _mapper)
    monkeypatch.setattr(dispatch_action_module, "execute_cdek_shipment", _cdek)

    action = _guarded_ship_action("INV-10")
    first = dispatch_action_module.dispatch_action(action, mode="REAL", db_conn=conn, trace_id="trace-1")
    second = dispatch_action_module.dispatch_action(action, mode="REAL", db_conn=conn, trace_id="trace-1")

    assert first["status"] == "success"
    assert second["status"] == "success"
    assert calls["cdek"] == 1


def test_t20_auto_ship_all_paid_fan_out(monkeypatch):
    conn = _Conn()
    calls = {"cdek": 0}

    def _invoices(_config, _payload):
        return {
            "status": "success",
            "invoices": [
                {"invoice_id": "INV-A", "status": "paid"},
                {"invoice_id": "INV-B", "status": "paid"},
                {"invoice_id": "INV-C", "status": "unpaid"},
            ],
        }

    def _invoice_status(_config, payload):
        return {"status": "success", "result_status": "paid", "response": {"invoice_id": payload.get("invoice_id")}}

    def _mapper(_config, invoice_id, _invoice_response):
        return ({"invoice_id": invoice_id, "payload": "mapped"}, None)

    def _cdek(_config, payload):
        calls["cdek"] += 1
        return {"status": "success", "response": {"uuid": f"TRK-{payload.get('invoice_id', 'X')}"}}

    monkeypatch.setattr(dispatch_action_module, "execute_tbank_invoices_list", _invoices)
    monkeypatch.setattr(dispatch_action_module, "execute_tbank_invoice_status", _invoice_status)
    monkeypatch.setattr(dispatch_action_module, "map_tbank_invoice_to_cdek_payload", _mapper)
    monkeypatch.setattr(dispatch_action_module, "execute_cdek_shipment", _cdek)

    action = {
        "action_type": "auto_ship_all_paid",
        "payload": {},
        "source": "test",
        "metadata": {"chat_id": 1, "user_id": 1},
    }
    result = dispatch_action_module.dispatch_action(action, mode="REAL", db_conn=conn, trace_id="trace-2")

    assert result["status"] == "success"
    assert result["processed_count"] == 2
    assert calls["cdek"] == 2
    assert "ship_paid:INV-A" in conn.rows
    assert "ship_paid:INV-B" in conn.rows


def test_t21_dry_run_real_actions_work_without_db():
    action = _guarded_ship_action("INV-DRY")
    # trace_id required by B1 (Task 5.2)
    result = dispatch_action_module.dispatch_action(action, mode="DRY_RUN", db_conn=None, trace_id="t-dry")
    assert result["status"] == "success"
    assert result["dry_run"] is True


def test_t22_dry_run_does_not_write_idempotency_rows():
    conn = _Conn()
    action = _guarded_ship_action("INV-DRY-2")
    result = dispatch_action_module.dispatch_action(action, mode="DRY_RUN", db_conn=conn, trace_id="trace-dry")
    assert result["status"] == "success"
    assert conn.rows == {}

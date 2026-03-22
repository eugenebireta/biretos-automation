"""
Tests for ru_worker/nlu_confirmation_store.py — Phase 7.9.
Pure unit tests: stub DB, no live Postgres, deterministic.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _ensure_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_path()

import json
import uuid
from domain.nlu_models import NLUConfig
from domain.assistant_models import ConfirmationPending
from domain.intent_parser import parse_intent
from ru_worker.nlu_confirmation_store import (
    store_confirmation,
    get_and_consume,
    expire_stale,
)


# ---------------------------------------------------------------------------
# Stub DB
# ---------------------------------------------------------------------------

class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn

    def execute(self, query: str, params=None) -> None:
        self._conn.queries.append((query, params))
        q = query.strip().lower()
        if "returning" in q and "insert" in q:
            self._conn._last = (str(uuid.uuid4()),)
        elif "update" in q and "returning" in q and self._conn._pending_row:
            row = self._conn._pending_row
            self._conn._last = row
            self._conn._pending_row = None  # consumed
        elif "update" in q and "status = 'expired'" in q:
            self._conn._rowcount = self._conn._stale_count
            self._conn._last = None
        else:
            self._conn._last = None

    def fetchone(self):
        return self._conn._last

    @property
    def rowcount(self):
        return self._conn._rowcount

    def close(self):
        pass


class _Conn:
    def __init__(self, pending_row=None, stale_count: int = 0) -> None:
        self.queries = []
        self.committed = False
        self._last = None
        self._pending_row = pending_row
        self._stale_count = stale_count
        self._rowcount = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.committed = True


def _make_parsed():
    cfg = NLUConfig(
        nlu_enabled=True, degradation_level=0, confidence_threshold=0.80,
        shadow_mode=False, model_version="regex-v1", prompt_version="v1.0",
        max_input_bytes=1024,
    )
    result = parse_intent("проверить платёж INV-001", cfg)
    return result.parsed


# ---------------------------------------------------------------------------
# store_confirmation
# ---------------------------------------------------------------------------

def test_store_confirmation_inserts_row():
    conn = _Conn()
    parsed = _make_parsed()
    conf_id = store_confirmation(
        conn,
        trace_id="trace-store-001",
        employee_id="emp-1",
        employee_role="operator",
        parsed=parsed,
    )
    assert isinstance(conf_id, str)
    assert len(conf_id) > 0
    assert any("insert" in q[0].lower() for q in conn.queries)


def test_store_confirmation_returns_uuid_string():
    conn = _Conn()
    parsed = _make_parsed()
    conf_id = store_confirmation(
        conn,
        trace_id="trace-store-002",
        employee_id="emp-2",
        employee_role="manager",
        parsed=parsed,
    )
    # Should be a valid UUID string
    uuid.UUID(conf_id)  # raises if invalid


# ---------------------------------------------------------------------------
# get_and_consume
# ---------------------------------------------------------------------------

def _pending_row_tuple():
    row_id = str(uuid.uuid4())
    return (
        row_id, "trace-consume-001", "emp-1", "operator",
        "check_payment", json.dumps({"invoice_id": "INV-001"}),
        "regex-v1", "v1.0", "0.9999",
    )


def test_get_and_consume_returns_confirmation_pending():
    conn = _Conn(pending_row=_pending_row_tuple())
    result = get_and_consume(conn, "some-uuid")
    assert isinstance(result, ConfirmationPending)
    assert result.parsed_intent_type == "check_payment"
    assert result.parsed_entities == {"invoice_id": "INV-001"}


def test_get_and_consume_returns_none_when_expired():
    conn = _Conn(pending_row=None)
    result = get_and_consume(conn, "expired-uuid")
    assert result is None


def test_get_and_consume_double_consume_returns_none():
    conn = _Conn(pending_row=_pending_row_tuple())
    first = get_and_consume(conn, "some-uuid")
    # Second call — pending_row is now None (consumed)
    second = get_and_consume(conn, "some-uuid")
    assert first is not None
    assert second is None


def test_get_and_consume_confidence_as_float():
    conn = _Conn(pending_row=_pending_row_tuple())
    result = get_and_consume(conn, "some-uuid")
    assert isinstance(result.confidence, float)


# ---------------------------------------------------------------------------
# expire_stale
# ---------------------------------------------------------------------------

def test_expire_stale_returns_count():
    conn = _Conn(stale_count=3)
    count = expire_stale(conn)
    assert count == 3


def test_expire_stale_issues_update():
    conn = _Conn(stale_count=0)
    expire_stale(conn)
    assert any("update" in q[0].lower() for q in conn.queries)

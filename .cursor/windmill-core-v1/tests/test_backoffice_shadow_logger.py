"""
Tests for ru_worker/backoffice_shadow_logger.py — Phase 6.9.
Pure unit tests: stub DB, deterministic.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_path()

from ru_worker.backoffice_shadow_logger import write_shadow_rag_entry


# ---------------------------------------------------------------------------
# Stub DB
# ---------------------------------------------------------------------------

class _ShadowCursor:
    def __init__(self, conn: "_ShadowConn") -> None:
        self._conn = conn

    def execute(self, query: str, params=None) -> None:
        self._conn.entries.append(params)

    def close(self):
        pass


class _ShadowConn:
    def __init__(self) -> None:
        self.entries: list = []

    def cursor(self):
        return _ShadowCursor(self)


class _BrokenConn:
    """Simulates DB failure."""
    def cursor(self):
        raise RuntimeError("DB connection lost")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_write_shadow_entry_success():
    conn = _ShadowConn()
    result = write_shadow_rag_entry(
        conn,
        trace_id="trace-rag-001",
        employee_id="emp-42",
        intent_type="check_payment",
        context_json={"invoice_id": "INV-001", "outcome": "success"},
        response_summary="payment ok",
    )
    assert result["action"] == "created"
    assert len(conn.entries) == 1


def test_write_shadow_entry_fire_and_forget_on_db_error():
    """DB failure must NOT raise — returns error dict."""
    conn = _BrokenConn()
    result = write_shadow_rag_entry(
        conn,
        trace_id="trace-rag-002",
        employee_id="emp-43",
        intent_type="get_tracking",
        context_json={},
    )
    assert result["action"] == "error"
    assert result["retriable"] is True
    assert "error" in result


def test_write_shadow_entry_no_response_summary():
    conn = _ShadowConn()
    result = write_shadow_rag_entry(
        conn,
        trace_id="trace-rag-003",
        employee_id="emp-1",
        intent_type="get_waybill",
        context_json={"outcome": "success"},
        response_summary=None,
    )
    assert result["action"] == "created"

"""
Tests for ru_worker/nlu_sla_tracker.py — Phase 7.9.
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

from ru_worker.nlu_sla_tracker import record_nlu_sla, get_sla_stats


# ---------------------------------------------------------------------------
# Stub DB
# ---------------------------------------------------------------------------

class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn

    def execute(self, query: str, params=None) -> None:
        self._conn.queries.append((query, params))

    def fetchone(self):
        return self._conn._stats_row

    def fetchall(self):
        return self._conn._status_rows

    def close(self):
        pass


class _Conn:
    def __init__(self, stats_row=None, status_rows=None) -> None:
        self.queries = []
        self._stats_row = stats_row or (0, 0, 0, 0, 0)
        self._status_rows = status_rows or []

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        pass


# ---------------------------------------------------------------------------
# record_nlu_sla
# ---------------------------------------------------------------------------

def test_record_nlu_sla_inserts_row():
    conn = _Conn()
    record_nlu_sla(
        conn,
        trace_id="trace-sla-001",
        employee_id="emp-1",
        intent_type="check_payment",
        model_version="regex-v1",
        prompt_version="v1.0",
        degradation_level=0,
        parse_duration_ms=12,
        total_duration_ms=45,
        status="ok",
    )
    assert len(conn.queries) == 1
    assert "insert" in conn.queries[0][0].lower()


def test_record_nlu_sla_swallows_db_error():
    """Fire-and-forget: exceptions must not propagate."""

    class _FailConn:
        def cursor(self):
            raise RuntimeError("DB is down")
        def commit(self):
            pass

    # Must not raise
    record_nlu_sla(
        _FailConn(),
        trace_id="trace-sla-fail",
        employee_id="emp-x",
        intent_type=None,
        model_version="regex-v1",
        prompt_version="v1.0",
        degradation_level=2,
        parse_duration_ms=0,
        total_duration_ms=0,
        status="button_only",
    )


# ---------------------------------------------------------------------------
# get_sla_stats
# ---------------------------------------------------------------------------

def test_get_sla_stats_returns_dict():
    conn = _Conn(
        stats_row=(100, 90, 15, 50, 120),
        status_rows=[("ok", 90), ("fallback", 10)],
    )
    stats = get_sla_stats(conn, hours=1)
    assert isinstance(stats, dict)
    assert stats["total"] == 100
    assert stats["ok_count"] == 90
    assert stats["p50_ms"] == 15
    assert stats["p95_ms"] == 50
    assert stats["p99_ms"] == 120


def test_get_sla_stats_success_rate_calculation():
    conn = _Conn(
        stats_row=(200, 150, 10, 30, 80),
        status_rows=[("ok", 150), ("fallback", 50)],
    )
    stats = get_sla_stats(conn)
    assert stats["success_rate"] == round(150 / 200, 4)


def test_get_sla_stats_zero_total():
    conn = _Conn(stats_row=(0, 0, 0, 0, 0), status_rows=[])
    stats = get_sla_stats(conn)
    assert stats["total"] == 0
    assert stats["success_rate"] == 0.0


def test_get_sla_stats_swallows_db_error():
    class _FailConn:
        def cursor(self):
            raise RuntimeError("DB is down")

    stats = get_sla_stats(_FailConn())
    assert "error" in stats
    assert stats["total"] == 0


def test_get_sla_stats_by_status_dict():
    conn = _Conn(
        stats_row=(10, 7, 5, 15, 25),
        status_rows=[("ok", 7), ("fallback", 2), ("button_only", 1)],
    )
    stats = get_sla_stats(conn)
    assert stats["by_status"] == {"ok": 7, "fallback": 2, "button_only": 1}

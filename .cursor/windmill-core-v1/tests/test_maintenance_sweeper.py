from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_import_paths() -> None:
    root = _project_root()
    ru_worker_dir = root / "ru_worker"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if str(ru_worker_dir) not in sys.path:
        sys.path.insert(0, str(ru_worker_dir))


def _import_maintenance_sweeper():
    _ensure_import_paths()
    return importlib.import_module("maintenance_sweeper")


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows: List[Any] = []

    def execute(self, query: str, params=None) -> None:
        params = params or ()
        normalized = " ".join(query.strip().lower().split())
        if normalized.startswith("select id from review_cases where status = 'executing'"):
            # Threshold selection is validated by test inputs; we return pre-canned rows.
            limit = int(params[0]) if params else 0
            self._rows = [(cid,) for cid in self._conn.stuck_case_ids[:limit]]
            return
        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchall(self):
        return list(self._rows)

    def close(self) -> None:
        return None


class _Conn:
    def __init__(self, *, stuck_case_ids: Optional[List[str]] = None) -> None:
        self.stuck_case_ids = list(stuck_case_ids or [])

    def cursor(self) -> _Cursor:
        return _Cursor(self)


def _install_fake_ru_worker(monkeypatch, calls: Dict[str, Any], *, raises_duplicate: bool = False) -> None:
    fake = ModuleType("ru_worker")

    def enqueue_job_with_trace(db_conn, job_type: str, payload: Dict[str, Any], idempotency_key: str, trace_id: Optional[str]):
        calls.setdefault("enqueues", []).append(
            {
                "job_type": job_type,
                "payload": payload,
                "idempotency_key": idempotency_key,
                "trace_id": trace_id,
            }
        )
        if raises_duplicate:
            raise RuntimeError("duplicate key value violates unique constraint")
        return uuid4()

    fake.enqueue_job_with_trace = enqueue_job_with_trace  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ru_worker", fake)


def test_watchdog_1_enqueues_stuck_case(monkeypatch):
    ms = _import_maintenance_sweeper()
    calls: Dict[str, Any] = {}
    _install_fake_ru_worker(monkeypatch, calls)

    conn = _Conn(stuck_case_ids=["case-1"])
    out = ms._run_governance_watchdog(conn, trace_id="t1", threshold_minutes=15, limit=20)
    assert out == 1
    assert len(calls["enqueues"]) == 1
    enq = calls["enqueues"][0]
    assert enq["job_type"] == "governance_execute"
    assert enq["payload"] == {"case_id": "case-1"}
    assert enq["idempotency_key"].startswith("gov_watch:case-1:")
    assert enq["trace_id"] == "t1"


def test_watchdog_2_no_enqueue_when_none_stuck(monkeypatch):
    ms = _import_maintenance_sweeper()
    calls: Dict[str, Any] = {}
    _install_fake_ru_worker(monkeypatch, calls)

    conn = _Conn(stuck_case_ids=[])
    out = ms._run_governance_watchdog(conn, trace_id="t1", threshold_minutes=15, limit=20)
    assert out == 0
    assert calls.get("enqueues") is None


def test_watchdog_3_duplicate_enqueue_is_handled(monkeypatch):
    ms = _import_maintenance_sweeper()
    calls: Dict[str, Any] = {}
    _install_fake_ru_worker(monkeypatch, calls, raises_duplicate=True)

    conn = _Conn(stuck_case_ids=["case-dup"])
    out = ms._run_governance_watchdog(conn, trace_id="t1", threshold_minutes=15, limit=20)
    assert out == 1
    assert calls["enqueues"][0]["idempotency_key"].startswith("gov_watch:case-dup:")


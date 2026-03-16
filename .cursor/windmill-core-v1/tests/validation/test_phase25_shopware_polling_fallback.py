from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


_ROOT = Path(__file__).resolve().parents[2]
_WORKERS = _ROOT / "workers"
for _p in (_ROOT, _WORKERS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

polling = importlib.import_module("shopware_order_polling_fallback")


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows: List[Any] = []

    def execute(self, query: str, params: Optional[tuple[Any, ...]] = None) -> None:
        params = params or ()
        normalized = " ".join(query.strip().lower().split())

        if normalized.startswith("create table if not exists wm_state"):
            self._rows = []
            return

        if normalized.startswith("select value from wm_state where key = %s"):
            key = params[0]
            value = self._conn.state.get(key)
            self._rows = [(value,)] if value is not None else []
            return

        if normalized.startswith("insert into wm_state"):
            key, value_json = params
            self._conn.state[key] = json.loads(value_json)
            self._rows = []
            return

        if normalized.startswith("insert into shopware_inbound_events"):
            _, event_id, *_rest = params
            if event_id in self._conn.inbound_events:
                self._rows = []
                return
            self._conn.inbound_events.add(event_id)
            self._rows = [("inb-id",)]
            return

        if normalized.startswith("insert into job_queue"):
            *_prefix, idem_key, _trace = params
            if idem_key in self._conn.jobs:
                self._rows = []
                return
            self._conn.jobs.add(idem_key)
            self._rows = [("job-id",)]
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        if not self._rows:
            return None
        return self._rows.pop(0)

    def close(self) -> None:
        return None


class _Conn:
    def __init__(self) -> None:
        self.state: Dict[str, Any] = {}
        self.inbound_events: set[str] = set()
        self.jobs: set[str] = set()
        self.commits = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        return None


def test_polling_fallback_creates_events_jobs_and_cursor() -> None:
    conn = _Conn()
    payload = {"instance": "ru"}

    def _fetch_orders(_db, _instance, _cursor):
        return [
            {"order_number": "SO-1", "updated_at": "2026-03-01T10:00:00+00:00", "total_minor": 1000},
            {"order_number": "SO-2", "updated_at": "2026-03-01T10:01:00+00:00", "total_minor": 2000},
        ]

    result = polling.run_shopware_order_polling_fallback(conn, payload, fetch_orders=_fetch_orders)
    assert result["created_events"] == 2
    assert result["enqueued_jobs"] == 2
    assert result["next_cursor"] == "2026-03-01T10:01:00+00:00"
    assert conn.commits == 1


def test_polling_fallback_dedups_existing_events_and_jobs() -> None:
    conn = _Conn()
    conn.state["shopware_poll_cursor:ru"] = {"cursor": "2026-03-01T09:00:00+00:00"}
    payload = {"instance": "ru"}

    def _fetch_orders(_db, _instance, _cursor):
        return [{"order_number": "SO-1", "updated_at": "2026-03-01T10:00:00+00:00", "total_minor": 1000}]

    first = polling.run_shopware_order_polling_fallback(conn, payload, fetch_orders=_fetch_orders)
    second = polling.run_shopware_order_polling_fallback(conn, payload, fetch_orders=_fetch_orders)
    assert first["created_events"] == 1
    assert first["enqueued_jobs"] == 1
    assert second["created_events"] == 0
    assert second["enqueued_jobs"] == 0

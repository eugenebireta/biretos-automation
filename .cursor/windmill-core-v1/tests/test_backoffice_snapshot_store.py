"""
Tests for ru_worker/backoffice_snapshot_store.py — Phase 6.7+6.8.
Pure unit tests: stub DB cursor, deterministic.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_path()

from ru_worker.backoffice_snapshot_store import snapshot_external_read


# ---------------------------------------------------------------------------
# Stub DB
# ---------------------------------------------------------------------------

class _SnapCursor:
    def __init__(self, conn: "_SnapConn") -> None:
        self._conn = conn
        self._rows: list = []

    def execute(self, query: str, params=None) -> None:
        params = params or ()
        q = " ".join(query.strip().lower().split())
        if "insert into external_read_snapshots" in q:
            key = str(params[1])  # snapshot_key
            trace = str(params[0])
            composite = (trace, key)
            if composite in self._conn.snapshots:
                self._rows = []
                return
            snap_id = f"snap-{len(self._conn.snapshots) + 1}"
            self._conn.snapshots[composite] = snap_id
            self._rows = [(snap_id,)]
        else:
            raise AssertionError(f"Unexpected query: {query[:60]}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self):
        pass


class _SnapConn:
    def __init__(self) -> None:
        self.snapshots: dict = {}

    def cursor(self):
        return _SnapCursor(self)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_snapshot_created():
    conn = _SnapConn()
    result = snapshot_external_read(
        conn,
        trace_id="aaaaaaaa-0000-0000-0000-000000000000",
        provider="tbank",
        entity_type="invoice",
        entity_id="INV-001",
        snapshot_data={"status": "paid"},
    )
    assert result["action"] == "created"
    assert result["snapshot_key"] == "tbank:invoice:INV-001"


def test_snapshot_idempotent_duplicate():
    conn = _SnapConn()
    r1 = snapshot_external_read(
        conn,
        trace_id="bbbbbbbb-0000-0000-0000-000000000000",
        provider="cdek",
        entity_type="tracking",
        entity_id="CDEK-UUID-001",
        snapshot_data={"status": "delivered"},
    )
    r2 = snapshot_external_read(
        conn,
        trace_id="bbbbbbbb-0000-0000-0000-000000000000",
        provider="cdek",
        entity_type="tracking",
        entity_id="CDEK-UUID-001",
        snapshot_data={"status": "delivered"},
    )
    assert r1["action"] == "created"
    assert r2["action"] == "duplicate"


def test_different_traces_create_separate_snapshots():
    conn = _SnapConn()
    r1 = snapshot_external_read(
        conn,
        trace_id="trace-aaa",
        provider="cdek",
        entity_type="waybill",
        entity_id="UUID-001",
        snapshot_data={"pdf_size": 12345},
    )
    r2 = snapshot_external_read(
        conn,
        trace_id="trace-bbb",
        provider="cdek",
        entity_type="waybill",
        entity_id="UUID-001",
        snapshot_data={"pdf_size": 12345},
    )
    assert r1["action"] == "created"
    assert r2["action"] == "created"
    assert len(conn.snapshots) == 2


def test_snapshot_key_format():
    conn = _SnapConn()
    result = snapshot_external_read(
        conn,
        trace_id="cccccccc-0000-0000-0000-000000000000",
        provider="edo",
        entity_type="invoice",
        entity_id="EDO-DOC-999",
        snapshot_data={},
    )
    assert result["snapshot_key"] == "edo:invoice:EDO-DOC-999"

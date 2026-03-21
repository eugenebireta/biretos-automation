from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from uuid import UUID


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_path() -> None:
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


# ---------------------------------------------------------------------------
# Stub adapter
# ---------------------------------------------------------------------------

class _StubCDEKAdapter:
    """Minimal CDEK adapter stub for sync_shipment_status."""

    def __init__(self, *, carrier_status: str) -> None:
        self._carrier_status = carrier_status

    def get_tracking_status(self, req):
        class _Result:
            pass

        r = _Result()
        r.carrier_status = self._carrier_status
        return r


# ---------------------------------------------------------------------------
# Stub DB — handles all SQL from sync_shipment_status + update_shipment_status_atomic
#           + recompute_order_cdek_cache_atomic + verify_shipment_carrier_sync
# ---------------------------------------------------------------------------

class _Rc7Cursor:
    def __init__(self, conn: "_Rc7Conn") -> None:
        self._conn = conn
        self._rows: list = []
        self.rowcount = 0

    def execute(self, query: str, params=None) -> None:  # noqa: C901
        params = params or ()
        n = " ".join(query.strip().lower().split())

        # sync_shipment_status — SELECT id, order_id, current_status, carrier_external_id
        if n.startswith(
            "select id, order_id, current_status, carrier_external_id from shipments"
        ):
            sid = str(params[0])
            s = self._conn.shipments.get(sid)
            if s:
                self._rows = [(sid, s["order_id"], s["current_status"], s["carrier_external_id"])]
            else:
                self._rows = []
            return

        # update_shipment_status_atomic — SELECT id, order_id, carrier_code, current_status, packages, status_history
        if n.startswith(
            "select id, order_id, carrier_code, current_status, packages, status_history from shipments"
        ):
            sid = str(params[0])
            s = self._conn.shipments.get(sid)
            if s:
                self._rows = [(
                    sid,
                    s["order_id"],
                    s["carrier_code"],
                    s["current_status"],
                    json.dumps(s["packages"]),
                    json.dumps(s["status_history"]),
                )]
            else:
                self._rows = []
            return

        # update_shipment_status_atomic — UPDATE shipments SET current_status
        if n.startswith("update shipments set current_status"):
            new_status = params[0]
            sid = str(params[3])
            if sid in self._conn.shipments:
                self._conn.shipments[sid]["current_status"] = new_status
            self.rowcount = 1
            self._rows = []
            return

        # recompute_order_cdek_cache_atomic — SELECT carrier_external_id FROM shipments by order_id
        if (
            "select carrier_external_id from shipments" in n
            and "order by shipment_seq desc" in n
        ):
            order_id = str(params[0])
            candidates = [
                s for s in self._conn.shipments.values()
                if s["order_id"] == order_id
                and s["carrier_code"] == "cdek"
                and s["current_status"] != "cancelled"
                and s["carrier_external_id"] is not None
            ]
            candidates.sort(key=lambda s: s["shipment_seq"], reverse=True)
            self._rows = [(candidates[0]["carrier_external_id"],)] if candidates else [(None,)]
            return

        # recompute_order_cdek_cache_atomic — UPDATE order_ledger SET cdek_uuid
        if n.startswith("update order_ledger set cdek_uuid"):
            cdek_uuid = params[0]
            order_id = str(params[1])
            if order_id in self._conn.order_ledger:
                self._conn.order_ledger[order_id]["cdek_uuid"] = cdek_uuid
            self.rowcount = 1
            self._rows = []
            return

        # verify_shipment_carrier_sync — SELECT id, order_id, current_status FROM shipments
        if n.startswith("select id, order_id, current_status from shipments"):
            sid = str(params[0])
            s = self._conn.shipments.get(sid)
            if s:
                self._rows = [(sid, s["order_id"], s["current_status"])]
            else:
                self._rows = []
            return

        raise AssertionError(f"Unexpected SQL in _Rc7Cursor: {n!r}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self) -> None:
        pass


class _Rc7Conn:
    def __init__(self, *, initial_status: str) -> None:
        self.autocommit = False
        self.order_id = "11111111-1111-1111-1111-111111111111"
        self.shipment_id = "22222222-2222-2222-2222-222222222222"

        self.shipments = {
            self.shipment_id: {
                "order_id": self.order_id,
                "carrier_code": "cdek",
                "current_status": initial_status,
                "carrier_external_id": "CDEK-RC7-001",
                "packages": [],
                "status_history": [],
                "shipment_seq": 1,
            }
        }
        self.order_ledger = {self.order_id: {"cdek_uuid": None}}

    def cursor(self) -> _Rc7Cursor:
        return _Rc7Cursor(self)

    def commit(self) -> None:
        pass


# ---------------------------------------------------------------------------
# sync_shipment_status tests
# ---------------------------------------------------------------------------

def test_rc7_syncs_status_handed_over_to_in_transit() -> None:
    """handed_over → in_transit is a valid FSM transition."""
    _ensure_path()
    recon = importlib.import_module("domain.reconciliation_service")
    conn = _Rc7Conn(initial_status="handed_over")
    adapter = _StubCDEKAdapter(carrier_status="in_transit")

    result = recon.sync_shipment_status(
        conn,
        shipment_id=UUID(conn.shipment_id),
        adapter=adapter,
        trace_id="tr-rc7-a",
        event_id="rc7:test-event-001",
        occurred_at="2026-03-20T12:00:00+00:00",
    )

    assert result["action"] == "updated"
    assert result["from_status"] == "handed_over"
    assert result["to_status"] == "in_transit"
    assert conn.shipments[conn.shipment_id]["current_status"] == "in_transit"
    assert conn.order_ledger[conn.order_id]["cdek_uuid"] == "CDEK-RC7-001"


def test_rc7_noop_when_status_already_matches() -> None:
    """If carrier status matches current status, no DB write occurs."""
    _ensure_path()
    recon = importlib.import_module("domain.reconciliation_service")
    conn = _Rc7Conn(initial_status="in_transit")
    adapter = _StubCDEKAdapter(carrier_status="in_transit")

    result = recon.sync_shipment_status(
        conn,
        shipment_id=UUID(conn.shipment_id),
        adapter=adapter,
        trace_id="tr-rc7-noop",
    )

    assert result["action"] == "noop"
    assert result["status"] == "in_transit"
    # No mutation
    assert conn.shipments[conn.shipment_id]["current_status"] == "in_transit"


# ---------------------------------------------------------------------------
# verify_shipment_carrier_sync tests (from reconciliation_verify_ext)
# ---------------------------------------------------------------------------

def test_rc7_verify_match_after_sync() -> None:
    _ensure_path()
    verify_ext = importlib.import_module("domain.reconciliation_verify_ext")
    conn = _Rc7Conn(initial_status="in_transit")

    result = verify_ext.verify_shipment_carrier_sync(
        conn,
        shipment_id=UUID(conn.shipment_id),
        expected_status="in_transit",
        trace_id="tr-v-rc7",
    )

    assert result["verdict"] == "MATCH"
    assert result["actual"]["current_status"] == "in_transit"


def test_rc7_verify_divergence_when_status_stale() -> None:
    _ensure_path()
    verify_ext = importlib.import_module("domain.reconciliation_verify_ext")
    conn = _Rc7Conn(initial_status="handed_over")

    result = verify_ext.verify_shipment_carrier_sync(
        conn,
        shipment_id=UUID(conn.shipment_id),
        expected_status="in_transit",
        trace_id="tr-v-rc7-div",
    )

    assert result["verdict"] == "DIVERGENCE"
    assert result["expected"]["current_status"] == "in_transit"
    assert result["actual"]["current_status"] == "handed_over"

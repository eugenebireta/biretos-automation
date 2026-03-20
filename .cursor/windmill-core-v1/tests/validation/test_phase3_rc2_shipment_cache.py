from __future__ import annotations

import importlib
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
# Shared stub infrastructure
# ---------------------------------------------------------------------------

class _Rc2Cursor:
    def __init__(self, conn: "_Rc2Conn") -> None:
        self._conn = conn
        self._rows: list = []
        self.rowcount = 0

    def execute(self, query: str, params=None) -> None:
        params = params or ()
        n = " ".join(query.strip().lower().split())

        # recompute_order_cdek_cache_atomic — SELECT latest CDEK uuid
        if (
            "select carrier_external_id from shipments" in n
            and "order by shipment_seq desc" in n
        ):
            order_id = str(params[0])
            candidates = [
                s for s in self._conn.shipments
                if s["order_id"] == order_id
                and s["carrier_code"] == "cdek"
                and s["current_status"] != "cancelled"
                and s["carrier_external_id"] is not None
            ]
            candidates.sort(key=lambda s: s["shipment_seq"], reverse=True)
            self._rows = [(candidates[0]["carrier_external_id"],)] if candidates else [(None,)]
            return

        # recompute_order_cdek_cache_atomic — UPDATE order_ledger cdek_uuid
        if n.startswith("update order_ledger set cdek_uuid"):
            cdek_uuid = params[0]
            order_id = str(params[1])
            if order_id in self._conn.order_ledger:
                self._conn.order_ledger[order_id]["cdek_uuid"] = cdek_uuid
            self.rowcount = 1
            self._rows = []
            return

        # verify_shipment_cache — SELECT cdek_uuid from order_ledger
        if n.startswith("select cdek_uuid from order_ledger"):
            order_id = str(params[0])
            row = self._conn.order_ledger.get(order_id)
            self._rows = [(row["cdek_uuid"],)] if row else []
            return

        raise AssertionError(f"Unexpected SQL in _Rc2Cursor: {n!r}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self) -> None:
        pass


class _Rc2Conn:
    def __init__(self, *, ledger_cdek_uuid, shipment_cdek_uuid) -> None:
        self.autocommit = False
        self.order_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        self.order_ledger = {self.order_id: {"cdek_uuid": ledger_cdek_uuid}}
        self.shipments = [
            {
                "order_id": self.order_id,
                "carrier_code": "cdek",
                "current_status": "in_transit",
                "carrier_external_id": shipment_cdek_uuid,
                "shipment_seq": 1,
            }
        ]

    def cursor(self) -> _Rc2Cursor:
        return _Rc2Cursor(self)

    def commit(self) -> None:
        pass


# ---------------------------------------------------------------------------
# reconcile_shipment_cache tests
# ---------------------------------------------------------------------------

def test_rc2_reconcile_updates_cdek_uuid_when_stale() -> None:
    _ensure_path()
    recon = importlib.import_module("domain.reconciliation_service")
    conn = _Rc2Conn(ledger_cdek_uuid=None, shipment_cdek_uuid="CDEK-111")
    order_id = UUID(conn.order_id)

    result = recon.reconcile_shipment_cache(conn, order_id=order_id, trace_id="tr-rc2-a")

    assert result["action"] == "updated"
    assert result["cdek_uuid"] == "CDEK-111"
    assert conn.order_ledger[conn.order_id]["cdek_uuid"] == "CDEK-111"


def test_rc2_reconcile_is_idempotent_when_already_synced() -> None:
    _ensure_path()
    recon = importlib.import_module("domain.reconciliation_service")
    conn = _Rc2Conn(ledger_cdek_uuid="CDEK-222", shipment_cdek_uuid="CDEK-222")
    order_id = UUID(conn.order_id)

    result1 = recon.reconcile_shipment_cache(conn, order_id=order_id, trace_id="tr-rc2-idem")
    result2 = recon.reconcile_shipment_cache(conn, order_id=order_id, trace_id="tr-rc2-idem")

    assert result1["cdek_uuid"] == "CDEK-222"
    assert result2["cdek_uuid"] == "CDEK-222"
    assert conn.order_ledger[conn.order_id]["cdek_uuid"] == "CDEK-222"


# ---------------------------------------------------------------------------
# verify_shipment_cache tests
# ---------------------------------------------------------------------------

def test_rc2_verify_match() -> None:
    _ensure_path()
    verify = importlib.import_module("domain.reconciliation_verify")
    conn = _Rc2Conn(ledger_cdek_uuid="CDEK-999", shipment_cdek_uuid="CDEK-999")

    result = verify.verify_shipment_cache(conn, order_id=UUID(conn.order_id), trace_id="tr-v-rc2")

    assert result["verdict"] == "MATCH"


def test_rc2_verify_divergence_detected() -> None:
    _ensure_path()
    verify = importlib.import_module("domain.reconciliation_verify")
    conn = _Rc2Conn(ledger_cdek_uuid="CDEK-OLD", shipment_cdek_uuid="CDEK-NEW")

    result = verify.verify_shipment_cache(conn, order_id=UUID(conn.order_id), trace_id="tr-v-rc2-div")

    assert result["verdict"] == "DIVERGENCE"
    assert result["expected"]["cdek_uuid"] == "CDEK-NEW"
    assert result["actual"]["cdek_uuid"] == "CDEK-OLD"

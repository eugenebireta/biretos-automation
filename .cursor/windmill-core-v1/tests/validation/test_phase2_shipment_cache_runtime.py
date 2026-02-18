from __future__ import annotations

import importlib
import sys
from pathlib import Path
from uuid import UUID


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _import_shipment_service():
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module("domain.shipment_service")


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows = []
        self.rowcount = 0

    def execute(self, query: str, params=None):
        params = params or ()
        normalized = " ".join(query.strip().lower().split())
        if normalized.startswith("select carrier_external_id from shipments"):
            order_id = str(params[0])
            rows = [
                row for row in self._conn.shipments
                if row["order_id"] == order_id
                and row["carrier_code"] == "cdek"
                and row["current_status"] != "cancelled"
                and row["carrier_external_id"] is not None
            ]
            rows.sort(key=lambda r: r["shipment_seq"], reverse=True)
            self._rows = [(rows[0]["carrier_external_id"],)] if rows else []
            return

        if normalized.startswith("update order_ledger set cdek_uuid = %s"):
            cdek_uuid, order_id = params
            self._conn.order_ledger[str(order_id)]["cdek_uuid"] = cdek_uuid
            self.rowcount = 1
            self._rows = []
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self):
        return None


class _Conn:
    def __init__(self) -> None:
        self.autocommit = False
        self.order_ledger = {
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": {"cdek_uuid": None}
        }
        self.shipments = [
            {
                "order_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "carrier_code": "cdek",
                "carrier_external_id": "cdek-old",
                "current_status": "cancelled",
                "shipment_seq": 1,
            },
            {
                "order_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "carrier_code": "cdek",
                "carrier_external_id": "cdek-active-2",
                "current_status": "created",
                "shipment_seq": 2,
            },
            {
                "order_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "carrier_code": "cdek",
                "carrier_external_id": "cdek-active-3",
                "current_status": "label_ready",
                "shipment_seq": 3,
            },
        ]

    def cursor(self):
        return _Cursor(self)


def test_recompute_order_cdek_cache_uses_latest_non_cancelled():
    svc = _import_shipment_service()
    conn = _Conn()
    order_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    latest = svc.recompute_order_cdek_cache_atomic(conn, order_id=order_id)
    assert latest == "cdek-active-3"
    assert conn.order_ledger[str(order_id)]["cdek_uuid"] == "cdek-active-3"


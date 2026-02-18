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

        if normalized.startswith("select id, order_id, carrier_code, current_status, packages, status_history from shipments"):
            shipment_id = str(params[0])
            row = self._conn.shipments.get(shipment_id)
            self._rows = [(
                shipment_id,
                row["order_id"],
                row["carrier_code"],
                row["current_status"],
                row["packages"],
                row["status_history"],
            )]
            return

        if normalized.startswith("select line_status from order_line_items"):
            line_item_id, order_id = str(params[0]), str(params[1])
            status = self._conn.line_status[(order_id, line_item_id)]
            self._rows = [(status,)]
            return

        if normalized.startswith("select coalesce(sum(quantity), 0) from reservations"):
            order_id, line_item_id = str(params[0]), str(params[1])
            qty = self._conn.active_reservations.get((order_id, line_item_id), 0)
            self._rows = [(qty,)]
            return

        if normalized.startswith("update order_line_items set line_status = %s"):
            next_status, line_item_id, order_id = params
            self._conn.line_status[(str(order_id), str(line_item_id))] = str(next_status)
            self.rowcount = 1
            return

        if normalized.startswith("update shipments set current_status = %s"):
            to_status, _, _, shipment_id = params
            self._conn.shipments[str(shipment_id)]["current_status"] = to_status
            self.rowcount = 1
            return

        if normalized.startswith("select carrier_external_id from shipments"):
            order_id = str(params[0])
            rows = []
            for row in self._conn.shipments.values():
                if row["order_id"] != order_id:
                    continue
                if row["carrier_code"] != "cdek":
                    continue
                if row["current_status"] == "cancelled":
                    continue
                rows.append(row)
            rows.sort(key=lambda r: r["shipment_seq"], reverse=True)
            self._rows = [(rows[0]["carrier_external_id"],)] if rows else []
            return

        if normalized.startswith("update order_ledger set cdek_uuid = %s"):
            cdek_uuid, order_id = params
            self._conn.order_cache[str(order_id)] = cdek_uuid
            self.rowcount = 1
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self):
        return None


class _Conn:
    def __init__(self) -> None:
        self.autocommit = False
        self.shipments = {
            "99999999-9999-9999-9999-999999999999": {
                "order_id": "88888888-8888-8888-8888-888888888888",
                "carrier_code": "cdek",
                "carrier_external_id": "cdek-to-cancel",
                "current_status": "created",
                "shipment_seq": 2,
                "packages": [
                    {"items": [{"line_item_id": "77777777-7777-7777-7777-777777777777", "quantity": 1}]}
                ],
                "status_history": [],
            }
        }
        self.line_status = {
            ("88888888-8888-8888-8888-888888888888", "77777777-7777-7777-7777-777777777777"): "allocated"
        }
        self.active_reservations = {
            ("88888888-8888-8888-8888-888888888888", "77777777-7777-7777-7777-777777777777"): 1
        }
        self.order_cache = {"88888888-8888-8888-8888-888888888888": "cdek-to-cancel"}

    def cursor(self):
        return _Cursor(self)


def test_cancel_shipment_triggers_unpack_allocated_to_reserved():
    svc = _import_shipment_service()
    conn = _Conn()
    result = svc.update_shipment_status_atomic(
        conn,
        shipment_id=UUID("99999999-9999-9999-9999-999999999999"),
        to_status="cancelled",
        event_id="event-1",
        occurred_at="2026-02-14T00:00:00Z",
        reason="SHIPMENT_VOIDED",
        trace_id=None,
        context={},
    )
    assert result["action"] == "updated"
    assert conn.shipments["99999999-9999-9999-9999-999999999999"]["current_status"] == "cancelled"
    assert (
        conn.line_status[("88888888-8888-8888-8888-888888888888", "77777777-7777-7777-7777-777777777777")]
        == "reserved"
    )
    assert conn.order_cache["88888888-8888-8888-8888-888888888888"] is None


from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _import_reconciliation():
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module("domain.reconciliation_service")


class _PaymentCursor:
    def __init__(self, conn: "_PaymentConn") -> None:
        self._conn = conn
        self._rows = []
        self.rowcount = 0

    def execute(self, query: str, params=None):
        params = params or ()
        normalized = " ".join(query.strip().lower().split())

        if normalized.startswith("select order_id, payment_status, metadata, order_total_minor from order_ledger"):
            order_id = str(params[0])
            row = self._conn.order_ledger.get(order_id)
            self._rows = [(order_id, row["payment_status"], row["metadata"], row.get("order_total_minor"))] if row else []
            return

        if normalized.startswith("select coalesce(sum(amount_minor), 0) from payment_transactions"):
            order_id = str(params[0])
            if "transaction_type = 'charge'" in normalized:
                total = sum(
                    tx["amount_minor"]
                    for tx in self._conn.payment_transactions
                    if tx["order_id"] == order_id and tx["status"] == "confirmed" and tx["transaction_type"] == "charge"
                )
            else:
                total = sum(
                    tx["amount_minor"]
                    for tx in self._conn.payment_transactions
                    if tx["order_id"] == order_id
                    and tx["status"] == "confirmed"
                    and tx["transaction_type"] in {"refund", "chargeback"}
                )
            self._rows = [(total,)]
            return

        if normalized.startswith("select exists ( select 1 from payment_transactions"):
            self._rows = [(False,)]
            return

        if normalized.startswith("update order_ledger set payment_status = %s"):
            payment_status = params[0]
            order_id = str(params[2])
            self._conn.order_ledger[order_id]["payment_status"] = payment_status
            self.rowcount = 1
            self._rows = []
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self):
        return None


class _PaymentConn:
    def __init__(self):
        self.autocommit = False
        self.order_ledger = {
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": {
                "payment_status": "unpaid",
                "metadata": {"totalAmount": 100.0},
            }
        }
        self.payment_transactions = [
            {
                "order_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "status": "confirmed",
                "transaction_type": "charge",
                "amount_minor": 10000,
            }
        ]
        self.commit_calls = 0

    def cursor(self):
        return _PaymentCursor(self)

    def commit(self):
        self.commit_calls += 1


class _Rc4Cursor:
    def __init__(self, conn: "_Rc4Conn") -> None:
        self._conn = conn
        self._rows = []
        self.rowcount = 0

    def execute(self, query: str, params=None):
        params = params or ()
        normalized = " ".join(query.strip().lower().split())

        if normalized.startswith("select id from reservations where status = 'active'"):
            now_ts = params[0]
            limit = int(params[1])
            ids = [
                rid
                for rid, reservation in self._conn.reservations.items()
                if reservation["status"] == "active"
                and reservation["expires_at"] is not None
                and reservation["expires_at"] < now_ts
            ][:limit]
            self._rows = [(rid,) for rid in ids]
            return

        if normalized.startswith("select id, order_id, line_item_id, product_id"):
            reservation_id = str(params[0])
            reservation = self._conn.reservations.get(reservation_id)
            if not reservation:
                self._rows = []
                return
            self._rows = [
                (
                    reservation_id,
                    reservation["order_id"],
                    reservation["line_item_id"],
                    reservation["product_id"],
                    reservation["sku_snapshot"],
                    reservation["warehouse_code"],
                    reservation["quantity"],
                    reservation["status"],
                    reservation["expires_at"],
                )
            ]
            return

        if normalized.startswith("select line_status from order_line_items"):
            line_item_id = str(params[0])
            order_id = str(params[1])
            item = self._conn.line_items.get(line_item_id)
            if not item or item["order_id"] != order_id:
                self._rows = []
                return
            self._rows = [(item["line_status"],)]
            return

        if normalized.startswith("update reservations set status = 'expired'"):
            reservation_id = str(params[1])
            reservation = self._conn.reservations[reservation_id]
            reservation["status"] = "expired"
            reservation["released_at"] = self._conn.now
            self.rowcount = 1
            self._rows = []
            return

        if normalized.startswith("insert into stock_ledger_entries"):
            key = str(params[6])
            if key in self._conn.stock_ledger_keys:
                self._rows = []
                return
            self._conn.stock_ledger_keys.add(key)
            self._conn.stock_ledger_entries.append(
                {
                    "idempotency_key": key,
                    "reservation_id": str(params[4]),
                    "quantity_delta": int(params[3]),
                }
            )
            self._rows = [(f"ledger-{len(self._conn.stock_ledger_entries)}",)]
            return

        if normalized.startswith("insert into availability_snapshot"):
            product_id = str(params[0])
            warehouse = str(params[1])
            sku = str(params[2])
            self._conn.snapshots.setdefault(
                (product_id, warehouse),
                {"sku": sku, "quantity_on_hand": 0, "quantity_reserved": 0, "quantity_available": 0},
            )
            self._rows = []
            return

        if normalized.startswith("select quantity_on_hand, quantity_reserved, quantity_available from availability_snapshot"):
            product_id = str(params[0])
            warehouse = str(params[1])
            snap = self._conn.snapshots.get((product_id, warehouse))
            self._rows = [(snap["quantity_on_hand"], snap["quantity_reserved"], snap["quantity_available"])] if snap else []
            return

        if normalized.startswith("update availability_snapshot set quantity_reserved = %s"):
            quantity_reserved = int(params[0])
            quantity_available = int(params[1])
            product_id = str(params[2])
            warehouse = str(params[3])
            snap = self._conn.snapshots[(product_id, warehouse)]
            snap["quantity_reserved"] = quantity_reserved
            snap["quantity_available"] = quantity_available
            self._rows = []
            return

        if normalized.startswith("select count(*) from reservations where order_id = %s"):
            order_id = str(params[0])
            line_item_id = str(params[1])
            count = sum(
                1
                for reservation in self._conn.reservations.values()
                if reservation["order_id"] == order_id
                and reservation["line_item_id"] == line_item_id
                and reservation["status"] == "active"
            )
            self._rows = [(count,)]
            return

        if normalized.startswith("update order_line_items set line_status = 'pending'"):
            line_item_id = str(params[0])
            order_id = str(params[1])
            item = self._conn.line_items[line_item_id]
            if item["order_id"] == order_id:
                item["line_status"] = "pending"
            self._rows = []
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows = self._rows
        self._rows = []
        return rows

    def close(self):
        return None


class _Rc4Conn:
    def __init__(self, *, line_status: str):
        self.autocommit = False
        self.commit_calls = 0
        self.rollback_calls = 0
        self.now = datetime.now(timezone.utc)

        self.order_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        self.line_item_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        self.product_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"
        self.reservation_id = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"

        self.reservations = {
            self.reservation_id: {
                "order_id": self.order_id,
                "line_item_id": self.line_item_id,
                "product_id": self.product_id,
                "sku_snapshot": "SKU-1",
                "warehouse_code": "WH-1",
                "quantity": 2,
                "status": "active",
                "expires_at": self.now - timedelta(minutes=30),
                "released_at": None,
            }
        }
        self.line_items = {
            self.line_item_id: {
                "order_id": self.order_id,
                "line_status": line_status,
            }
        }
        self.snapshots = {
            (self.product_id, "WH-1"): {
                "sku": "SKU-1",
                "quantity_on_hand": 10,
                "quantity_reserved": 2,
                "quantity_available": 8,
            }
        }
        self.stock_ledger_keys = set()
        self.stock_ledger_entries = []

    def cursor(self):
        return _Rc4Cursor(self)

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1


def test_rc1_reconcile_payment_cache_is_idempotent():
    svc = _import_reconciliation()
    conn = _PaymentConn()
    order_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    first = svc.reconcile_payment_cache(conn, order_id=order_id, trace_id="tr-1")
    second = svc.reconcile_payment_cache(conn, order_id=order_id, trace_id="tr-1")

    assert first["payment_status"] == "paid"
    assert second["payment_status"] == "paid"
    assert first["action"] == "updated"
    assert second["action"] == "noop"
    assert conn.order_ledger[str(order_id)]["payment_status"] == "paid"


def test_rc4_allocated_line_guard_prevents_release():
    svc = _import_reconciliation()
    conn = _Rc4Conn(line_status="allocated")

    result = svc.expire_reservations(
        conn,
        trace_id="tr-guard",
        batch_limit=10,
        now=conn.now,
    )

    assert result["released"] == 0
    assert result["skipped"] == 1
    assert conn.reservations[conn.reservation_id]["status"] == "active"
    assert conn.stock_ledger_entries == []
    assert conn.stock_ledger_keys == set()


def test_rc4_prevents_double_release_via_idempotency_key():
    svc = _import_reconciliation()
    conn = _Rc4Conn(line_status="reserved")

    first = svc.expire_reservations(
        conn,
        trace_id="tr-rc4",
        batch_limit=10,
        now=conn.now,
    )
    second = svc.expire_reservations(
        conn,
        trace_id="tr-rc4",
        batch_limit=10,
        now=conn.now,
    )

    expected_key = f"reservation_expiry:{conn.reservation_id}"
    assert expected_key in conn.stock_ledger_keys
    assert len(conn.stock_ledger_entries) == 1
    assert first["released"] == 1
    assert second["released"] == 0
    assert conn.reservations[conn.reservation_id]["status"] == "expired"


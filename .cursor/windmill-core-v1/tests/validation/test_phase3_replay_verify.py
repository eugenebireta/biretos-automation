from __future__ import annotations

import importlib
import sys
from pathlib import Path
from uuid import UUID


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _import_verify():
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module("domain.reconciliation_verify")


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows = []

    def execute(self, query: str, params=None):
        params = params or ()
        normalized = " ".join(query.strip().lower().split())

        forbidden = ("insert into", "update ", "delete from")
        if any(tok in normalized for tok in forbidden):
            raise AssertionError(f"Forbidden SQL in verify-only module: {normalized}")

        if normalized.startswith("select order_id, payment_status, metadata, order_total_minor from order_ledger"):
            order_id = str(params[0])
            row = self._conn.order_ledger.get(order_id)
            self._rows = [(order_id, row["payment_status"], row["metadata"], row.get("order_total_minor"))] if row else []
            return

        if normalized.startswith("select cdek_uuid from order_ledger"):
            order_id = str(params[0])
            row = self._conn.order_ledger.get(order_id)
            self._rows = [(row.get("cdek_uuid"),)] if row else []
            return

        if normalized.startswith("select invoice_request_key, revision from order_ledger"):
            order_id = str(params[0])
            row = self._conn.order_ledger.get(order_id)
            if not row:
                self._rows = []
                return
            self._rows = [(row.get("invoice_request_key"), row.get("revision"))]
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
            self._rows = [(int(total),)]
            return

        if normalized.startswith("select exists ( select 1 from payment_transactions"):
            order_id = str(params[0])
            exists = any(
                tx["order_id"] == order_id and tx["status"] == "pending" and tx["transaction_type"] == "refund"
                for tx in self._conn.payment_transactions
            )
            self._rows = [(bool(exists),)]
            return

        if normalized.startswith("select carrier_external_id from shipments"):
            order_id = str(params[0])
            candidates = [
                s
                for s in self._conn.shipments
                if s["order_id"] == order_id
                and s["carrier_code"] == "cdek"
                and s["current_status"] != "cancelled"
                and s["carrier_external_id"] is not None
            ]
            candidates.sort(key=lambda s: int(s.get("shipment_seq", 0)), reverse=True)
            self._rows = [(candidates[0]["carrier_external_id"],)] if candidates else []
            return

        if normalized.startswith("select id, generation_key, revision from documents"):
            order_id = str(params[0])
            docs = [
                d
                for d in self._conn.documents
                if d["order_id"] == order_id and d["document_type"] == "invoice" and d["status"] == "issued"
            ]
            docs.sort(key=lambda d: int(d.get("revision", 0)), reverse=True)
            if not docs:
                self._rows = []
                return
            top = docs[0]
            self._rows = [(top["id"], top["generation_key"], top["revision"])]
            return

        if normalized.startswith(
            "select quantity_on_hand, quantity_reserved, quantity_available from availability_snapshot"
        ):
            product_id = str(params[0])
            warehouse_code = str(params[1])
            snap = self._conn.availability_snapshot.get((product_id, warehouse_code))
            self._rows = [(snap["quantity_on_hand"], snap["quantity_reserved"], snap["quantity_available"])] if snap else []
            return

        if normalized.startswith("select coalesce(sum(quantity_delta), 0) from stock_ledger_entries"):
            product_id = str(params[0])
            warehouse_code = str(params[1])
            total = sum(
                int(e["quantity_delta"])
                for e in self._conn.stock_ledger_entries
                if e["product_id"] == product_id
                and e["warehouse_code"] == warehouse_code
                and e["change_type"] in {"receipt", "return", "adjustment", "sale"}
            )
            self._rows = [(int(total),)]
            return

        if normalized.startswith("select coalesce(sum(quantity), 0) from reservations"):
            product_id = str(params[0])
            warehouse_code = str(params[1])
            total = sum(
                int(r["quantity"])
                for r in self._conn.reservations
                if r["product_id"] == product_id
                and r["warehouse_code"] == warehouse_code
                and r["status"] == "active"
            )
            self._rows = [(int(total),)]
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self):
        return None


class _Conn:
    def __init__(self):
        self.order_ledger = {}
        self.payment_transactions = []
        self.shipments = []
        self.documents = []
        self.availability_snapshot = {}
        self.stock_ledger_entries = []
        self.reservations = []

    def cursor(self):
        return _Cursor(self)


def test_verify_module_is_read_only_by_static_scan():
    source = (_project_root() / "domain" / "reconciliation_verify.py").read_text(encoding="utf-8")
    upper = source.upper()
    assert "INSERT INTO" not in upper
    assert "UPDATE " not in upper
    assert "DELETE FROM" not in upper


def test_verify_payment_cache_match_and_divergence():
    verify = _import_verify()
    conn = _Conn()
    order_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    conn.order_ledger[str(order_id)] = {"payment_status": "paid", "metadata": {"totalAmount": 100.0}, "order_total_minor": None}
    conn.payment_transactions.append(
        {"order_id": str(order_id), "status": "confirmed", "transaction_type": "charge", "amount_minor": 10000}
    )

    ok = verify.verify_payment_cache(conn, order_id=order_id, trace_id="t1")
    assert ok["verdict"] == "MATCH"

    conn.order_ledger[str(order_id)]["payment_status"] = "unpaid"
    bad = verify.verify_payment_cache(conn, order_id=order_id, trace_id="t2")
    assert bad["verdict"] == "DIVERGENCE"
    assert bad["expected"]["payment_status"] == "paid"
    assert bad["actual"]["payment_status"] == "unpaid"


def test_verify_shipment_cache_match_and_divergence():
    verify = _import_verify()
    conn = _Conn()
    order_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    conn.order_ledger[str(order_id)] = {"cdek_uuid": "cdek-1"}
    conn.shipments.append(
        {
            "order_id": str(order_id),
            "carrier_code": "cdek",
            "current_status": "in_transit",
            "carrier_external_id": "cdek-1",
            "shipment_seq": 1,
        }
    )

    ok = verify.verify_shipment_cache(conn, order_id=order_id, trace_id="t1")
    assert ok["verdict"] == "MATCH"

    conn.order_ledger[str(order_id)]["cdek_uuid"] = "cdek-2"
    bad = verify.verify_shipment_cache(conn, order_id=order_id, trace_id="t2")
    assert bad["verdict"] == "DIVERGENCE"
    assert bad["expected"]["cdek_uuid"] == "cdek-1"
    assert bad["actual"]["cdek_uuid"] == "cdek-2"


def test_verify_document_key_match_and_divergence():
    verify = _import_verify()
    conn = _Conn()
    order_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    conn.order_ledger[str(order_id)] = {"invoice_request_key": "k1", "revision": 2}
    conn.documents.append(
        {
            "id": "doc-1",
            "order_id": str(order_id),
            "document_type": "invoice",
            "status": "issued",
            "generation_key": "k1",
            "revision": 2,
        }
    )

    ok = verify.verify_document_key(conn, order_id=order_id, trace_id="t1")
    assert ok["verdict"] == "MATCH"

    conn.order_ledger[str(order_id)]["invoice_request_key"] = "k2"
    bad = verify.verify_document_key(conn, order_id=order_id, trace_id="t2")
    assert bad["verdict"] == "DIVERGENCE"
    assert bad["expected"]["invoice_request_key"] == "k1"
    assert bad["actual"]["invoice_request_key"] == "k2"


def test_verify_stock_snapshot_match_and_divergence():
    verify = _import_verify()
    conn = _Conn()
    product_id = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    warehouse_code = "WH-1"

    # expected_on_hand = 10 (receipt)
    conn.stock_ledger_entries.append(
        {"product_id": str(product_id), "warehouse_code": warehouse_code, "change_type": "receipt", "quantity_delta": 10}
    )
    # expected_reserved = 3 (active reservations)
    conn.reservations.append({"product_id": str(product_id), "warehouse_code": warehouse_code, "status": "active", "quantity": 3})

    conn.availability_snapshot[(str(product_id), warehouse_code)] = {
        "quantity_on_hand": 10,
        "quantity_reserved": 3,
        "quantity_available": 7,
    }

    ok = verify.verify_stock_snapshot(conn, product_id=product_id, warehouse_code=warehouse_code, trace_id="t1")
    assert ok["verdict"] == "MATCH"

    conn.availability_snapshot[(str(product_id), warehouse_code)]["quantity_available"] = 6
    bad = verify.verify_stock_snapshot(conn, product_id=product_id, warehouse_code=warehouse_code, trace_id="t2")
    assert bad["verdict"] == "DIVERGENCE"
    assert bad["expected"]["quantity_available"] == 7
    assert bad["actual"]["quantity_available"] == 6


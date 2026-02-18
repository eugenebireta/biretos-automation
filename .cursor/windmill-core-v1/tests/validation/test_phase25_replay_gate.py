from __future__ import annotations

import importlib
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID


ORDER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PRODUCT_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
LINE_ITEM_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
RESERVATION_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
DOCUMENT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
WAREHOUSE_CODE = "WH-MAIN"
DOC_KEY = f"invoice:{ORDER_ID}:abc123"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _import_observability():
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module("domain.observability_service")


def _import_reconciliation():
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module("domain.reconciliation_service")


class _Cursor:
    def __init__(self, conn: "_ReplayConn") -> None:
        self._conn = conn
        self._rows = []
        self.rowcount = 0

    def execute(self, query: str, params=None):
        params = params or ()
        normalized = " ".join(query.strip().lower().split())

        # Guardrail: replay rebuild must not append into truth ledgers.
        if normalized.startswith("insert into payment_transactions"):
            raise AssertionError("Forbidden append-only INSERT during replay rebuild: payment_transactions")
        if normalized.startswith("insert into stock_ledger_entries"):
            raise AssertionError("Forbidden append-only INSERT during replay rebuild: stock_ledger_entries")

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
            order_id = str(params[0])
            exists = any(
                tx["order_id"] == order_id
                and tx["status"] == "pending"
                and tx["transaction_type"] == "refund"
                for tx in self._conn.payment_transactions
            )
            self._rows = [(exists,)]
            return

        if normalized.startswith("update order_ledger set payment_status = %s"):
            next_status = str(params[0])
            trace_id = params[1]
            order_id = str(params[2])
            row = self._conn.order_ledger[order_id]
            row["payment_status"] = next_status
            if row.get("trace_id") is None and trace_id is not None:
                row["trace_id"] = trace_id
            self.rowcount = 1
            self._rows = []
            return

        if normalized.startswith("select cdek_uuid from order_ledger"):
            order_id = str(params[0])
            row = self._conn.order_ledger.get(order_id)
            self._rows = [(row["cdek_uuid"],)] if row else []
            return

        if normalized.startswith("select carrier_external_id from shipments"):
            order_id = str(params[0])
            rows = [
                row
                for row in self._conn.shipments
                if row["order_id"] == order_id
                and row["carrier_code"] == "cdek"
                and row["current_status"] != "cancelled"
                and row["carrier_external_id"] is not None
            ]
            rows.sort(key=lambda item: item["shipment_seq"], reverse=True)
            self._rows = [(rows[0]["carrier_external_id"],)] if rows else []
            return

        if normalized.startswith("select count(*) from shipments"):
            order_id = str(params[0])
            rows = [
                row
                for row in self._conn.shipments
                if row["order_id"] == order_id and row["carrier_code"] == "cdek"
            ]
            if "current_status = 'cancelled'" in normalized:
                rows = [row for row in rows if row["current_status"] == "cancelled"]
            self._rows = [(len(rows),)]
            return

        if normalized.startswith("update order_ledger set cdek_uuid = %s"):
            cdek_uuid = params[0]
            order_id = str(params[1])
            self._conn.order_ledger[order_id]["cdek_uuid"] = cdek_uuid
            self.rowcount = 1
            self._rows = []
            return

        if normalized.startswith("select quantity_on_hand, quantity_reserved, quantity_available from availability_snapshot"):
            product_id = str(params[0])
            warehouse_code = str(params[1])
            row = self._conn.availability_snapshot.get((product_id, warehouse_code))
            self._rows = [(row["quantity_on_hand"], row["quantity_reserved"], row["quantity_available"])] if row else []
            return

        if normalized.startswith("select coalesce(sum(quantity_delta), 0) from stock_ledger_entries"):
            product_id = str(params[0])
            warehouse_code = str(params[1])
            allowed_types = {"receipt", "return", "adjustment", "sale"}
            total = sum(
                int(entry["quantity_delta"])
                for entry in self._conn.stock_ledger_entries
                if entry["product_id"] == product_id
                and entry["warehouse_code"] == warehouse_code
                and entry["change_type"] in allowed_types
            )
            self._rows = [(total,)]
            return

        if normalized.startswith("select coalesce(sum(quantity), 0) from reservations"):
            product_id = str(params[0])
            warehouse_code = str(params[1])
            total = sum(
                int(entry["quantity"])
                for entry in self._conn.reservations.values()
                if entry["product_id"] == product_id
                and entry["warehouse_code"] == warehouse_code
                and entry["status"] == "active"
            )
            self._rows = [(total,)]
            return

        if normalized.startswith("update availability_snapshot set quantity_on_hand = %s"):
            quantity_on_hand = int(params[0])
            quantity_reserved = int(params[1])
            quantity_available = int(params[2])
            product_id = str(params[3])
            warehouse_code = str(params[4])
            self._conn.availability_snapshot[(product_id, warehouse_code)] = {
                **self._conn.availability_snapshot[(product_id, warehouse_code)],
                "quantity_on_hand": quantity_on_hand,
                "quantity_reserved": quantity_reserved,
                "quantity_available": quantity_available,
            }
            self.rowcount = 1
            self._rows = []
            return

        if normalized.startswith("select invoice_request_key, revision from order_ledger"):
            order_id = str(params[0])
            row = self._conn.order_ledger.get(order_id)
            self._rows = [(row["invoice_request_key"], row["revision"])] if row else []
            return

        if normalized.startswith("select id, generation_key, revision from documents"):
            order_id = str(params[0])
            rows = [
                doc
                for doc in self._conn.documents
                if doc["order_id"] == order_id
                and doc["document_type"] == "invoice"
                and doc["status"] == "issued"
            ]
            rows.sort(key=lambda item: item["revision"], reverse=True)
            self._rows = [(rows[0]["id"], rows[0]["generation_key"], rows[0]["revision"])] if rows else []
            return

        if normalized.startswith("select generation_key, revision from documents"):
            order_id = str(params[0])
            rows = [
                doc
                for doc in self._conn.documents
                if doc["order_id"] == order_id
                and doc["document_type"] == "invoice"
                and doc["status"] == "issued"
            ]
            rows.sort(key=lambda item: item["revision"], reverse=True)
            self._rows = [(rows[0]["generation_key"], rows[0]["revision"])] if rows else []
            return

        if normalized.startswith("update order_ledger set invoice_request_key = %s"):
            invoice_request_key = str(params[0]) if params[0] is not None else None
            revision = int(params[1]) if params[1] is not None else None
            trace_id = params[2]
            order_id = str(params[3])
            row = self._conn.order_ledger[order_id]
            row["invoice_request_key"] = invoice_request_key
            row["revision"] = revision
            if row.get("trace_id") is None and trace_id is not None:
                row["trace_id"] = trace_id
            self.rowcount = 1
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


class _ReplayConn:
    def __init__(self) -> None:
        self.autocommit = False
        self.now = datetime.now(timezone.utc)
        self.commit_calls = 0
        self.rollback_calls = 0

        self.order_ledger = {
            ORDER_ID: {
                "payment_status": "unpaid",  # Deliberately wrong cache.
                "cdek_uuid": None,  # Deliberately wrong cache.
                "invoice_request_key": None,  # Deliberately wrong cache.
                "revision": 0,  # Deliberately wrong cache.
                "metadata": {"totalAmount": 100.0},
                "trace_id": None,
            }
        }
        self.payment_transactions = [
            {
                "id": "pt-1",
                "order_id": ORDER_ID,
                "status": "confirmed",
                "transaction_type": "charge",
                "amount_minor": 10000,
            }
        ]
        self.shipments = [
            {
                "id": "ship-1",
                "order_id": ORDER_ID,
                "carrier_code": "cdek",
                "carrier_external_id": "cdek-old",
                "current_status": "cancelled",
                "shipment_seq": 1,
            },
            {
                "id": "ship-2",
                "order_id": ORDER_ID,
                "carrier_code": "cdek",
                "carrier_external_id": "cdek-active",
                "current_status": "created",
                "shipment_seq": 2,
            },
        ]
        self.stock_ledger_entries = [
            {
                "id": "sle-1",
                "product_id": PRODUCT_ID,
                "warehouse_code": WAREHOUSE_CODE,
                "change_type": "receipt",
                "quantity_delta": 20,
            }
        ]
        self.reservations = {
            RESERVATION_ID: {
                "id": RESERVATION_ID,
                "order_id": ORDER_ID,
                "line_item_id": LINE_ITEM_ID,
                "product_id": PRODUCT_ID,
                "warehouse_code": WAREHOUSE_CODE,
                "quantity": 5,
                "status": "active",
                "expires_at": self.now + timedelta(hours=24),
            }
        }
        self.availability_snapshot = {
            (PRODUCT_ID, WAREHOUSE_CODE): {
                "sku": "SKU-1",
                "quantity_on_hand": 0,  # Deliberately wrong cache.
                "quantity_reserved": 0,  # Deliberately wrong cache.
                "quantity_available": 0,  # Deliberately wrong cache.
            }
        }
        self.documents = [
            {
                "id": DOCUMENT_ID,
                "order_id": ORDER_ID,
                "document_type": "invoice",
                "status": "issued",
                "revision": 1,
                "generation_key": DOC_KEY,
                "provider_document_id": "tbank-doc-1",
            }
        ]
        self.order_line_items = {
            LINE_ITEM_ID: {
                "id": LINE_ITEM_ID,
                "order_id": ORDER_ID,
                "quantity": 5,
                "line_status": "reserved",
            }
        }

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1


def _assert_ic_1253_fail(observability, conn: _ReplayConn) -> None:
    order_id = UUID(ORDER_ID)
    product_id = UUID(PRODUCT_ID)
    ic1 = observability.check_payment_cache_integrity(conn, order_id=order_id, trace_id="pre")
    ic2 = observability.check_shipment_cache_integrity(conn, order_id=order_id, trace_id="pre")
    ic3 = observability.check_stock_snapshot_integrity(
        conn,
        product_id=product_id,
        warehouse_code=WAREHOUSE_CODE,
        trace_id="pre",
    )
    ic5 = observability.check_document_generation_key_consistency(conn, order_id=order_id, trace_id="pre")
    assert ic1["verdict"] == "FAIL"
    assert ic2["verdict"] == "FAIL"
    assert ic3["verdict"] == "FAIL"
    assert ic5["verdict"] == "FAIL"


def _assert_ic_1253_pass(observability, conn: _ReplayConn) -> None:
    order_id = UUID(ORDER_ID)
    product_id = UUID(PRODUCT_ID)
    ic1 = observability.check_payment_cache_integrity(conn, order_id=order_id, trace_id="post")
    ic2 = observability.check_shipment_cache_integrity(conn, order_id=order_id, trace_id="post")
    ic3 = observability.check_stock_snapshot_integrity(
        conn,
        product_id=product_id,
        warehouse_code=WAREHOUSE_CODE,
        trace_id="post",
    )
    ic5 = observability.check_document_generation_key_consistency(conn, order_id=order_id, trace_id="post")
    assert ic1["verdict"] == "PASS"
    assert ic2["verdict"] == "PASS"
    assert ic3["verdict"] == "PASS"
    assert ic5["verdict"] == "PASS"


def _cache_signature(conn: _ReplayConn):
    order = conn.order_ledger[ORDER_ID]
    snap = conn.availability_snapshot[(PRODUCT_ID, WAREHOUSE_CODE)]
    return {
        "payment_status": order["payment_status"],
        "cdek_uuid": order["cdek_uuid"],
        "invoice_request_key": order["invoice_request_key"],
        "revision": order["revision"],
        "quantity_on_hand": snap["quantity_on_hand"],
        "quantity_reserved": snap["quantity_reserved"],
        "quantity_available": snap["quantity_available"],
    }


def test_replay_gate_pre_rebuild_inconsistent():
    observability = _import_observability()
    conn = _ReplayConn()
    _assert_ic_1253_fail(observability, conn)


def test_replay_gate_deterministic_rebuild():
    observability = _import_observability()
    reconciliation = _import_reconciliation()
    conn = _ReplayConn()

    reconciliation.reconcile_payment_cache(conn, order_id=UUID(ORDER_ID), trace_id="replay")
    reconciliation.reconcile_shipment_cache(conn, order_id=UUID(ORDER_ID), trace_id="replay")
    reconciliation.rebuild_stock_snapshot(
        conn,
        product_id=UUID(PRODUCT_ID),
        warehouse_code=WAREHOUSE_CODE,
        trace_id="replay",
    )
    reconciliation.reconcile_document_key(conn, order_id=UUID(ORDER_ID), trace_id="replay")

    _assert_ic_1253_pass(observability, conn)

    assert conn.order_ledger[ORDER_ID]["payment_status"] == "paid"
    assert conn.order_ledger[ORDER_ID]["cdek_uuid"] == "cdek-active"
    snap = conn.availability_snapshot[(PRODUCT_ID, WAREHOUSE_CODE)]
    assert snap["quantity_on_hand"] == 20
    assert snap["quantity_reserved"] == 5
    assert snap["quantity_available"] == 15
    assert conn.order_ledger[ORDER_ID]["invoice_request_key"] == DOC_KEY
    assert conn.order_ledger[ORDER_ID]["revision"] == 1


def test_replay_gate_rebuild_is_idempotent():
    observability = _import_observability()
    reconciliation = _import_reconciliation()
    conn = _ReplayConn()

    reconciliation.reconcile_payment_cache(conn, order_id=UUID(ORDER_ID), trace_id="r1")
    reconciliation.reconcile_shipment_cache(conn, order_id=UUID(ORDER_ID), trace_id="r1")
    reconciliation.rebuild_stock_snapshot(
        conn,
        product_id=UUID(PRODUCT_ID),
        warehouse_code=WAREHOUSE_CODE,
        trace_id="r1",
    )
    reconciliation.reconcile_document_key(conn, order_id=UUID(ORDER_ID), trace_id="r1")

    before_second = deepcopy(_cache_signature(conn))
    second_rc1 = reconciliation.reconcile_payment_cache(conn, order_id=UUID(ORDER_ID), trace_id="r2")
    reconciliation.reconcile_shipment_cache(conn, order_id=UUID(ORDER_ID), trace_id="r2")
    reconciliation.rebuild_stock_snapshot(
        conn,
        product_id=UUID(PRODUCT_ID),
        warehouse_code=WAREHOUSE_CODE,
        trace_id="r2",
    )
    second_rc5 = reconciliation.reconcile_document_key(conn, order_id=UUID(ORDER_ID), trace_id="r2")
    after_second = _cache_signature(conn)

    assert second_rc1["action"] == "noop"
    assert second_rc5["action"] == "noop"
    assert after_second == before_second
    _assert_ic_1253_pass(observability, conn)


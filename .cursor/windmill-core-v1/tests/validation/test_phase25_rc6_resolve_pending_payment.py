from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID


ORDER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TX_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _import_reconciliation():
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module("domain.reconciliation_service")


class _StubInvoiceAdapter:
    def __init__(self, *, provider_status: str = "paid", error: Exception | None = None) -> None:
        self._provider_status = provider_status
        self._error = error
        self.calls = []

    def get_invoice_status(self, request):
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        return SimpleNamespace(
            provider_status=self._provider_status,
            raw_response={"provider_status": self._provider_status},
        )


class _Rc6Cursor:
    def __init__(self, conn: "_Rc6Conn") -> None:
        self._conn = conn
        self._rows = []
        self.rowcount = 0

    def execute(self, query: str, params=None):
        params = params or ()
        normalized = " ".join(query.strip().lower().split())

        if normalized.startswith("select id, order_id, status, provider_code, provider_transaction_id from payment_transactions"):
            tx_id = str(params[0])
            tx = next((row for row in self._conn.payment_transactions if row["id"] == tx_id), None)
            if not tx:
                self._rows = []
                return
            self._rows = [
                (
                    tx["id"],
                    tx["order_id"],
                    tx["status"],
                    tx["provider_code"],
                    tx["provider_transaction_id"],
                )
            ]
            return

        if normalized.startswith("update payment_transactions set status = %s"):
            next_status = str(params[0])
            raw_provider_response = params[1]
            trace_id = params[2]
            tx_id = str(params[3])
            tx = next((row for row in self._conn.payment_transactions if row["id"] == tx_id), None)
            if not tx or tx["status"] != "pending":
                self.rowcount = 0
                self._rows = []
                return
            tx["status"] = next_status
            tx["raw_provider_response"] = raw_provider_response
            if tx.get("trace_id") is None and trace_id is not None:
                tx["trace_id"] = trace_id
            self.rowcount = 1
            self._rows = []
            return

        if normalized.startswith("select order_id, payment_status, metadata, order_total_minor from order_ledger"):
            order_id = str(params[0])
            row = self._conn.order_ledger.get(order_id)
            self._rows = [(order_id, row["payment_status"], row["metadata"], row.get("order_total_minor"))] if row else []
            return

        if normalized.startswith("select coalesce(sum(amount_minor), 0) from payment_transactions"):
            order_id = str(params[0])
            if "transaction_type = 'charge'" in normalized:
                total = sum(
                    row["amount_minor"]
                    for row in self._conn.payment_transactions
                    if row["order_id"] == order_id
                    and row["status"] == "confirmed"
                    and row["transaction_type"] == "charge"
                )
            else:
                total = sum(
                    row["amount_minor"]
                    for row in self._conn.payment_transactions
                    if row["order_id"] == order_id
                    and row["status"] == "confirmed"
                    and row["transaction_type"] in {"refund", "chargeback"}
                )
            self._rows = [(total,)]
            return

        if normalized.startswith("select exists ( select 1 from payment_transactions"):
            order_id = str(params[0])
            exists = any(
                row["order_id"] == order_id
                and row["status"] == "pending"
                and row["transaction_type"] == "refund"
                for row in self._conn.payment_transactions
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

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self):
        return None


class _Rc6Conn:
    def __init__(self, *, tx_status: str = "pending", payment_status: str = "unpaid") -> None:
        self.autocommit = False
        self.order_ledger = {
            ORDER_ID: {
                "payment_status": payment_status,
                "metadata": {"totalAmount": 100.0},
                "trace_id": None,
            }
        }
        self.payment_transactions = [
            {
                "id": TX_ID,
                "order_id": ORDER_ID,
                "status": tx_status,
                "provider_code": "tbank",
                "provider_transaction_id": "prov-1",
                "transaction_type": "charge",
                "amount_minor": 10000,
                "trace_id": None,
                "raw_provider_response": {},
            }
        ]

    def cursor(self):
        return _Rc6Cursor(self)


def test_rc6_resolve_pending_payment_confirmed_update_and_idempotent_noop():
    svc = _import_reconciliation()
    conn = _Rc6Conn(tx_status="pending", payment_status="unpaid")
    adapter = _StubInvoiceAdapter(provider_status="paid")
    tx_id = UUID(TX_ID)

    first = svc.resolve_pending_payment(conn, payment_transaction_id=tx_id, adapter=adapter, trace_id="tr-rc6-1")
    second = svc.resolve_pending_payment(conn, payment_transaction_id=tx_id, adapter=adapter, trace_id="tr-rc6-2")

    assert first["action"] == "updated"
    assert first["transaction_status"] == "confirmed"
    assert first["cache_result"]["payment_status"] == "paid"
    assert conn.payment_transactions[0]["status"] == "confirmed"
    assert conn.order_ledger[ORDER_ID]["payment_status"] == "paid"

    assert second["action"] == "noop"
    assert second["reason"] == "not_pending"
    assert second["status"] == "confirmed"


def test_rc6_resolve_pending_payment_noop_when_not_pending():
    svc = _import_reconciliation()
    conn = _Rc6Conn(tx_status="confirmed", payment_status="paid")
    adapter = _StubInvoiceAdapter(provider_status="paid")

    result = svc.resolve_pending_payment(
        conn,
        payment_transaction_id=UUID(TX_ID),
        adapter=adapter,
        trace_id="tr-rc6-noop",
    )

    assert result["action"] == "noop"
    assert result["reason"] == "not_pending"
    assert result["status"] == "confirmed"


def test_rc6_resolve_pending_payment_adapter_error_unknown():
    svc = _import_reconciliation()
    conn = _Rc6Conn(tx_status="pending", payment_status="unpaid")
    adapter = _StubInvoiceAdapter(error=RuntimeError("timeout"))

    result = svc.resolve_pending_payment(
        conn,
        payment_transaction_id=UUID(TX_ID),
        adapter=adapter,
        trace_id="tr-rc6-error",
    )

    assert result["action"] == "UNKNOWN"
    assert result["reason"] == "adapter_error"
    assert "timeout" in result["error"]
    assert conn.payment_transactions[0]["status"] == "pending"
    assert conn.order_ledger[ORDER_ID]["payment_status"] == "unpaid"

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from uuid import UUID


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _import_payment_service():
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module("domain.payment_service")


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows = []
        self.rowcount = 0

    def execute(self, query: str, params=None):
        params = params or ()
        normalized = " ".join(query.strip().lower().split())

        if normalized.startswith("select order_id, metadata, order_total_minor from order_ledger"):
            order_id = str(params[0])
            row = self._conn.order_ledger.get(order_id)
            self._rows = [(order_id, row["metadata"], None)] if row else []
            return

        if normalized.startswith("insert into payment_transactions"):
            key = params[9]
            if key in self._conn.by_idempotency:
                self._rows = []
                return
            tx_id = f"tx-{len(self._conn.payment_transactions)+1}"
            tx = {
                "id": tx_id,
                "order_id": str(params[0]),
                "transaction_type": params[2],
                "status": params[7],
                "amount_minor": int(params[5]),
                "idempotency_key": key,
            }
            self._conn.payment_transactions.append(tx)
            self._conn.by_idempotency.add(key)
            self._rows = [(tx_id,)]
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
                    if tx["order_id"] == order_id and tx["status"] == "confirmed" and tx["transaction_type"] in {"refund", "chargeback"}
                )
            self._rows = [(total,)]
            return

        if normalized.startswith("select exists ( select 1 from payment_transactions"):
            self._rows = [(False,)]
            return

        if normalized.startswith("update order_ledger set payment_status = %s"):
            payment_status, order_id = params
            self._conn.order_ledger[str(order_id)]["payment_status"] = payment_status
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
            "11111111-1111-1111-1111-111111111111": {
                "metadata": {"totalAmount": 100.0},
                "payment_status": "unpaid",
            }
        }
        self.payment_transactions = []
        self.by_idempotency = set()
        self.commit_calls = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commit_calls += 1


def test_payment_transaction_update_is_atomic_service_step_without_commit_side_effect():
    svc = _import_payment_service()
    conn = _Conn()
    order_id = UUID("11111111-1111-1111-1111-111111111111")

    result = svc.record_payment_transaction_atomic(
        conn,
        order_id=order_id,
        trace_id=None,
        transaction_type="charge",
        provider_code="tbank",
        provider_transaction_id="inv-1",
        amount_minor=10000,
        currency="RUB",
        status="confirmed",
        status_changed_at="2026-01-01T00:00:00Z",
        idempotency_key="payment:tbank:inv-1",
        raw_provider_response={"invoice_id": "inv-1"},
        metadata={},
    )
    assert result["action"] == "inserted"
    assert conn.order_ledger[str(order_id)]["payment_status"] == "paid"
    assert conn.commit_calls == 0

    dup = svc.record_payment_transaction_atomic(
        conn,
        order_id=order_id,
        trace_id=None,
        transaction_type="charge",
        provider_code="tbank",
        provider_transaction_id="inv-1",
        amount_minor=10000,
        currency="RUB",
        status="confirmed",
        status_changed_at="2026-01-01T00:00:00Z",
        idempotency_key="payment:tbank:inv-1",
        raw_provider_response={"invoice_id": "inv-1"},
        metadata={},
    )
    assert dup["action"] == "duplicate"
    assert conn.commit_calls == 0


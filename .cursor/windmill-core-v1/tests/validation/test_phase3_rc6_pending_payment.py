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
# Stub adapter
# ---------------------------------------------------------------------------

class _StubTBankAdapter:
    """Minimal TBank adapter stub for resolve_pending_payment."""

    def __init__(self, *, provider_status: str) -> None:
        self._provider_status = provider_status

    def get_invoice_status(self, req):
        class _Result:
            raw_response: dict = {}

        r = _Result()
        r.provider_status = self._provider_status
        return r


# ---------------------------------------------------------------------------
# Stub DB — handles all SQL from resolve_pending_payment + reconcile_payment_cache
# ---------------------------------------------------------------------------

class _Rc6Cursor:
    def __init__(self, conn: "_Rc6Conn") -> None:
        self._conn = conn
        self._rows: list = []
        self.rowcount = 0

    def execute(self, query: str, params=None) -> None:  # noqa: C901
        params = params or ()
        n = " ".join(query.strip().lower().split())

        # resolve_pending_payment — SELECT payment_transaction FOR UPDATE
        if n.startswith(
            "select id, order_id, status, provider_code, provider_transaction_id from payment_transactions"
        ):
            tx_id = str(params[0])
            tx = self._conn.payment_transactions.get(tx_id)
            if tx:
                self._rows = [(tx_id, tx["order_id"], tx["status"], tx["provider_code"], tx["provider_transaction_id"])]
            else:
                self._rows = []
            return

        # resolve_pending_payment — UPDATE payment_transactions SET status
        if n.startswith("update payment_transactions set status"):
            new_status = params[0]
            tx_id = str(params[3])
            tx = self._conn.payment_transactions.get(tx_id)
            if tx and tx["status"] == "pending":
                tx["status"] = new_status
                self.rowcount = 1
            else:
                self.rowcount = 0
            self._rows = []
            return

        # reconcile_payment_cache — SELECT order_ledger FOR UPDATE
        if n.startswith("select order_id, payment_status, metadata, order_total_minor from order_ledger"):
            order_id = str(params[0])
            row = self._conn.order_ledger.get(order_id)
            if row:
                self._rows = [(order_id, row["payment_status"], row["metadata"], row["order_total_minor"])]
            else:
                self._rows = []
            return

        # reconcile_payment_cache — SELECT SUM charges
        if (
            "select coalesce(sum(amount_minor), 0) from payment_transactions" in n
            and "transaction_type = 'charge'" in n
        ):
            order_id = str(params[0])
            total = sum(
                tx["amount_minor"]
                for tx in self._conn.payment_transactions.values()
                if tx["order_id"] == order_id
                and tx["status"] == "confirmed"
                and tx["transaction_type"] == "charge"
            )
            self._rows = [(total,)]
            return

        # reconcile_payment_cache — SELECT SUM refunds
        if (
            "select coalesce(sum(amount_minor), 0) from payment_transactions" in n
            and "transaction_type in ('refund', 'chargeback')" in n
        ):
            order_id = str(params[0])
            total = sum(
                tx["amount_minor"]
                for tx in self._conn.payment_transactions.values()
                if tx["order_id"] == order_id
                and tx["status"] == "confirmed"
                and tx["transaction_type"] in {"refund", "chargeback"}
            )
            self._rows = [(total,)]
            return

        # reconcile_payment_cache — SELECT EXISTS pending refund
        if "select exists" in n and "status = 'pending'" in n and "transaction_type = 'refund'" in n:
            self._rows = [(False,)]
            return

        # reconcile_payment_cache — UPDATE order_ledger SET payment_status
        if n.startswith("update order_ledger set payment_status"):
            new_status = params[0]
            order_id = str(params[2])
            if order_id in self._conn.order_ledger:
                self._conn.order_ledger[order_id]["payment_status"] = new_status
            self.rowcount = 1
            self._rows = []
            return

        # verify_pending_payment_state — SELECT id, order_id, status FROM payment_transactions
        if n.startswith("select id, order_id, status from payment_transactions"):
            tx_id = str(params[0])
            tx = self._conn.payment_transactions.get(tx_id)
            if tx:
                self._rows = [(tx_id, tx["order_id"], tx["status"])]
            else:
                self._rows = []
            return

        raise AssertionError(f"Unexpected SQL in _Rc6Cursor: {n!r}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self) -> None:
        pass


class _Rc6Conn:
    def __init__(self, *, tx_status: str = "pending") -> None:
        self.autocommit = False
        self.order_id = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
        self.tx_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"

        self.payment_transactions = {
            self.tx_id: {
                "order_id": self.order_id,
                "status": tx_status,
                "provider_code": "tbank",
                "provider_transaction_id": "TBANK-PAY-001",
                "transaction_type": "charge",
                "amount_minor": 10000,
            }
        }
        self.order_ledger = {
            self.order_id: {
                "payment_status": "unpaid",
                "metadata": {"totalAmount": 100.0},
                "order_total_minor": None,
            }
        }

    def cursor(self) -> _Rc6Cursor:
        return _Rc6Cursor(self)

    def commit(self) -> None:
        pass


# ---------------------------------------------------------------------------
# resolve_pending_payment tests
# ---------------------------------------------------------------------------

def test_rc6_resolves_pending_to_confirmed_on_paid_status() -> None:
    _ensure_path()
    recon = importlib.import_module("domain.reconciliation_service")
    conn = _Rc6Conn(tx_status="pending")
    adapter = _StubTBankAdapter(provider_status="paid")

    result = recon.resolve_pending_payment(
        conn,
        payment_transaction_id=UUID(conn.tx_id),
        adapter=adapter,
        trace_id="tr-rc6-a",
    )

    assert result["action"] == "updated"
    assert result["transaction_status"] == "confirmed"
    assert conn.payment_transactions[conn.tx_id]["status"] == "confirmed"
    assert conn.order_ledger[conn.order_id]["payment_status"] == "paid"


def test_rc6_noop_when_transaction_already_confirmed() -> None:
    _ensure_path()
    recon = importlib.import_module("domain.reconciliation_service")
    conn = _Rc6Conn(tx_status="confirmed")
    adapter = _StubTBankAdapter(provider_status="paid")

    result = recon.resolve_pending_payment(
        conn,
        payment_transaction_id=UUID(conn.tx_id),
        adapter=adapter,
        trace_id="tr-rc6-noop",
    )

    assert result["action"] == "noop"
    assert result["reason"] == "not_pending"


# ---------------------------------------------------------------------------
# verify_pending_payment_state tests (from reconciliation_verify_ext)
# ---------------------------------------------------------------------------

def test_rc6_verify_match_when_resolved() -> None:
    _ensure_path()
    verify_ext = importlib.import_module("domain.reconciliation_verify_ext")
    conn = _Rc6Conn(tx_status="confirmed")

    result = verify_ext.verify_pending_payment_state(
        conn,
        payment_transaction_id=UUID(conn.tx_id),
        trace_id="tr-v-rc6",
    )

    assert result["verdict"] == "MATCH"
    assert result["actual_status"] == "confirmed"


def test_rc6_verify_divergence_when_still_pending() -> None:
    _ensure_path()
    verify_ext = importlib.import_module("domain.reconciliation_verify_ext")
    conn = _Rc6Conn(tx_status="pending")

    result = verify_ext.verify_pending_payment_state(
        conn,
        payment_transaction_id=UUID(conn.tx_id),
        trace_id="tr-v-rc6-div",
    )

    assert result["verdict"] == "DIVERGENCE"
    assert result["actual_status"] == "pending"

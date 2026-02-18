from __future__ import annotations

import importlib
import sys
from pathlib import Path
from uuid import UUID


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _import_observability():
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module("domain.observability_service")


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows = []

    def execute(self, query: str, params=None):
        params = params or ()
        normalized = " ".join(query.strip().lower().split())

        if normalized.startswith("select order_id, payment_status, metadata, order_total_minor from order_ledger"):
            order_id = str(params[0])
            order = self._conn.order_ledger.get(order_id)
            self._rows = [
                (
                    order_id,
                    order["payment_status"],
                    order["metadata"],
                    order.get("order_total_minor"),
                )
            ] if order else []
            return

        if normalized.startswith("select coalesce(sum(amount_minor), 0) from payment_transactions"):
            order_id = str(params[0])
            txs = [t for t in self._conn.payment_transactions if t["order_id"] == order_id]
            if "transaction_type = 'charge'" in normalized:
                total = sum(t["amount_minor"] for t in txs if t["status"] == "confirmed" and t["transaction_type"] == "charge")
            elif "transaction_type in ('refund', 'chargeback')" in normalized:
                total = sum(
                    t["amount_minor"]
                    for t in txs
                    if t["status"] == "confirmed" and t["transaction_type"] in {"refund", "chargeback"}
                )
            else:
                raise AssertionError(f"Unexpected SQL branch: {normalized}")
            self._rows = [(total,)]
            return

        if normalized.startswith("select exists ( select 1 from payment_transactions"):
            order_id = str(params[0])
            exists = any(
                t["order_id"] == order_id and t["status"] == "pending" and t["transaction_type"] == "refund"
                for t in self._conn.payment_transactions
            )
            self._rows = [(exists,)]
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self):
        return None


class _Conn:
    def __init__(self, *, payment_status: str) -> None:
        self.autocommit = False
        self.order_ledger = {
            "11111111-1111-1111-1111-111111111111": {
                "payment_status": payment_status,
                "metadata": {"totalAmount": 100.0},
            }
        }
        self.payment_transactions = [
            {
                "order_id": "11111111-1111-1111-1111-111111111111",
                "status": "confirmed",
                "transaction_type": "charge",
                "amount_minor": 10000,
            }
        ]

    def cursor(self):
        return _Cursor(self)


def test_ic1_payment_cache_integrity_pass_and_fail():
    obs = _import_observability()
    order_id = UUID("11111111-1111-1111-1111-111111111111")

    conn_pass = _Conn(payment_status="paid")
    verdict_pass = obs.check_payment_cache_integrity(conn_pass, order_id=order_id, trace_id="t-pass")
    assert verdict_pass["verdict"] == "PASS"
    assert verdict_pass["severity"] == "INFO"

    conn_fail = _Conn(payment_status="unpaid")
    verdict_fail = obs.check_payment_cache_integrity(conn_fail, order_id=order_id, trace_id="t-fail")
    assert verdict_fail["verdict"] == "FAIL"
    assert verdict_fail["severity"] == "CRITICAL"
    assert verdict_fail["details"]["expected_status"] == "paid"


def test_health_classifier_priority(monkeypatch):
    obs = _import_observability()
    order_id = UUID("22222222-2222-2222-2222-222222222222")

    class _EmptyConn:
        autocommit = False

        class _Cur:
            def execute(self, *_args, **_kwargs):
                return None

            def fetchone(self):
                return ("pending_invoice", None)

            def close(self):
                return None

        def cursor(self):
            return self._Cur()

    conn = _EmptyConn()

    monkeypatch.setattr(
        obs,
        "collect_order_invariant_verdicts",
        lambda *_args, **_kwargs: [
            {"check_name": "IC-1", "verdict": "FAIL"},
            {"check_name": "IC-7", "verdict": "STALE"},
        ],
    )
    res_inconsistent = obs.classify_order_health(conn, order_id=order_id, trace_id="t-1", reconciliation_failed=False)
    assert res_inconsistent["health"] == "INCONSISTENT"

    res_manual = obs.classify_order_health(conn, order_id=order_id, trace_id="t-2", reconciliation_failed=True)
    assert res_manual["health"] == "REQUIRES_MANUAL"

    monkeypatch.setattr(
        obs,
        "collect_order_invariant_verdicts",
        lambda *_args, **_kwargs: [{"check_name": "IC-7", "verdict": "STALE"}],
    )
    res_stuck = obs.classify_order_health(conn, order_id=order_id, trace_id="t-3")
    assert res_stuck["health"] == "STUCK"


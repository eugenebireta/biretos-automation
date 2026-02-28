from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _import_checks():
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module("domain.structural_checks")


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows = []

    def execute(self, query: str, params=None):
        params = params or ()
        normalized = " ".join(query.strip().lower().split())

        if normalized.startswith("select product_id, warehouse_code, coalesce(sum(quantity_delta), 0) as on_hand"):
            limit = int(params[0])
            self._rows = list(self._conn.neg_stock_rows)[:limit]
            return

        if normalized.startswith("select r.id, r.order_id, r.line_item_id, o.state"):
            # params: (TERMINAL_ORDER_STATES, limit)
            limit = int(params[1])
            self._rows = list(self._conn.terminal_res_rows)[:limit]
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchall(self):
        rows = self._rows
        self._rows = []
        return rows

    def close(self):
        return None


class _Conn:
    def __init__(self):
        self.neg_stock_rows = []
        self.terminal_res_rows = []

    def cursor(self):
        return _Cursor(self)


def test_check_stock_ledger_non_negative_pass_and_fail():
    checks = _import_checks()
    conn = _Conn()

    ok = checks.check_stock_ledger_non_negative(conn, trace_id="t1")
    assert ok["verdict"] == "PASS"
    assert ok["problems"] == []

    conn.neg_stock_rows = [("p1", "WH-1", -5)]
    bad = checks.check_stock_ledger_non_negative(conn, trace_id="t2")
    assert bad["verdict"] == "FAIL"
    assert bad["check_code"] == "L3-A"
    assert bad["severity"] == "CRITICAL"
    assert bad["problems"][0]["entity_id"] == "p1:WH-1"


def test_check_reservations_for_terminal_orders_pass_and_fail():
    checks = _import_checks()
    conn = _Conn()

    ok = checks.check_reservations_for_terminal_orders(conn, trace_id="t1")
    assert ok["verdict"] == "PASS"
    assert ok["problems"] == []

    conn.terminal_res_rows = [("r1", "o1", "li1", "completed")]
    bad = checks.check_reservations_for_terminal_orders(conn, trace_id="t2")
    assert bad["verdict"] == "FAIL"
    assert bad["check_code"] == "L3-D"
    assert bad["severity"] == "MEDIUM"
    assert bad["problems"][0]["entity_id"] == "r1"


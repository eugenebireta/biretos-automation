from __future__ import annotations

import sys
from pathlib import Path


def _ensure_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_path()

from ru_worker.send_invoice_execution import execute_send_invoice, resolve_send_invoice_request


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows = []

    def execute(self, query: str, params=None) -> None:
        normalized = " ".join(query.strip().lower().split())
        params = params or ()
        self._rows = []
        self._conn.queries.append((normalized, params))

        if normalized.startswith("select order_id::text, insales_order_id, customer_data, delivery_data, metadata, order_total_minor from order_ledger"):
            order = self._conn.orders.get(str(params[0]))
            if order is not None:
                self._rows = [(
                    order["order_id"],
                    order["insales_order_id"],
                    order["customer_data"],
                    order["delivery_data"],
                    order["metadata"],
                    order["order_total_minor"],
                )]
            return

        if normalized.startswith("select line_seq, product_id, sku_snapshot, name_snapshot, quantity, price_unit_minor, tax_rate_bps from order_line_items"):
            rows = self._conn.line_items.get(str(params[0]), [])
            self._rows = [
                (
                    row["line_seq"],
                    row.get("product_id"),
                    row["sku_snapshot"],
                    row["name_snapshot"],
                    row["quantity"],
                    row["price_unit_minor"],
                    row.get("tax_rate_bps", 0),
                )
                for row in rows[:2]
            ]
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows = list(self._rows)
        self._rows = []
        return rows

    def close(self) -> None:
        return None


class _Conn:
    def __init__(self, *, orders=None, line_items=None) -> None:
        self.orders = orders or {}
        self.line_items = line_items or {}
        self.queries = []

    def cursor(self) -> _Cursor:
        return _Cursor(self)


class _BrokenConn:
    def cursor(self):
        raise RuntimeError("relation order_ledger does not exist")


def _order(*, order_id: str = "11111111-1111-1111-1111-111111111111", insales_order_id: str = "ORDER-123") -> dict:
    return {
        "order_id": order_id,
        "insales_order_id": insales_order_id,
        "customer_data": {"companyName": "ООО Тест", "inn": "7701234567"},
        "delivery_data": {"city": "Moscow"},
        "metadata": {"currency": "RUB"},
        "order_total_minor": 15000,
    }


def _line(*, line_seq: int = 1, quantity: int = 1, price_unit_minor: int = 12000) -> dict:
    return {
        "line_seq": line_seq,
        "product_id": None,
        "sku_snapshot": "SKU-1",
        "name_snapshot": "Товар",
        "quantity": quantity,
        "price_unit_minor": price_unit_minor,
        "tax_rate_bps": 0,
    }


def test_resolve_send_invoice_ready_single_line_item():
    order = _order()
    conn = _Conn(
        orders={order["insales_order_id"]: order},
        line_items={order["order_id"]: [_line()]},
    )

    result = resolve_send_invoice_request(
        conn,
        trace_id="trace-send-1",
        payload={"insales_order_id": order["insales_order_id"]},
    )

    assert result["status"] == "ready"
    assert result["invoice_payload"]["insales_order_id"] == "ORDER-123"
    assert result["invoice_payload"]["total_amount"] == 150.0
    assert result["invoice_payload"]["delivery_cost"] == 30.0
    assert result["invoice_payload"]["product"]["name"] == "Товар"


def test_send_invoice_requires_explicit_order_id():
    conn = _Conn()

    result = execute_send_invoice(
        conn,
        trace_id="trace-send-2",
        payload={},
    )

    assert result["status"] == "insufficient_context"
    assert result["error"] == "send_invoice_requires_insales_order_id"


def test_send_invoice_requires_single_line_item_snapshot():
    order = _order(insales_order_id="ORDER-456")
    conn = _Conn(
        orders={order["insales_order_id"]: order},
        line_items={order["order_id"]: [_line(line_seq=1), _line(line_seq=2)]},
    )

    result = execute_send_invoice(
        conn,
        trace_id="trace-send-3",
        payload={"insales_order_id": order["insales_order_id"]},
    )

    assert result["status"] == "review_required"
    assert result["error"] == "send_invoice_multiple_line_items_unsupported"


def test_send_invoice_success_uses_invoice_executor():
    order = _order(insales_order_id="ORDER-789")
    conn = _Conn(
        orders={order["insales_order_id"]: order},
        line_items={order["order_id"]: [_line()]},
    )
    captured = {}

    def _executor(payload, db_conn):
        captured["payload"] = payload
        assert db_conn is conn
        return {
            "status": "completed",
            "ok": True,
            "tbank_invoice_id": "TBANK-1",
            "invoice_number": "INV-1",
        }

    result = execute_send_invoice(
        conn,
        trace_id="trace-send-4",
        payload={"insales_order_id": order["insales_order_id"]},
        invoice_executor=_executor,
    )

    assert result["status"] == "success"
    assert result["provider_document_id"] == "TBANK-1"
    assert captured["payload"]["product"]["sku"] == "SKU-1"


def test_send_invoice_gracefully_handles_missing_order_context_backend():
    result = execute_send_invoice(
        _BrokenConn(),
        trace_id="trace-send-5",
        payload={"insales_order_id": "ORDER-999"},
    )

    assert result["status"] == "review_required"
    assert result["error"] == "send_invoice_order_context_unavailable"

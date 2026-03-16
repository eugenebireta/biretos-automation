from __future__ import annotations

from typing import Any, Dict, List, Optional

from ru_worker.shopware_order_handoff import execute_shopware_order_handoff


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows: List[Any] = []

    def execute(self, query: str, params: Optional[tuple[Any, ...]] = None) -> None:
        params = params or ()
        normalized = " ".join(query.strip().lower().split())

        if normalized.startswith("insert into order_ledger"):
            self._conn.order_ledger_writes.append(params)
            self._rows = []
            return

        if normalized.startswith("insert into shopware_outbound_queue"):
            _, _, _, idempotency_key, _trace_id = params
            if idempotency_key in self._conn.outbound_idem:
                self._rows = []
                return
            self._conn.outbound_idem.add(idempotency_key)
            self._rows = [("queue-id",)]
            return

        if normalized.startswith("update shopware_inbound_events set processing_status = 'processed'"):
            self._conn.inbound_status_updates.append(("processed", params[0]))
            self._rows = []
            return

        if normalized.startswith("update shopware_inbound_events set processing_status = 'failed'"):
            self._conn.inbound_status_updates.append(("failed", params[1]))
            self._rows = []
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        if not self._rows:
            return None
        return self._rows.pop(0)

    def close(self) -> None:
        return None


class _Conn:
    def __init__(self) -> None:
        self.order_ledger_writes: List[Any] = []
        self.outbound_idem: set[str] = set()
        self.inbound_status_updates: List[tuple[str, str]] = []

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def test_shopware_handoff_blocked_by_guardian() -> None:
    conn = _Conn()
    payload = {
        "instance": "ru",
        "shopware_event_id": "evt-1",
        "order_number": "SW-100",
        "currency": "RUB",
        "total_minor": -1,
    }
    result = execute_shopware_order_handoff(payload, conn, trace_id="00000000-0000-0000-0000-000000000111")
    assert result["status"] == "blocked"
    assert not conn.order_ledger_writes
    assert conn.inbound_status_updates == [("failed", "evt-1")]


def test_shopware_handoff_creates_order_and_outbound_status() -> None:
    conn = _Conn()
    payload = {
        "instance": "ru",
        "shopware_event_id": "evt-2",
        "order_number": "SW-200",
        "currency": "RUB",
        "total_minor": 12345,
        "payment_state": "paid",
        "customer": {"name": "Test Buyer"},
    }
    result = execute_shopware_order_handoff(payload, conn, trace_id="00000000-0000-0000-0000-000000000222")
    assert result["status"] == "completed"
    assert result["core_state"] == "paid"
    assert result["outbound_enqueued"] is True
    assert len(conn.order_ledger_writes) == 1
    assert conn.inbound_status_updates == [("processed", "evt-2")]

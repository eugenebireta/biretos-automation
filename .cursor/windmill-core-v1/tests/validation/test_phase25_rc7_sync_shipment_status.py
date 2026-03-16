from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID


ORDER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SHIPMENT_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _import_reconciliation():
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module("domain.reconciliation_service")


class _StubShipmentAdapter:
    def __init__(self, *, carrier_status: str = "in_transit", error: Exception | None = None) -> None:
        self._carrier_status = carrier_status
        self._error = error
        self.calls = []

    def get_tracking_status(self, request):
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        return SimpleNamespace(
            carrier_status=self._carrier_status,
            raw_response={"carrier_status": self._carrier_status},
        )


class _Rc7Cursor:
    def __init__(self, conn: "_Rc7Conn") -> None:
        self._conn = conn
        self._rows = []

    def execute(self, query: str, params=None):
        params = params or ()
        normalized = " ".join(query.strip().lower().split())

        if normalized.startswith("select id, order_id, current_status, carrier_external_id from shipments"):
            shipment_id = str(params[0])
            row = self._conn.shipments.get(shipment_id)
            self._rows = [
                (
                    row["id"],
                    row["order_id"],
                    row["current_status"],
                    row["carrier_external_id"],
                )
            ] if row else []
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self):
        return None


class _Rc7Conn:
    def __init__(self, *, current_status: str = "created", carrier_external_id: str | None = "cdek-ext-1") -> None:
        self.autocommit = False
        self.shipments = {
            SHIPMENT_ID: {
                "id": SHIPMENT_ID,
                "order_id": ORDER_ID,
                "current_status": current_status,
                "carrier_external_id": carrier_external_id,
            }
        }

    def cursor(self):
        return _Rc7Cursor(self)


def test_rc7_sync_shipment_status_transition_updated(monkeypatch):
    svc = _import_reconciliation()
    conn = _Rc7Conn(current_status="created", carrier_external_id="cdek-ext-1")
    adapter = _StubShipmentAdapter(carrier_status="in_transit")
    captured = {}

    def _mock_update_shipment_status_atomic(
        db_conn,
        *,
        shipment_id,
        to_status,
        event_id,
        occurred_at,
        reason,
        trace_id,
        context,
    ):
        captured.update(
            {
                "db_conn": db_conn,
                "shipment_id": shipment_id,
                "to_status": to_status,
                "event_id": event_id,
                "occurred_at": occurred_at,
                "reason": reason,
                "trace_id": trace_id,
                "context": context,
            }
        )
        return {"ok": True, "event_id": event_id}

    monkeypatch.setattr(svc, "update_shipment_status_atomic", _mock_update_shipment_status_atomic)

    result = svc.sync_shipment_status(
        conn,
        shipment_id=UUID(SHIPMENT_ID),
        adapter=adapter,
        trace_id="tr-rc7-update",
    )

    assert result["action"] == "updated"
    assert result["from_status"] == "created"
    assert result["to_status"] == "in_transit"
    assert result["shipment_id"] == SHIPMENT_ID
    assert captured["shipment_id"] == UUID(SHIPMENT_ID)
    assert captured["to_status"] == "in_transit"
    assert captured["event_id"].startswith(f"rc7:{SHIPMENT_ID}:")
    assert captured["reason"] == "reconciliation:carrier_status_sync"
    assert captured["context"]["source"] == "phase25_rc7"
    assert result["transition"]["ok"] is True


def test_rc7_sync_shipment_status_noop_when_same_status(monkeypatch):
    svc = _import_reconciliation()
    conn = _Rc7Conn(current_status="in_transit", carrier_external_id="cdek-ext-2")
    adapter = _StubShipmentAdapter(carrier_status="in_transit")
    called = {"value": False}

    def _mock_update_shipment_status_atomic(*_args, **_kwargs):
        called["value"] = True
        return {"ok": True}

    monkeypatch.setattr(svc, "update_shipment_status_atomic", _mock_update_shipment_status_atomic)

    result = svc.sync_shipment_status(
        conn,
        shipment_id=UUID(SHIPMENT_ID),
        adapter=adapter,
        trace_id="tr-rc7-noop",
    )

    assert result["action"] == "noop"
    assert result["status"] == "in_transit"
    assert called["value"] is False


def test_rc7_sync_shipment_status_unknown_when_carrier_external_id_missing(monkeypatch):
    svc = _import_reconciliation()
    conn = _Rc7Conn(current_status="created", carrier_external_id=None)
    adapter = _StubShipmentAdapter(carrier_status="in_transit")
    called = {"value": False}

    def _mock_update_shipment_status_atomic(*_args, **_kwargs):
        called["value"] = True
        return {"ok": True}

    monkeypatch.setattr(svc, "update_shipment_status_atomic", _mock_update_shipment_status_atomic)

    result = svc.sync_shipment_status(
        conn,
        shipment_id=UUID(SHIPMENT_ID),
        adapter=adapter,
        trace_id="tr-rc7-missing",
    )

    assert result["action"] == "UNKNOWN"
    assert result["reason"] == "carrier_external_id_missing"
    assert result["shipment_id"] == SHIPMENT_ID
    assert called["value"] is False

"""
Tests for ru_worker/backoffice_router.py — Phase 6.11.
Pure unit tests: stub DB, stub adapters, deterministic.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_path()

import pytest

from domain.ports import (
    InvoiceStatusRequest,
    InvoiceStatusResponse,
    ShipmentTrackingStatusRequest,
    ShipmentTrackingStatusResponse,
    WaybillRequest,
    WaybillResponse,
)
from ru_worker.backoffice_router import route_backoffice_intent


# ---------------------------------------------------------------------------
# Stub DB (supports execute, fetchone, cursor, commit)
# ---------------------------------------------------------------------------

class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn

    def execute(self, query: str, params=None) -> None:
        self._conn.queries.append((query, params))
        # Simulate INSERT RETURNING for action_logger / snapshot_store
        q = query.strip().lower()
        if "returning" in q:
            self._conn._last_returning = ("stub-id-001",)
        else:
            self._conn._last_returning = None

    def fetchone(self):
        return self._conn._last_returning

    def close(self):
        pass


class _Conn:
    def __init__(self, rate_count: int = 0) -> None:
        self.queries: list = []
        self.committed: bool = False
        self._last_returning = None
        self._rate_count = rate_count

    def cursor(self):
        c = _Cursor(self)

        # Override execute to handle rate-limit COUNT query
        original_execute = c.execute

        def smart_execute(query: str, params=None) -> None:
            q = query.strip().lower()
            if "select count" in q and "employee_actions_log" in q:
                self._last_returning = (self._rate_count,)
            else:
                original_execute(query, params)

        c.execute = smart_execute
        return c

    def commit(self):
        self.committed = True


# ---------------------------------------------------------------------------
# Stub adapters
# ---------------------------------------------------------------------------

class _StubPaymentAdapter:
    def get_invoice_status(self, req: InvoiceStatusRequest) -> InvoiceStatusResponse:
        return InvoiceStatusResponse(
            provider_document_id=req.provider_document_id,
            provider_status="paid",
            raw_response={"status": "paid", "dry_run": True},
        )


class _StubShipmentAdapter:
    def get_tracking_status(self, req: ShipmentTrackingStatusRequest) -> ShipmentTrackingStatusResponse:
        return ShipmentTrackingStatusResponse(
            carrier_external_id=req.carrier_external_id,
            carrier_status="delivered",
            raw_response={"status": "delivered", "dry_run": True},
        )

    def get_waybill(self, req: WaybillRequest) -> WaybillResponse:
        return WaybillResponse(
            carrier_external_id=req.carrier_external_id,
            pdf_bytes=b"%PDF-1.4 stub",
            raw_response={"dry_run": True},
        )


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

def _base_payload(intent_type: str, role: str = "operator", extra: dict | None = None) -> dict:
    p = {
        "trace_id": "trace-router-001",
        "intent_type": intent_type,
        "employee_id": "emp-router-1",
        "employee_role": role,
        "payload": {},
        "metadata": {},
    }
    if extra:
        p["payload"].update(extra)
    return p


def test_check_payment_happy_path():
    conn = _Conn(rate_count=0)
    payload = _base_payload("check_payment", extra={"invoice_id": "INV-001"})
    result = route_backoffice_intent(
        payload, conn,
        payment_adapter=_StubPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["status"] == "success"
    assert result["intent_type"] == "check_payment"
    assert result["provider_status"] == "paid"
    assert conn.committed is True


def test_get_tracking_happy_path():
    conn = _Conn(rate_count=0)
    payload = _base_payload("get_tracking", role="operator", extra={"carrier_external_id": "CDEK-UUID-001"})
    result = route_backoffice_intent(
        payload, conn,
        payment_adapter=_StubPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["status"] == "success"
    assert result["carrier_status"] == "delivered"
    assert conn.committed is True


def test_get_waybill_happy_path():
    conn = _Conn(rate_count=0)
    payload = _base_payload("get_waybill", role="manager", extra={"carrier_external_id": "CDEK-UUID-002"})
    result = route_backoffice_intent(
        payload, conn,
        payment_adapter=_StubPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["status"] == "success"
    assert result["pdf_size_bytes"] > 0
    assert conn.committed is True


def test_result_contains_trace_id():
    conn = _Conn(rate_count=0)
    payload = _base_payload("check_payment", extra={"invoice_id": "INV-002"})
    result = route_backoffice_intent(
        payload, conn,
        payment_adapter=_StubPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["trace_id"] == "trace-router-001"


# ---------------------------------------------------------------------------
# Permission denied
# ---------------------------------------------------------------------------

def test_operator_cannot_get_waybill_returns_forbidden():
    conn = _Conn(rate_count=0)
    payload = _base_payload("get_waybill", role="operator", extra={"carrier_external_id": "CDEK-001"})
    result = route_backoffice_intent(
        payload, conn,
        payment_adapter=_StubPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["status"] == "forbidden"
    assert result["invariant"] == "INV-PERMISSION-DENIED"
    # Even for forbidden, we still commit the audit log
    assert conn.committed is True


def test_unknown_role_returns_forbidden():
    conn = _Conn(rate_count=0)
    payload = _base_payload("check_payment", role="superuser", extra={"invoice_id": "INV-003"})
    result = route_backoffice_intent(
        payload, conn,
        payment_adapter=_StubPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["status"] == "forbidden"
    assert "invariant" in result


def test_unknown_intent_returns_forbidden():
    conn = _Conn(rate_count=0)
    payload = {
        "trace_id": "trace-unk-001",
        "intent_type": "delete_all",
        "employee_id": "emp-1",
        "employee_role": "admin",
        "payload": {},
    }
    result = route_backoffice_intent(
        payload, conn,
        payment_adapter=_StubPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["status"] == "forbidden"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def test_rate_limited_low_risk():
    conn = _Conn(rate_count=200)  # Over LOW limit (100)
    payload = _base_payload("check_payment", extra={"invoice_id": "INV-004"})
    result = route_backoffice_intent(
        payload, conn,
        payment_adapter=_StubPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["status"] == "rate_limited"
    assert result["current_count"] == 200
    assert conn.committed is True


def test_rate_limited_medium_risk():
    conn = _Conn(rate_count=25)  # Over MEDIUM limit (20)
    payload = _base_payload("get_waybill", role="manager", extra={"carrier_external_id": "CDEK-003"})
    result = route_backoffice_intent(
        payload, conn,
        payment_adapter=_StubPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["status"] == "rate_limited"
    assert result["limit"] == 20


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

def test_missing_trace_id_returns_error():
    conn = _Conn(rate_count=0)
    payload = {
        "intent_type": "check_payment",
        "employee_id": "emp-1",
        "employee_role": "operator",
        "payload": {"invoice_id": "INV-001"},
    }
    result = route_backoffice_intent(
        payload, conn,
        payment_adapter=_StubPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["status"] == "error"
    assert result["error_class"] == "POLICY_VIOLATION"


def test_empty_trace_id_returns_error():
    conn = _Conn(rate_count=0)
    payload = {
        "trace_id": "",
        "intent_type": "check_payment",
        "employee_id": "emp-1",
        "employee_role": "operator",
        "payload": {"invoice_id": "INV-001"},
    }
    result = route_backoffice_intent(
        payload, conn,
        payment_adapter=_StubPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["status"] == "error"
    assert result["error_class"] == "POLICY_VIOLATION"


# ---------------------------------------------------------------------------
# Leaf handler errors
# ---------------------------------------------------------------------------

def test_missing_invoice_id_returns_error():
    conn = _Conn(rate_count=0)
    payload = _base_payload("check_payment")  # no invoice_id in payload
    result = route_backoffice_intent(
        payload, conn,
        payment_adapter=_StubPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["status"] == "error"
    assert result["error_class"] == "TRANSIENT"
    assert conn.committed is True


def test_missing_carrier_id_get_tracking_returns_error():
    conn = _Conn(rate_count=0)
    payload = _base_payload("get_tracking")  # no carrier_external_id
    result = route_backoffice_intent(
        payload, conn,
        payment_adapter=_StubPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["status"] == "error"
    assert result["error_class"] == "TRANSIENT"


class _FailingPaymentAdapter:
    def get_invoice_status(self, req):
        raise RuntimeError("TBank API timeout")


def test_adapter_exception_returns_error():
    conn = _Conn(rate_count=0)
    payload = _base_payload("check_payment", extra={"invoice_id": "INV-FAIL"})
    result = route_backoffice_intent(
        payload, conn,
        payment_adapter=_FailingPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["status"] == "error"
    assert result["error_class"] == "TRANSIENT"
    assert "TBank API timeout" in result["error"]
    assert conn.committed is True

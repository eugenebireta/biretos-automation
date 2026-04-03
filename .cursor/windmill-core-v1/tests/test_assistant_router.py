"""
Tests for ru_worker/assistant_router.py — Phase 7.9.
Pure unit tests: stub DB, deterministic.

NLU_ENABLED / NLU_DEGRADATION_LEVEL are controlled via os.environ.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path


def _ensure_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_path()

import pytest
from ru_worker.assistant_router import route_assistant_intent, confirm_nlu_intent


# ---------------------------------------------------------------------------
# Stub DB
# ---------------------------------------------------------------------------

class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn

    def execute(self, query: str, params=None) -> None:
        self._conn.queries.append((query, params))
        q = query.strip().lower()
        if "insert" in q and "returning" in q:
            self._conn._last = (str(uuid.uuid4()),)
        elif "update" in q and "returning" in q and self._conn._pending_row:
            self._conn._last = self._conn._pending_row
            self._conn._pending_row = None
        elif "insert" in q and "nlu_sla_log" in q:
            self._conn._last = None
        elif "insert" in q and "shadow_rag_log" in q:
            self._conn._last = None
        elif "select count" in q and "employee_actions_log" in q:
            # rate limiter COUNT query → 0 calls
            self._conn._last = (0,)
        elif "insert" in q and "employee_actions_log" in q and "returning" in q:
            self._conn._last = ("stub-action-id",)
        elif "insert" in q and "read_snapshots" in q and "returning" in q:
            self._conn._last = ("stub-snapshot-id",)
        else:
            self._conn._last = None

    def fetchone(self):
        return self._conn._last

    def close(self):
        pass


class _Conn:
    def __init__(self, pending_row=None) -> None:
        self.queries = []
        self.committed = False
        self._last = None
        self._pending_row = pending_row

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.committed = True


def _pending_row_tuple(intent_type: str = "check_payment", entities: dict | None = None):
    if entities is None:
        entities = {"invoice_id": "INV-001"}
    row_id = str(uuid.uuid4())
    return (
        row_id, "trace-confirm-001", "emp-1", "operator",
        intent_type, json.dumps(entities),
        "regex-v1", "v1.0", "1.0",
    )


# ---------------------------------------------------------------------------
# route_assistant_intent — button_only (default NLU_ENABLED=false)
# ---------------------------------------------------------------------------

def test_route_button_only_when_nlu_disabled():
    os.environ["NLU_ENABLED"] = "false"
    os.environ["NLU_DEGRADATION_LEVEL"] = "2"
    conn = _Conn()
    result = route_assistant_intent(
        {"trace_id": "trace-ra-001", "employee_id": "emp-1", "text": "отследить посылку"},
        conn,
    )
    assert result["status"] == "button_only"
    assert conn.committed is True


def test_route_missing_trace_id_returns_policy_violation():
    conn = _Conn()
    result = route_assistant_intent(
        {"employee_id": "emp-1", "text": "проверить платёж"},
        conn,
    )
    assert result["status"] == "error"
    assert result["error_class"] == "POLICY_VIOLATION"


def test_route_empty_text_returns_policy_violation():
    os.environ["NLU_ENABLED"] = "false"
    conn = _Conn()
    result = route_assistant_intent(
        {"trace_id": "trace-ra-002", "employee_id": "emp-1", "text": ""},
        conn,
    )
    assert result["status"] == "error"
    assert result["error_class"] == "POLICY_VIOLATION"


def test_route_shadow_mode_returns_shadow():
    os.environ["NLU_ENABLED"] = "true"
    os.environ["NLU_DEGRADATION_LEVEL"] = "0"
    os.environ["NLU_SHADOW_MODE"] = "true"
    conn = _Conn()
    result = route_assistant_intent(
        {"trace_id": "trace-ra-003", "employee_id": "emp-1", "text": "отследить посылку"},
        conn,
    )
    assert result["status"] == "shadow"
    assert conn.committed is True


def test_route_nlu_ok_returns_needs_confirmation():
    os.environ["NLU_ENABLED"] = "true"
    os.environ["NLU_DEGRADATION_LEVEL"] = "0"
    os.environ["NLU_SHADOW_MODE"] = "false"
    conn = _Conn()
    result = route_assistant_intent(
        {"trace_id": "trace-ra-004", "employee_id": "emp-1", "text": "статус доставки"},
        conn,
    )
    assert result["status"] == "needs_confirmation"
    assert "confirmation_id" in result
    assert "reply_markup" in result
    assert conn.committed is True


def test_route_nlu_ok_writes_shadow_and_sla_rows():
    os.environ["NLU_ENABLED"] = "true"
    os.environ["NLU_DEGRADATION_LEVEL"] = "0"
    os.environ["NLU_SHADOW_MODE"] = "false"
    conn = _Conn()
    result = route_assistant_intent(
        {"trace_id": "trace-ra-004b", "employee_id": "emp-1", "text": "статус доставки 10248510566"},
        conn,
    )
    assert result["status"] == "needs_confirmation"
    sql = "\n".join(query for query, _ in conn.queries).lower()
    assert "shadow_rag_log" in sql
    assert "nlu_sla_log" in sql


def test_route_fallback_on_unknown_text():
    os.environ["NLU_ENABLED"] = "true"
    os.environ["NLU_DEGRADATION_LEVEL"] = "0"
    os.environ["NLU_SHADOW_MODE"] = "false"
    conn = _Conn()
    result = route_assistant_intent(
        {"trace_id": "trace-ra-005", "employee_id": "emp-1", "text": "привет как дела"},
        conn,
    )
    assert result["status"] == "fallback"
    assert conn.committed is True


# ---------------------------------------------------------------------------
# confirm_nlu_intent
# ---------------------------------------------------------------------------

def test_confirm_missing_trace_id_returns_policy_violation():
    conn = _Conn()
    result = confirm_nlu_intent(
        {"confirmation_id": "some-id"},
        conn,
    )
    assert result["status"] == "error"
    assert result["error_class"] == "POLICY_VIOLATION"


def test_confirm_missing_confirmation_id_returns_policy_violation():
    conn = _Conn()
    result = confirm_nlu_intent(
        {"trace_id": "trace-c-001"},
        conn,
    )
    assert result["status"] == "error"
    assert result["error_class"] == "POLICY_VIOLATION"


def test_confirm_expired_returns_error():
    conn = _Conn(pending_row=None)  # no pending row = expired/consumed
    result = confirm_nlu_intent(
        {"trace_id": "trace-c-002", "confirmation_id": str(uuid.uuid4())},
        conn,
    )
    assert result["status"] == "error"
    assert result["invariant"] == "INV-MBC"
    assert conn.committed is True


def test_confirm_send_invoice_returns_not_implemented():
    conn = _Conn(pending_row=_pending_row_tuple("send_invoice", {}))
    result = confirm_nlu_intent(
        {"trace_id": "trace-c-003", "confirmation_id": str(uuid.uuid4())},
        conn,
    )
    assert result["status"] == "not_implemented"
    assert result["intent_type"] == "send_invoice"
    assert conn.committed is True


# ---------------------------------------------------------------------------
# Stub payment adapter for confirm routing
# ---------------------------------------------------------------------------

class _StubPaymentAdapter:
    def get_invoice_status(self, req):
        from domain.ports import InvoiceStatusResponse
        return InvoiceStatusResponse(
            provider_document_id=req.provider_document_id,
            provider_status="paid",
            raw_response={"dry_run": True},
        )


class _StubShipmentAdapter:
    def get_tracking_status(self, req):
        from domain.ports import ShipmentTrackingStatusResponse
        return ShipmentTrackingStatusResponse(
            carrier_external_id=req.carrier_external_id,
            carrier_status="delivered",
            raw_response={"dry_run": True},
        )

    def get_waybill(self, req):
        from domain.ports import WaybillResponse
        return WaybillResponse(
            carrier_external_id=req.carrier_external_id,
            pdf_bytes=b"%PDF-stub",
            raw_response={"dry_run": True},
        )


def test_confirm_check_payment_happy_path():
    conn = _Conn(pending_row=_pending_row_tuple("check_payment", {"invoice_id": "INV-999"}))
    result = confirm_nlu_intent(
        {"trace_id": "trace-c-004", "confirmation_id": str(uuid.uuid4())},
        conn,
        payment_adapter=_StubPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["status"] == "success"
    assert result.get("nlu_confirmed") is True


def test_confirm_get_tracking_happy_path():
    conn = _Conn(pending_row=_pending_row_tuple("get_tracking", {"carrier_external_id": "10248510566"}))
    result = confirm_nlu_intent(
        {"trace_id": "trace-c-005", "confirmation_id": str(uuid.uuid4())},
        conn,
        payment_adapter=_StubPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["status"] == "success"
    assert result["intent_type"] == "get_tracking"
    assert result["carrier_external_id"] == "10248510566"
    assert result.get("nlu_confirmed") is True


def test_confirm_get_waybill_happy_path():
    conn = _Conn(pending_row=_pending_row_tuple("get_waybill", {"carrier_external_id": "10248510566"}))
    result = confirm_nlu_intent(
        {"trace_id": "trace-c-006", "confirmation_id": str(uuid.uuid4())},
        conn,
        payment_adapter=_StubPaymentAdapter(),
        shipment_adapter=_StubShipmentAdapter(),
    )
    assert result["status"] == "success"
    assert result["intent_type"] == "get_waybill"
    assert result["carrier_external_id"] == "10248510566"
    assert result["pdf_size_bytes"] > 0

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Optional

from config import get_config
from domain.ports import (
    InvoiceCreateRequest,
    InvoiceCreateResponse,
    InvoiceStatusRequest,
    InvoiceStatusResponse,
    OrderSourcePort,
    PaymentInvoicePort,
    ShipmentCreateRequest,
    ShipmentCreateResponse,
    ShipmentPort,
    ShipmentTrackingStatusRequest,
    ShipmentTrackingStatusResponse,
)
from side_effects.adapters.cdek_adapter import CDEKShipmentAdapter
from side_effects.adapters.insales_adapter import InSalesOrderAdapter
from side_effects.adapters.tbank_adapter import TBankInvoiceAdapter


class ReplayPaymentInvoiceAdapter(PaymentInvoicePort):
    def __init__(self, db_conn=None, trace_id: Optional[str] = None) -> None:
        self._db_conn = db_conn
        self._trace_id = trace_id

    def create_invoice(self, request: InvoiceCreateRequest) -> InvoiceCreateResponse:
        if self._db_conn is not None and self._trace_id:
            cursor = self._db_conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT provider_document_id, pdf_url, raw_provider_response
                    FROM documents
                    WHERE trace_id = %s::uuid
                      AND provider_code = 'tbank'
                      AND document_type = 'invoice'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (self._trace_id,),
                )
                row = cursor.fetchone()
                if row:
                    return InvoiceCreateResponse(
                        provider_document_id=str(row[0]),
                        pdf_url=row[1],
                        raw_response=row[2] if isinstance(row[2], dict) else {"response": row[2], "replay": True},
                    )
            finally:
                cursor.close()

        replay_invoice_id = f"replay-{request.invoice_number}"
        return InvoiceCreateResponse(
            provider_document_id=replay_invoice_id,
            pdf_url=None,
            raw_response={"replay": True, "request": asdict(request)},
        )

    def get_invoice_status(self, request: InvoiceStatusRequest) -> InvoiceStatusResponse:
        if self._db_conn is not None and self._trace_id:
            cursor = self._db_conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT payment_status
                    FROM order_ledger
                    WHERE trace_id = %s::uuid
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (self._trace_id,),
                )
                row = cursor.fetchone()
                if row:
                    status = str(row[0] or "unknown").lower()
                    mapped = "paid" if status in {"paid", "overpaid"} else status
                    return InvoiceStatusResponse(
                        provider_document_id=request.provider_document_id,
                        provider_status=mapped,
                        raw_response={"replay": True, "payment_status": status},
                    )
            finally:
                cursor.close()

        return InvoiceStatusResponse(
            provider_document_id=request.provider_document_id,
            provider_status="unknown",
            raw_response={"replay": True},
        )


class ReplayShipmentAdapter(ShipmentPort):
    def __init__(self, db_conn=None, trace_id: Optional[str] = None) -> None:
        self._db_conn = db_conn
        self._trace_id = trace_id

    def create_shipment(self, request: ShipmentCreateRequest) -> ShipmentCreateResponse:
        if self._db_conn is not None and self._trace_id:
            cursor = self._db_conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT carrier_external_id, carrier_metadata
                    FROM shipments
                    WHERE trace_id = %s::uuid
                      AND carrier_code = 'cdek'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (self._trace_id,),
                )
                row = cursor.fetchone()
                if row:
                    return ShipmentCreateResponse(
                        carrier_external_id=str(row[0]),
                        raw_response=row[1] if isinstance(row[1], dict) else {"response": row[1], "replay": True},
                    )
            finally:
                cursor.close()

        return ShipmentCreateResponse(
            carrier_external_id=f"replay-{self._trace_id or 'shipment'}",
            raw_response={"replay": True, "payload": request.payload},
        )

    def get_tracking_status(self, request: ShipmentTrackingStatusRequest) -> ShipmentTrackingStatusResponse:
        if self._db_conn is not None and self._trace_id:
            cursor = self._db_conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT current_status, carrier_metadata
                    FROM shipments
                    WHERE trace_id = %s::uuid
                      AND carrier_external_id = %s
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (self._trace_id, request.carrier_external_id),
                )
                row = cursor.fetchone()
                if row:
                    return ShipmentTrackingStatusResponse(
                        carrier_external_id=request.carrier_external_id,
                        carrier_status=str(row[0] or "unknown"),
                        raw_response=row[1] if isinstance(row[1], dict) else {"response": row[1], "replay": True},
                    )
            finally:
                cursor.close()

        return ShipmentTrackingStatusResponse(
            carrier_external_id=request.carrier_external_id,
            carrier_status="unknown",
            raw_response={"replay": True},
        )


class ReplayOrderSourceAdapter(OrderSourcePort):
    def set_order_custom_field(self, external_order_id: str, field_handle: str, value: str) -> None:
        return None

    def set_order_financial_status(self, external_order_id: str, status: str) -> None:
        return None


def _assert_replay_isolation() -> None:
    cfg = get_config()
    issues = []
    if not cfg.replay_tbank_api_token:
        issues.append("REPLAY_TBANK_API_TOKEN is empty")
    if not cfg.replay_cdek_api_token:
        issues.append("REPLAY_CDEK_API_TOKEN is empty")
    if not cfg.replay_insales_api_user:
        issues.append("REPLAY_INSALES_API_USER is empty")
    if not cfg.replay_insales_api_password:
        issues.append("REPLAY_INSALES_API_PASSWORD is empty")
    if cfg.replay_tbank_api_token and cfg.replay_tbank_api_token == cfg.tbank_api_token:
        issues.append("REPLAY_TBANK_API_TOKEN must differ from LIVE token")
    if cfg.replay_cdek_api_token and cfg.replay_cdek_api_token == cfg.cdek_api_token:
        issues.append("REPLAY_CDEK_API_TOKEN must differ from LIVE token")
    if cfg.replay_insales_api_user and cfg.replay_insales_api_user == (cfg.insales_api_user or ""):
        issues.append("REPLAY_INSALES_API_USER must differ from LIVE user")
    if cfg.replay_insales_api_password and cfg.replay_insales_api_password == (cfg.insales_api_password or ""):
        issues.append("REPLAY_INSALES_API_PASSWORD must differ from LIVE password")
    if issues:
        raise RuntimeError("REPLAY_UNSAFE_CREDENTIALS: " + "; ".join(issues))


def get_payment_invoice_adapter(
    *, execution_mode: str, db_conn=None, trace_id: Optional[str] = None
) -> PaymentInvoicePort:
    if execution_mode.upper() == "REPLAY":
        _assert_replay_isolation()
        return ReplayPaymentInvoiceAdapter(db_conn=db_conn, trace_id=trace_id)
    return TBankInvoiceAdapter()


def get_shipment_adapter(
    *, execution_mode: str, db_conn=None, trace_id: Optional[str] = None
) -> ShipmentPort:
    if execution_mode.upper() == "REPLAY":
        _assert_replay_isolation()
        return ReplayShipmentAdapter(db_conn=db_conn, trace_id=trace_id)
    return CDEKShipmentAdapter()


def get_order_source_adapter(*, execution_mode: str) -> OrderSourcePort:
    if execution_mode.upper() == "REPLAY":
        _assert_replay_isolation()
        return ReplayOrderSourceAdapter()
    return InSalesOrderAdapter()


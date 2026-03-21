from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


@dataclass(frozen=True)
class InvoiceCreateRequest:
    invoice_number: str
    due_date: str
    payer_name: str
    payer_inn: str
    items: list[Dict[str, Any]]
    trace_id: Optional[str] = None


@dataclass(frozen=True)
class InvoiceCreateResponse:
    provider_document_id: str
    pdf_url: Optional[str]
    raw_response: Dict[str, Any]


@dataclass(frozen=True)
class InvoiceStatusRequest:
    provider_document_id: str
    trace_id: Optional[str] = None


@dataclass(frozen=True)
class InvoiceStatusResponse:
    provider_document_id: str
    provider_status: str
    raw_response: Dict[str, Any]


class PaymentInvoicePort(Protocol):
    def create_invoice(self, request: InvoiceCreateRequest) -> InvoiceCreateResponse:
        ...

    def get_invoice_status(self, request: InvoiceStatusRequest) -> InvoiceStatusResponse:
        ...


@dataclass(frozen=True)
class ShipmentCreateRequest:
    payload: Dict[str, Any]
    trace_id: Optional[str] = None


@dataclass(frozen=True)
class ShipmentCreateResponse:
    carrier_external_id: str
    raw_response: Dict[str, Any]


@dataclass(frozen=True)
class ShipmentTrackingStatusRequest:
    carrier_external_id: str
    trace_id: Optional[str] = None


@dataclass(frozen=True)
class ShipmentTrackingStatusResponse:
    carrier_external_id: str
    carrier_status: str
    raw_response: Dict[str, Any]


@dataclass(frozen=True)
class WaybillRequest:
    carrier_external_id: str
    trace_id: Optional[str] = None


@dataclass(frozen=True)
class WaybillResponse:
    carrier_external_id: str
    pdf_bytes: bytes
    raw_response: Dict[str, Any]


class ShipmentPort(Protocol):
    def create_shipment(self, request: ShipmentCreateRequest) -> ShipmentCreateResponse:
        ...

    def get_tracking_status(self, request: ShipmentTrackingStatusRequest) -> ShipmentTrackingStatusResponse:
        ...

    def get_waybill(self, request: WaybillRequest) -> WaybillResponse:
        ...


# ---------------------------------------------------------------------------
# EDO (Electronic Document Operator) port — Phase 6.5
# Scaffold only. Adapters: Сберкорус, СБИС. Live wiring deferred.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EDOSendRequest:
    document_type: str          # invoice | waybill | act
    recipient_inn: str
    document_id: str            # internal document reference
    payload: Dict[str, Any]
    trace_id: Optional[str] = None


@dataclass(frozen=True)
class EDOSendResponse:
    edo_document_id: str
    provider: str               # sberkorus | sbis | kontur
    raw_response: Dict[str, Any]


@dataclass(frozen=True)
class EDOStatusRequest:
    edo_document_id: str
    provider: str
    trace_id: Optional[str] = None


@dataclass(frozen=True)
class EDOStatusResponse:
    edo_document_id: str
    provider: str
    provider_status: str
    raw_response: Dict[str, Any]


class EDOPort(Protocol):
    def send_document(self, request: EDOSendRequest) -> EDOSendResponse:
        ...

    def get_document_status(self, request: EDOStatusRequest) -> EDOStatusResponse:
        ...


class OrderSourcePort(Protocol):
    def set_order_custom_field(self, external_order_id: str, field_handle: str, value: str) -> None:
        ...

    def set_order_financial_status(self, external_order_id: str, status: str) -> None:
        ...


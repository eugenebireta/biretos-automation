from __future__ import annotations

from uuid import uuid4

import httpx

from config import get_config
from domain.ports import (
    InvoiceCreateRequest,
    InvoiceCreateResponse,
    InvoiceStatusRequest,
    InvoiceStatusResponse,
    PaymentInvoicePort,
)


class TBankInvoiceAdapter(PaymentInvoicePort):
    def __init__(self) -> None:
        self._config = get_config()
        self._api_url = self._config.tbank_api_url or "https://business.tbank.ru/openapi/api/v1/invoice/send"
        self._token = self._config.tbank_api_token
        self._dry_run = bool(self._config.dry_run_external_apis)

    def create_invoice(self, request: InvoiceCreateRequest) -> InvoiceCreateResponse:
        payload = {
            "invoiceNumber": request.invoice_number,
            "dueDate": request.due_date,
            "payer": {
                "name": request.payer_name,
                "inn": request.payer_inn,
            },
            "items": request.items,
        }
        if self._dry_run:
            invoice_id = str(uuid4())
            pdf_url = f"https://business.tbank.ru/invoices/{invoice_id}.pdf"
            return InvoiceCreateResponse(
                provider_document_id=invoice_id,
                pdf_url=pdf_url,
                raw_response={"invoiceId": invoice_id, "pdfUrl": pdf_url, "dry_run": True, "payload": payload},
            )

        if not self._token:
            raise RuntimeError("TBANK_API_TOKEN is not set")

        headers = {
            "Authorization": f"Bearer {self._token}",
            "X-Request-Id": str(uuid4()),
            "Content-Type": "application/json",
        }
        response = httpx.post(self._api_url, json=payload, headers=headers, timeout=30.0)
        response.raise_for_status()
        body = response.json()
        invoice_id = body.get("invoiceId")
        if not invoice_id:
            raise RuntimeError("T-Bank API response is missing invoiceId")
        return InvoiceCreateResponse(
            provider_document_id=str(invoice_id),
            pdf_url=body.get("pdfUrl"),
            raw_response=body,
        )

    def get_invoice_status(self, request: InvoiceStatusRequest) -> InvoiceStatusResponse:
        api_base = self._config.tbank_api_base
        status_path = self._config.tbank_invoice_status_path or ""
        invoice_id = request.provider_document_id

        if self._dry_run:
            return InvoiceStatusResponse(
                provider_document_id=invoice_id,
                provider_status="unknown",
                raw_response={"dry_run": True, "invoice_id": invoice_id},
            )

        if not api_base or not status_path:
            raise RuntimeError("TBANK_API_BASE and TBANK_INVOICE_STATUS_PATH are required")

        url_template = f"{api_base.rstrip('/')}/{status_path.lstrip('/')}"
        url = url_template.replace("{invoice_id}", invoice_id)
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if request.trace_id:
            headers["X-Trace-Id"] = request.trace_id

        response = httpx.get(url, headers=headers, timeout=10.0)
        response.raise_for_status()
        body = response.json()

        provider_status = "unknown"
        if isinstance(body, dict):
            candidate = body.get("status") or body.get("invoice_status") or body.get("state")
            if candidate is not None:
                provider_status = str(candidate).lower()

        return InvoiceStatusResponse(
            provider_document_id=invoice_id,
            provider_status=provider_status,
            raw_response=body if isinstance(body, dict) else {"response": body},
        )


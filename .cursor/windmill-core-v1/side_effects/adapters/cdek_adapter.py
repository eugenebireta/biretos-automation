from __future__ import annotations

from uuid import uuid4

import httpx

from config import get_config
from domain.ports import (
    ShipmentCreateRequest,
    ShipmentCreateResponse,
    ShipmentPort,
    ShipmentTrackingStatusRequest,
    ShipmentTrackingStatusResponse,
    WaybillRequest,
    WaybillResponse,
)


class CDEKShipmentAdapter(ShipmentPort):
    def __init__(self) -> None:
        self._config = get_config()
        self._api_url = self._config.cdek_api_url or "https://api.cdek.ru/v2/orders"
        self._token = self._config.cdek_api_token or ""
        self._dry_run = bool(self._config.dry_run_external_apis)

    def create_shipment(self, request: ShipmentCreateRequest) -> ShipmentCreateResponse:
        payload = dict(request.payload or {})
        if self._dry_run:
            cdek_uuid = str(uuid4())
            raw = {"entity": {"uuid": cdek_uuid}, "dry_run": True, "payload": payload}
            return ShipmentCreateResponse(carrier_external_id=cdek_uuid, raw_response=raw)

        if not self._token:
            raise RuntimeError("CDEK_API_TOKEN is not set")

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        response = httpx.post(self._api_url, json=payload, headers=headers, timeout=30.0)
        response.raise_for_status()
        body = response.json()
        cdek_uuid = body.get("entity", {}).get("uuid") or body.get("uuid")
        if not cdek_uuid:
            raise RuntimeError("CDEK response missing uuid")
        return ShipmentCreateResponse(carrier_external_id=str(cdek_uuid), raw_response=body)

    def get_tracking_status(self, request: ShipmentTrackingStatusRequest) -> ShipmentTrackingStatusResponse:
        carrier_external_id = request.carrier_external_id

        if self._dry_run:
            return ShipmentTrackingStatusResponse(
                carrier_external_id=carrier_external_id,
                carrier_status="created",
                raw_response={"dry_run": True, "carrier_external_id": carrier_external_id},
            )

        if not self._token:
            raise RuntimeError("CDEK_API_TOKEN is not set")

        url = f"{self._api_url.rstrip('/')}/{carrier_external_id}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        if request.trace_id:
            headers["X-Trace-Id"] = request.trace_id

        response = httpx.get(url, headers=headers, timeout=10.0)
        response.raise_for_status()
        body = response.json()

        candidate = None
        if isinstance(body, dict):
            candidate = (
                body.get("status")
                or body.get("state")
                or body.get("entity", {}).get("status")
            )
        carrier_status = str(candidate).lower() if candidate is not None else "unknown"

        return ShipmentTrackingStatusResponse(
            carrier_external_id=carrier_external_id,
            carrier_status=carrier_status,
            raw_response=body if isinstance(body, dict) else {"response": body},
        )

    def get_waybill(self, request: WaybillRequest) -> WaybillResponse:
        """
        Phase 6.6 — Download CDEK waybill (barcode sticker) as PDF.

        CDEK v2 API: GET /v2/orders/{uuid}/barcode
        Returns PDF bytes. dry_run returns stub bytes.
        """
        carrier_external_id = request.carrier_external_id

        if self._dry_run:
            stub_bytes = b"%PDF-1.4 DRY-RUN-WAYBILL"
            return WaybillResponse(
                carrier_external_id=carrier_external_id,
                pdf_bytes=stub_bytes,
                raw_response={"dry_run": True, "carrier_external_id": carrier_external_id},
            )

        if not self._token:
            raise RuntimeError("CDEK_API_TOKEN is not set")

        base = self._api_url.rstrip("/").rsplit("/orders", 1)[0]
        url = f"{base}/orders/{carrier_external_id}/barcode"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/pdf",
        }
        if request.trace_id:
            headers["X-Trace-Id"] = request.trace_id

        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "pdf" not in content_type and len(response.content) < 4:
            raise RuntimeError(
                f"CDEK waybill response is not a PDF: content-type={content_type!r}"
            )

        return WaybillResponse(
            carrier_external_id=carrier_external_id,
            pdf_bytes=response.content,
            raw_response={"content_type": content_type, "size_bytes": len(response.content)},
        )


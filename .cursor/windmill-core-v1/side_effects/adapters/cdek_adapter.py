from __future__ import annotations

import os
import re
import time
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
    _cached_token: str = ""
    _token_expires_at: float = 0.0

    def __init__(self) -> None:
        self._config = get_config()
        self._api_url = self._config.cdek_api_url or "https://api.cdek.ru/v2/orders"
        self._token = self._config.cdek_api_token or ""
        self._dry_run = bool(self._config.dry_run_external_apis)

    def _get_auth_token(self) -> str:
        static_token = getattr(self, "_token", "") or ""
        if static_token:
            return static_token

        cls = self.__class__
        if cls._cached_token and time.time() < cls._token_expires_at - 60:
            return cls._cached_token

        client_id = getattr(self._config, "cdek_client_id", None) or os.environ.get("CDEK_CLIENT_ID", "")
        client_secret = getattr(self._config, "cdek_client_secret", None) or os.environ.get("CDEK_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            raise RuntimeError("CDEK credentials are not set")

        response = httpx.post(
            "https://api.cdek.ru/v2/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        body = response.json()

        access_token = str(body.get("access_token") or "")
        if not access_token:
            raise RuntimeError("CDEK OAuth token response missing access_token")

        try:
            expires_in = int(body.get("expires_in", 3600))
        except (TypeError, ValueError):
            expires_in = 3600

        cls._cached_token = access_token
        cls._token_expires_at = time.time() + max(expires_in, 60)
        return access_token

    def create_shipment(self, request: ShipmentCreateRequest) -> ShipmentCreateResponse:
        payload = dict(request.payload or {})
        if self._dry_run:
            cdek_uuid = str(uuid4())
            raw = {"entity": {"uuid": cdek_uuid}, "dry_run": True, "payload": payload}
            return ShipmentCreateResponse(carrier_external_id=cdek_uuid, raw_response=raw)

        token = self._get_auth_token()

        headers = {
            "Authorization": f"Bearer {token}",
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

        token = self._get_auth_token()

        base = self._api_url.rstrip("/").rsplit("/orders", 1)[0]
        url = f"{base}/orders?cdek_number={carrier_external_id}"
        headers = {
            "Authorization": f"Bearer {token}",
        }
        if request.trace_id:
            headers["X-Trace-Id"] = request.trace_id

        response = httpx.get(url, headers=headers, timeout=10.0)

        if response.status_code == 400:
            body = response.json() if "json" in response.headers.get("content-type", "") else {}
            return ShipmentTrackingStatusResponse(
                carrier_external_id=carrier_external_id,
                carrier_status="not_found",
                raw_response=body if isinstance(body, dict) else {"response": str(body)},
            )

        response.raise_for_status()
        body = response.json()

        entity = body.get("entity", {}) if isinstance(body, dict) else {}
        statuses = entity.get("statuses", [])
        if statuses:
            carrier_status = str(statuses[-1].get("code", "unknown")).lower()
        else:
            candidate = entity.get("status") or body.get("status") or body.get("state")
            carrier_status = str(candidate).lower() if candidate is not None else "unknown"

        return ShipmentTrackingStatusResponse(
            carrier_external_id=carrier_external_id,
            carrier_status=carrier_status,
            raw_response=body if isinstance(body, dict) else {"response": body},
        )

    def _resolve_order_uuid(self, carrier_external_id: str, trace_id: str | None = None) -> str:
        """
        Resolve a CDEK tracking number (cdek_number) to an order UUID.

        If carrier_external_id already looks like a UUID, return it as-is.
        Otherwise GET /v2/orders?cdek_number=X and extract entity.uuid.
        """
        # Already a UUID?
        if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-", carrier_external_id, re.I):
            return carrier_external_id

        base = self._api_url.rstrip("/").rsplit("/orders", 1)[0]
        url = f"{base}/orders?cdek_number={carrier_external_id}"
        headers = {"Authorization": f"Bearer {self._get_auth_token()}"}
        if trace_id:
            headers["X-Trace-Id"] = trace_id

        resp = httpx.get(url, headers=headers, timeout=10.0)
        if resp.status_code == 400:
            raise RuntimeError(f"CDEK order not found for tracking number {carrier_external_id}")
        resp.raise_for_status()

        body = resp.json()
        order_uuid = (body.get("entity") or {}).get("uuid") if isinstance(body, dict) else None
        if not order_uuid:
            raise RuntimeError(
                f"CDEK returned no order UUID for tracking number {carrier_external_id}"
            )
        return str(order_uuid)

    def get_waybill(self, request: WaybillRequest) -> WaybillResponse:
        """
        Phase 6.6 — Download CDEK barcode sticker as PDF.

        CDEK v2 API (3-step):
          1. Resolve tracking number → order UUID
          2. POST /v2/print/barcodes  → print task UUID
          3. GET  /v2/print/barcodes/{task_uuid} → PDF bytes

        dry_run returns stub bytes.
        """
        carrier_external_id = request.carrier_external_id

        if self._dry_run:
            stub_bytes = b"%PDF-1.4 DRY-RUN-WAYBILL"
            return WaybillResponse(
                carrier_external_id=carrier_external_id,
                pdf_bytes=stub_bytes,
                raw_response={"dry_run": True, "carrier_external_id": carrier_external_id},
            )

        token = self._get_auth_token()

        base = self._api_url.rstrip("/").rsplit("/orders", 1)[0]
        auth_headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
        if request.trace_id:
            auth_headers["X-Trace-Id"] = request.trace_id

        # Step 1: tracking number → order UUID
        order_uuid = self._resolve_order_uuid(carrier_external_id, request.trace_id)

        # Step 2: create print task
        print_url = f"{base}/print/barcodes"
        print_body = {
            "orders": [{"order_uuid": order_uuid}],
            "copy_count": 1,
        }
        print_resp = httpx.post(
            print_url,
            json=print_body,
            headers={**auth_headers, "Content-Type": "application/json"},
            timeout=15.0,
        )
        print_resp.raise_for_status()

        print_data = print_resp.json()
        task_uuid = (print_data.get("entity") or {}).get("uuid")
        if not task_uuid:
            raise RuntimeError("CDEK print/barcodes did not return a task UUID")

        # Step 3: poll task status until READY, then download from entity.url
        # CDEK flow: GET /print/barcodes/{uuid} returns JSON with statuses.
        # When status is READY, entity.url contains the .pdf download link.
        status_url = f"{base}/print/barcodes/{task_uuid}"
        pdf_url: str | None = None

        for _attempt in range(10):
            time.sleep(3)
            st_resp = httpx.get(status_url, headers=auth_headers, timeout=15.0)

            # 406/202 = task still processing
            if st_resp.status_code in (406, 202):
                continue

            st_resp.raise_for_status()
            ct = st_resp.headers.get("content-type", "")

            # If CDEK returns PDF directly (unlikely but handle it)
            if "pdf" in ct or st_resp.content[:5] == b"%PDF-":
                return WaybillResponse(
                    carrier_external_id=carrier_external_id,
                    pdf_bytes=st_resp.content,
                    raw_response={
                        "content_type": ct,
                        "size_bytes": len(st_resp.content),
                        "order_uuid": order_uuid,
                        "print_task_uuid": str(task_uuid),
                    },
                )

            # Parse JSON status response
            try:
                st_body = st_resp.json()
            except Exception:
                continue

            entity = st_body.get("entity") or {}
            statuses = entity.get("statuses", [])
            last_code = statuses[-1].get("code", "").upper() if statuses else ""

            if last_code == "READY":
                pdf_url = entity.get("url")
                break
            elif last_code in ("FAILED", "INVALID"):
                raise RuntimeError(
                    f"CDEK print task {task_uuid} failed with status {last_code}"
                )
            # Still processing (ACCEPTED, etc.) — continue polling

        if not pdf_url:
            raise RuntimeError(
                f"CDEK print task {task_uuid} did not become READY within timeout"
            )

        # Step 4: download actual PDF from entity.url
        pdf_resp = httpx.get(pdf_url, headers=auth_headers, timeout=30.0)
        pdf_resp.raise_for_status()
        content_type = pdf_resp.headers.get("content-type", "")
        pdf_bytes: bytes | None = pdf_resp.content

        if not pdf_bytes or (pdf_bytes[:5] != b"%PDF-" and "pdf" not in content_type):
            raise RuntimeError(
                f"CDEK PDF download returned non-PDF: content-type={content_type!r}, "
                f"size={len(pdf_bytes)}"
            )

        return WaybillResponse(
            carrier_external_id=carrier_external_id,
            pdf_bytes=pdf_bytes,
            raw_response={
                "content_type": content_type,
                "size_bytes": len(pdf_bytes),
                "order_uuid": order_uuid,
                "print_task_uuid": str(task_uuid),
            },
        )


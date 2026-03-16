from __future__ import annotations

import logging
import os
import uuid
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests
from requests import RequestException, Session

from config.schema import Config


class ShopwareApiError(Exception):
    pass


class ShopwareApiClient:
    def __init__(self, config: Config, logger: logging.Logger) -> None:
        self._config = config
        self._logger = logger
        self._session: Session = requests.Session()
        self._token: Optional[str] = None
        self._token_expiry_ts: float = 0.0
        self._base_url = (self._config.shopware_url or "").rstrip("/")

    def _ensure_token(self) -> None:
        now = time.time()
        if self._token and now < (self._token_expiry_ts - 60):
            return

        if not self._base_url:
            raise ShopwareApiError("SHOPWARE_URL is empty")

        token_url = f"{self._base_url}/api/oauth/token"
        try:
            response = self._session.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._config.shopware_client_id,
                    "client_secret": self._config.shopware_client_secret,
                },
                timeout=self._config.shopware_timeout_seconds,
            )
        except RequestException as exc:
            raise ShopwareApiError(f"Shopware auth network error: {exc}") from exc

        if response.status_code >= 400:
            raise ShopwareApiError(
                f"Shopware auth failed: {response.status_code} {response.text.strip()}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ShopwareApiError("Shopware auth response is not JSON") from exc

        access_token = payload.get("access_token")
        if not access_token:
            raise ShopwareApiError("Shopware auth response missing access_token")

        expires_in = payload.get("expires_in", 600)
        try:
            expires_in_float = float(expires_in)
        except (TypeError, ValueError):
            expires_in_float = 600.0

        self._token = str(access_token)
        self._token_expiry_ts = now + expires_in_float

    def _request(self, method: str, path: str, json: Optional[Any] = None) -> Dict[str, Any]:
        self._ensure_token()

        if not path.startswith("/"):
            path = f"/{path}"

        url = f"{self._base_url}{path}"
        retriable_statuses = {429, 502, 503, 504}
        backoff_schedule = [1, 2, 4]
        attempts = len(backoff_schedule)
        headers = {"Authorization": f"Bearer {self._token}"}

        for attempt_idx in range(attempts):
            try:
                response = self._session.request(
                    method=method,
                    url=url,
                    json=json,
                    headers=headers,
                    timeout=self._config.shopware_timeout_seconds,
                )
            except RequestException as exc:
                if attempt_idx < (attempts - 1):
                    time.sleep(backoff_schedule[attempt_idx])
                    continue
                raise ShopwareApiError(f"Shopware network error: {exc}") from exc

            if response.status_code < 400:
                if not response.text:
                    return {}
                try:
                    return response.json()
                except ValueError:
                    return {"raw": response.text}

            status = response.status_code
            should_retry = status in retriable_statuses and attempt_idx < (attempts - 1)
            if should_retry:
                time.sleep(backoff_schedule[attempt_idx])
                continue

            raise ShopwareApiError(
                f"Shopware API request failed: {method} {path} -> {status} {response.text.strip()}"
            )

        raise ShopwareApiError(f"Shopware API request failed: {method} {path}")

    def upsert_product(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._config.shopware_enable_dry_run:
            self._logger.info(
                "DRY_RUN shopware upsert",
                extra={"product_number": payload.get("productNumber"), "path": "/api/_action/sync"},
            )
            return {"dry_run": True}

        sync_payload = [
            {
                "action": "upsert",
                "entity": "product",
                "payload": [payload],
            }
        ]
        return self._request("POST", "/api/_action/sync", json=sync_payload)

    def ensure_media_for_url(self, media_url: str) -> str:
        media_url = (media_url or "").strip()
        if not media_url:
            raise ShopwareApiError("media_url must be non-empty")

        if self._config.shopware_enable_dry_run:
            return uuid.uuid5(uuid.NAMESPACE_URL, media_url).hex

        media_id = uuid.uuid4().hex
        sync_payload = [
            {
                "action": "upsert",
                "entity": "media",
                "payload": [{"id": media_id}],
            }
        ]
        self._request("POST", "/api/_action/sync", json=sync_payload)

        parsed = urlparse(media_url)
        path = parsed.path or ""
        basename = os.path.basename(path) or "remote_media"
        file_name, extension = os.path.splitext(basename)
        extension = (extension or ".jpg").lstrip(".").lower() or "jpg"
        file_name = file_name or "remote_media"

        upload_path = (
            f"/api/_action/media/{media_id}/upload"
            f"?extension={extension}&fileName={file_name}"
        )
        self._request("POST", upload_path, json={"url": media_url})
        return media_id

    def find_product_by_number(self, product_number: str) -> Optional[str]:
        search_payload = {
            "filter": [{"field": "productNumber", "type": "equals", "value": product_number}],
            "limit": 1,
            "includes": {"product": ["id"]},
        }
        response = self._request("POST", "/api/search/product", json=search_payload)
        data = response.get("data")
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                product_id = first.get("id")
                if isinstance(product_id, str) and product_id:
                    return product_id
        return None

    def find_order_by_number(self, order_number: str) -> Optional[str]:
        search_payload = {
            "filter": [{"field": "orderNumber", "type": "equals", "value": order_number}],
            "limit": 1,
            "includes": {"order": ["id"]},
        }
        response = self._request("POST", "/api/search/order", json=search_payload)
        data = response.get("data")
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                order_id = first.get("id")
                if isinstance(order_id, str) and order_id:
                    return order_id
        return None

    def sync_order_state(self, *, order_number: str, target_core_state: str) -> Dict[str, Any]:
        if self._config.shopware_enable_dry_run:
            self._logger.info(
                "DRY_RUN shopware order state sync",
                extra={"order_number": order_number, "target_core_state": target_core_state},
            )
            return {"dry_run": True}

        order_id = self.find_order_by_number(order_number)
        if not order_id:
            raise ShopwareApiError(f"Order not found in Shopware: {order_number}")

        sync_payload = [
            {
                "action": "upsert",
                "entity": "order",
                "payload": [
                    {
                        "id": order_id,
                        "customFields": {"coreOrderState": target_core_state},
                    }
                ],
            }
        ]
        return self._request("POST", "/api/_action/sync", json=sync_payload)

    def close(self) -> None:
        self._session.close()

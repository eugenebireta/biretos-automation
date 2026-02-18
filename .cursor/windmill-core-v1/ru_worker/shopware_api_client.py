from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

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

    def close(self) -> None:
        self._session.close()

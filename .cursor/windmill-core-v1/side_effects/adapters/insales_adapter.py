from __future__ import annotations

from typing import Any, Dict

import httpx

from config import get_config
from domain.ports import OrderSourcePort


class InSalesOrderAdapter(OrderSourcePort):
    def __init__(self) -> None:
        self._config = get_config()
        self._shop = self._config.insales_shop or "bireta.myinsales.ru"
        self._user = self._config.insales_api_user or ""
        self._password = self._config.insales_api_password or ""
        self._dry_run = bool(self._config.dry_run_external_apis)

    def set_order_custom_field(self, external_order_id: str, field_handle: str, value: str) -> None:
        url = f"https://api.insales.ru/admin/orders/{external_order_id}.json"
        payload = {
            "order": {
                "fields_values_attributes": [
                    {"handle": field_handle, "value": value},
                ]
            }
        }
        self._send(url, payload)

    def set_order_financial_status(self, external_order_id: str, status: str) -> None:
        url = f"https://{self._shop}/admin/orders/{external_order_id}.json"
        payload = {"order": {"financial_status": status}}
        self._send(url, payload)

    def _send(self, url: str, payload: Dict[str, Any]) -> None:
        if self._dry_run:
            return
        if not (self._user and self._password):
            raise RuntimeError("InSales credentials are required")
        response = httpx.put(
            url,
            json=payload,
            auth=(self._user, self._password),
            headers={"Content-Type": "application/json"},
            timeout=10.0,
        )
        response.raise_for_status()


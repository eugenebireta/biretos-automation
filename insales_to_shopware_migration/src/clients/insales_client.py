from __future__ import annotations

import logging
import os
from dataclasses import dataclass
import time
from typing import Any, Dict, Iterable, List, Optional

import requests
from requests.auth import HTTPBasicAuth


LOG = logging.getLogger(__name__)

# Флаг для режима SNAPSHOT-only (отключение InSales API)
_SNAPSHOT_MODE = os.getenv("INSALES_SOURCE", "snapshot").lower() == "snapshot"


class InsalesClientError(RuntimeError):
    """Базовое исключение клиента Insales."""
    
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class InsalesConfig:
    host: str
    api_key: str
    api_password: str
    scheme: str = "https"

    @property
    def base_url(self) -> str:
        clean_host = self.host.strip()
        return f"{self.scheme}://{clean_host}".rstrip("/")


class InsalesClient:
    """Минимальный HTTP-клиент для Insales REST API."""

    def __init__(self, config: InsalesConfig, *, timeout: int = 30) -> None:
        if _SNAPSHOT_MODE:
            raise RuntimeError(
                "InSales API отключён в режиме SNAPSHOT. "
                "Используйте локальные файлы из insales_snapshot/ для импорта. "
                "Чтобы включить API, установите INSALES_SOURCE=api"
            )
        self._config = config
        self._timeout = timeout
        self._session = requests.Session()
        self._session.auth = HTTPBasicAuth(config.api_key, config.api_password)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._config.base_url}{path}"
        LOG.debug("Insales %s %s", method, url)
        resp = self._session.request(method, url, timeout=self._timeout, **kwargs)
        if resp.status_code >= 400:
            raise InsalesClientError(
                f"Insales API error {resp.status_code}: {resp.text.strip()}",
                status_code=resp.status_code
            )
        if not resp.text:
            return None
        return resp.json()

    def get_collections(self, *, page: int = 1, per_page: int = 250) -> List[Dict[str, Any]]:
        params = {"page": page, "per_page": per_page}
        data = self._request("GET", "/admin/collections.json", params=params)
        return data or []

    def get_option_names(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/admin/option_names.json")
        return data or []

    def get_properties(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/admin/properties.json")
        return data or []

    def get_products(self, *, page: int = 1, per_page: int = 250) -> List[Dict[str, Any]]:
        params = {"page": page, "per_page": per_page}
        data = self._request("GET", "/admin/products.json", params=params)
        if isinstance(data, dict) and "products" in data:
            return data["products"]
        return data or []

    def iter_products(self, *, per_page: int = 250) -> Iterable[Dict[str, Any]]:
        page = 1
        while True:
            chunk = self.get_products(page=page, per_page=per_page)
            if not chunk:
                break
            for product in chunk:
                yield product
            if len(chunk) < per_page:
                break
            page += 1

    def get_products_count(self) -> Optional[int]:
        data = self._request("GET", "/admin/products/count.json")
        if isinstance(data, dict):
            return data.get("count")
        return None

    def fetch_all(self, endpoint: str, per_page: int = 250) -> List[Dict[str, Any]]:
        """
        Универсальный метод для выгрузки всех страниц указанного ресурса.
        endpoint: путь без префикса /admin и без .json (например, '/products')
        """
        results: List[Dict[str, Any]] = []
        page = 1
        while True:
            time.sleep(0.3)  # страховка от rate limit
            try:
                path = endpoint if endpoint.endswith(".json") else f"{endpoint}.json"
                chunk = self._request(
                    "GET",
                    f"/admin{path}",
                    params={"page": page, "per_page": per_page},
                )
                if not chunk:
                    break

                # API может возвращать словарь вида {"products": [...]}
                if isinstance(chunk, dict):
                    # берем первое значение-список
                    lists = [value for value in chunk.values() if isinstance(value, list)]
                    data_part = lists[0] if lists else []
                else:
                    data_part = chunk

                if not data_part:
                    break

                results.extend(data_part)
                print(f"[Insales] {endpoint} page {page}: {len(data_part)} items")

                if len(data_part) < per_page:
                    break
                page += 1
            except Exception as exc:
                print(f"[WARN] fetch_all error {endpoint} page {page}: {exc}")
                break
        return results


__all__ = [
    "InsalesClient",
    "InsalesClientError",
    "InsalesConfig",
]


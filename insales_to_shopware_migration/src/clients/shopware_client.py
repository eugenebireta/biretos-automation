from __future__ import annotations

import csv
import logging
import time
import urllib3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Union

import requests

# Отключаем предупреждения о небезопасных SSL соединениях
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


LOG = logging.getLogger(__name__)


class ShopwareClientError(RuntimeError):
    """Базовое исключение клиента Shopware API."""


@dataclass(frozen=True)
class ShopwareConfig:
    url: str
    access_key_id: str
    secret_access_key: str

    @property
    def api_base(self) -> str:
        return self.url.rstrip("/")


class ShopwareClient:
    """Минимальный OAuth2 клиент для Shopware 6 API."""

    def __init__(self, config: ShopwareConfig, *, timeout: int = 10) -> None:
        self._config = config
        self._timeout = timeout  # По умолчанию 10 секунд для быстрой работы
        self._session = requests.Session()
        self._token: Optional[str] = None
        self._token_expiry: float = 0
        self._default_tax_id: Optional[str] = None
        self._currency_cache: Dict[str, str] = {}
        self._system_currency_id: Optional[str] = None
        self._system_language_id: Optional[str] = None
        # Заголовок для валюты по умолчанию (будет установлен после получения системной валюты)
        self._default_currency_header: Optional[str] = None
        # Кэш для папки Product Media и её конфигурации
        self._product_media_folder_id: Optional[str] = None
        self._product_media_config_id: Optional[str] = None
        # Кэш для custom field штрих-кода
        self._barcode_custom_field_created: bool = False
        # Кэши для нормализованного поиска (защита от дублей)
        self._manufacturers_cache: Dict[str, str] = {}  # normalized_name -> id
        self._price_rules_cache: Dict[str, str] = {}  # normalized_name -> id
        self._standard_tax_id: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _ensure_token(self) -> None:
        now = time.time()
        if self._token and now < (self._token_expiry - 60):
            return
        data = {
            "grant_type": "client_credentials",
            "client_id": self._config.access_key_id,
            "client_secret": self._config.secret_access_key,
        }
        url = f"{self._config.api_base}/api/oauth/token"
        resp = requests.post(url, data=data, timeout=self._timeout, verify=False)
        # Используем прямой вызов requests, чтобы избежать конфликтов
        if resp.status_code >= 400:
            raise ShopwareClientError(
                f"Shopware auth error {resp.status_code}: {resp.text.strip()}"
            )
        payload = resp.json()
        self._token = payload.get("access_token")
        expires_in = payload.get("expires_in", 600)
        self._token_expiry = now + float(expires_in)
        self._session.headers.update({"Authorization": f"Bearer {self._token}"})

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        self._ensure_token()
        url = f"{self._config.api_base}{path}"
        # Логируем каждый API вызов
        LOG.info(f"[Shopware API] {method} {url}")
        # Отключаем проверку SSL для тестового подключения по IP
        if "verify" not in kwargs:
            kwargs["verify"] = False
        
        # Используем timeout из конфигурации клиента (убеждаемся что не передаётся дважды)
        kwargs["timeout"] = self._timeout
        
        # Добавляем заголовок для системной валюты для операций с продуктами
        if path.startswith("/api/product") or path.startswith("/api/_action/sync"):
            if self._default_currency_header is None:
                # Приоритет: валюта из Sales Channel (там установлен RUB)
                sales_channel_currency = self.get_sales_channel_currency_id()
                if sales_channel_currency:
                    self._default_currency_header = sales_channel_currency
                    print(f"DEBUG: Using Sales Channel currency for header: {sales_channel_currency}")
                else:
                    # Если не найдена в Sales Channel, пробуем найти RUB по ISO коду
                    try:
                        rub_id = self.get_currency_id("RUB")
                        self._default_currency_header = rub_id
                        print(f"DEBUG: Using RUB currency (by ISO) for header: {rub_id}")
                    except Exception:
                        # Если RUB не найдена, используем системную валюту
                        self._default_currency_header = self.get_system_currency_id()
                        print(f"DEBUG: Using system currency for header: {self._default_currency_header}")
            # Устанавливаем заголовок для контекста валюты
            headers = kwargs.get("headers", {})
            if headers is None:
                headers = {}
            headers["sw-currency-id"] = self._default_currency_header
            # Также добавляем sw-language-id для контекста
            if "sw-language-id" not in headers:
                headers["sw-language-id"] = self.get_system_language_id()
            kwargs["headers"] = headers
        
        # timeout уже установлен в kwargs выше
        resp = self._session.request(method, url, **kwargs)
        if resp.status_code >= 400:
            raise ShopwareClientError(
                f"Shopware API error {resp.status_code}: {resp.text.strip()}"
            )
        if not resp.text:
            return None
        content_type = resp.headers.get("Content-Type", "").lower()
        if "json" in content_type:
            return resp.json()
        return resp.text

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def create_category(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/category", json=payload)

    def get_category(self, category_id: str) -> Optional[Dict[str, Any]]:
        """Получает категорию по ID из Shopware."""
        try:
            response = self._request("GET", f"/api/category/{category_id}")
            if isinstance(response, dict) and "data" in response:
                return response["data"]
            return response
        except Exception:
            return None

    def update_category(self, category_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self._request("PATCH", f"/api/category/{category_id}", json=payload)

    def search_seo_urls(
        self,
        foreign_key: Optional[str] = None,
        route_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Поиск SEO URLs."""
        filters = []
        if foreign_key:
            filters.append({"field": "foreignKey", "type": "equals", "value": foreign_key})
        if route_name:
            filters.append({"field": "routeName", "type": "equals", "value": route_name})
        
        response = self._request(
            "POST",
            "/api/search/seo-url",
            json={
                "filter": filters,
                "limit": limit,
                "includes": {"seo_url": ["id", "seoPathInfo", "foreignKey", "salesChannelId", "isCanonical"]},
            },
        )
        if isinstance(response, dict) and "data" in response:
            return response["data"]
        return []

    def delete_seo_url(self, seo_url_id: str) -> bool:
        """Удаляет SEO URL по ID."""
        try:
            self._request("DELETE", f"/api/seo-url/{seo_url_id}")
            return True
        except Exception:
            return False

    def get_sales_channel(self, sales_channel_id: str) -> Optional[Dict[str, Any]]:
        """Получает Sales Channel по ID."""
        try:
            response = self._request("GET", f"/api/sales-channel/{sales_channel_id}")
            if isinstance(response, dict) and "data" in response:
                return response["data"]
            return response
        except Exception:
            return None

    def update_sales_channel(self, sales_channel_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        """Обновляет Sales Channel."""
        return self._request("PATCH", f"/api/sales-channel/{sales_channel_id}", json=payload)

    def create_property_group(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/property-group", json=payload)

    def find_property_group_by_name(self, name: str) -> Optional[str]:
        response = self._request(
            "POST",
            "/api/search/property-group",
            json={
                "filter": [{"field": "name", "type": "equals", "value": name}],
                "limit": 1,
                "includes": {"property_group": ["id"]},
            },
        )
        if response.get("total"):
            return response["data"][0]["id"]
        return None

    def create_property_option(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/property-group-option", json=payload)

    def find_property_option_id(self, group_id: str, name: str) -> Optional[str]:
        response = self._request(
            "POST",
            "/api/search/property-group-option",
            json={
                "filter": [
                    {"field": "groupId", "type": "equals", "value": group_id},
                    {"field": "name", "type": "equals", "value": name},
                ],
                "limit": 1,
                "includes": {"property_group_option": ["id"]},
            },
        )
        if response.get("total"):
            return response["data"][0]["id"]
        return None
    
    def get_product_properties(self, product_id: str) -> List[str]:
        """
        Получает список property_option_ids текущих properties товара.
        
        Args:
            product_id: ID товара
        
        Returns:
            Список property_option_ids
        """
        try:
            # Используем Search API с associations для получения properties
            response = self._request(
                "POST",
                "/api/search/product",
                json={
                    "filter": [{"field": "id", "type": "equals", "value": product_id}],
                    "limit": 1,
                    "associations": {
                        "properties": {}
                    }
                }
            )
            
            if isinstance(response, dict):
                data_list = response.get("data", [])
                if data_list:
                    product_data = data_list[0]
                    # Проверяем relationships для properties
                    relationships = product_data.get("relationships", {})
                    properties_rel = relationships.get("properties", {})
                    if properties_rel:
                        # Получаем IDs из relationships.data
                        properties_data = properties_rel.get("data", [])
                        property_ids = [prop.get("id") for prop in properties_data if prop.get("id")]
                        if property_ids:
                            return property_ids
                    
                    # Альтернативный способ: через included
                    included = response.get("included", [])
                    if included:
                        property_ids = []
                        for item in included:
                            if item.get("type") == "property_group_option":
                                prop_id = item.get("id")
                                if prop_id:
                                    property_ids.append(prop_id)
                        if property_ids:
                            return property_ids
                    
                    # Альтернативный способ: через прямой GET
                    try:
                        direct_response = self._request("GET", f"/api/product/{product_id}?associations[properties]=true")
                        if isinstance(direct_response, dict):
                            data = direct_response.get("data", {})
                            if isinstance(data, dict):
                                relationships = data.get("relationships", {})
                                properties_rel = relationships.get("properties", {})
                                if properties_rel:
                                    properties_data = properties_rel.get("data", [])
                                    property_ids = [prop.get("id") for prop in properties_data if prop.get("id")]
                                    if property_ids:
                                        return property_ids
                    except Exception:
                        pass
            
            return []
        except Exception as e:
            LOG.error(f"[Product Properties] Ошибка получения properties для товара {product_id}: {e}")
            return []
    
    def delete_product_properties(self, product_id: str) -> bool:
        """
        Удаляет все существующие product-property связи для товара.
        
        В Shopware 6.7 properties работают по append-модели при PATCH.
        Для полной замены необходимо сначала удалить старые связи.
        
        Метод: PATCH с пустым массивом properties удаляет все существующие связи.
        После PATCH выполняется валидация: повторный GET для проверки, что properties пустые.
        
        Args:
            product_id: ID товара
        
        Returns:
            True при успехе (properties пустые), False при ошибке или если properties не удалены
        """
        max_attempts = 2
        
        for attempt in range(1, max_attempts + 1):
            try:
                # В Shopware 6.7 удаление всех properties выполняется через PATCH с пустым массивом
                # Это заменяет все существующие properties на пустой список
                self._request("PATCH", f"/api/product/{product_id}", json={"properties": []})
                
                # ВАЛИДАЦИЯ: Проверяем, что properties действительно удалены
                import time
                time.sleep(0.2)  # Небольшая задержка для применения изменений
                
                remaining_properties = self.get_product_properties(product_id)
                
                if not remaining_properties:
                    # Properties успешно удалены
                    LOG.info(f"[Product Properties] Удалены все properties для товара {product_id} (попытка {attempt})")
                    return True
                else:
                    # Properties не удалены, пробуем еще раз
                    if attempt < max_attempts:
                        LOG.warning(
                            f"[Product Properties] Properties не удалены для товара {product_id} после попытки {attempt}. "
                            f"Осталось {len(remaining_properties)} properties. Повторная попытка..."
                        )
                        continue
                    else:
                        # Все попытки исчерпаны
                        LOG.error(
                            f"[Product Properties] ERROR: Не удалось удалить properties для товара {product_id} после {max_attempts} попыток. "
                            f"Осталось {len(remaining_properties)} properties: {remaining_properties}"
                        )
                        return False
                        
            except Exception as e:
                if attempt < max_attempts:
                    LOG.warning(f"[Product Properties] Ошибка при удалении properties для товара {product_id} (попытка {attempt}): {e}. Повторная попытка...")
                    continue
                else:
                    LOG.error(f"[Product Properties] ERROR: Не удалось удалить properties для товара {product_id} после {max_attempts} попыток: {e}")
                    return False
        
        return False
    
    def update_product_properties(
        self,
        product_id: str,
        property_option_ids: List[str]
    ) -> bool:
        """
        Обновляет properties товара через DELETE старых + PATCH новых.
        
        В Shopware 6.7 properties работают по append-модели при PATCH.
        Для полной замены необходимо сначала удалить старые связи.
        
        После каждого шага выполняется валидация для гарантии детерминированности.
        
        Args:
            product_id: ID товара
            property_option_ids: Список property_option_ids для установки
        
        Returns:
            True при успехе, False при ошибке
        """
        try:
            # ЗАЩИТА ОТ РЕГРЕССИИ: Проверяем формат property_option_ids
            if not all(isinstance(pid, str) and pid for pid in property_option_ids):
                raise ValueError(
                    "[REGRESSION GUARD] property_option_ids must be non-empty strings. "
                    f"Получено: {property_option_ids}"
                )
            
            # ШАГ 1: Удаляем старые properties
            if not self.delete_product_properties(product_id):
                LOG.error(f"[Product Properties] ERROR: Не удалось удалить старые properties для товара {product_id}. Прерываем обновление.")
                return False
            
            # ВАЛИДАЦИЯ ШАГ 1: Проверяем, что properties действительно пустые
            import time
            time.sleep(0.2)  # Небольшая задержка для применения изменений
            remaining_properties = self.get_product_properties(product_id)
            if remaining_properties:
                LOG.error(
                    f"[Product Properties] ERROR: Properties не пустые после delete для товара {product_id}. "
                    f"Осталось {len(remaining_properties)} properties: {remaining_properties}. Прерываем обновление."
                )
                return False
            
            # ШАГ 2: PATCH с новыми properties
            payload = {
                "properties": [{"id": pid} for pid in property_option_ids]
            }
            
            self._request("PATCH", f"/api/product/{product_id}", json=payload)
            
            # ВАЛИДАЦИЯ ШАГ 2: Проверяем, что новые properties установлены
            time.sleep(0.2)  # Небольшая задержка для применения изменений
            actual_properties = set(self.get_product_properties(product_id))
            expected_properties = set(property_option_ids)
            
            if actual_properties == expected_properties:
                LOG.info(f"[Product Properties] Обновлены properties для товара {product_id}: {len(property_option_ids)} properties. Валидация пройдена.")
                return True
            else:
                missing = expected_properties - actual_properties
                extra = actual_properties - expected_properties
                LOG.error(
                    f"[Product Properties] ERROR: Properties не совпадают после update для товара {product_id}. "
                    f"Ожидалось: {sorted(expected_properties)}, получено: {sorted(actual_properties)}. "
                    f"Отсутствуют: {sorted(missing) if missing else 'нет'}, лишние: {sorted(extra) if extra else 'нет'}"
                )
                return False
                
        except Exception as e:
            LOG.error(f"[Product Properties] Ошибка обновления properties для товара {product_id}: {e}")
            return False

    def find_manufacturer_by_name(self, name: str) -> Optional[str]:
        """Ищет Manufacturer по имени, возвращает ID или None."""
        response = self._request(
            "POST",
            "/api/search/product-manufacturer",
            json={
                "filter": [{"field": "name", "type": "equals", "value": name}],
                "limit": 1,
                "includes": {"product_manufacturer": ["id"]},
            },
        )
        if response.get("total"):
            return response["data"][0]["id"]
        return None

    def create_manufacturer(self, name: str) -> str:
        """Создает нового Manufacturer, возвращает ID."""
        import uuid
        manufacturer_id = str(uuid.uuid4().hex)
        payload = {
            "id": manufacturer_id,
            "name": name
        }
        self._request("POST", "/api/product-manufacturer", json=payload)
        return manufacturer_id

    def get_or_create_manufacturer(self, name: str) -> str:
        """Находит существующий Manufacturer или создает новый, возвращает ID."""
        if not name or not name.strip():
            raise ValueError("Manufacturer name cannot be empty")
        name = name.strip()
        existing_id = self.find_manufacturer_by_name(name)
        if existing_id:
            return existing_id
        return self.create_manufacturer(name)
    
    @staticmethod
    def _normalize_name(name: str) -> str:
        """Нормализует имя для поиска: strip, collapse spaces, casefold."""
        if not name:
            return ""
        # Убираем пробелы в начале и конце
        normalized = name.strip()
        # Схлопываем множественные пробелы в один
        import re
        normalized = re.sub(r'\s+', ' ', normalized)
        # Приводим к нижнему регистру
        normalized = normalized.casefold()
        return normalized
    
    def find_manufacturer_by_name_normalized(self, name: str) -> Optional[str]:
        """
        Ищет Manufacturer по нормализованному имени (case-insensitive, trim, collapse spaces).
        Если найдено несколько дублей - возвращает первый и выводит WARNING.
        Использует кэш для избежания повторных запросов.
        
        Args:
            name: Имя производителя
            
        Returns:
            ID производителя (первого найденного, если дублей несколько) или None, если не найден
        """
        normalized = self._normalize_name(name)
        if not normalized:
            return None
        
        # Проверяем кэш
        if normalized in self._manufacturers_cache:
            return self._manufacturers_cache[normalized]
        
        # Ищем через Search API (case-insensitive поиск через contains)
        try:
            response = self._request(
                "POST",
                "/api/search/product-manufacturer",
                json={
                    "filter": [{"field": "name", "type": "contains", "value": normalized}],
                    "limit": 100,  # Получаем все для проверки нормализации
                    "includes": {"product_manufacturer": ["id", "name"]},
                },
            )
            
            if response.get("total") and response.get("data"):
                # Фильтруем по точному совпадению после нормализации
                matching = []
                for manufacturer in response["data"]:
                    manufacturer_name = manufacturer.get("name", "")
                    if self._normalize_name(manufacturer_name) == normalized:
                        matching.append(manufacturer)
                
                if matching:
                    # Если найдено несколько дублей - выводим WARNING и используем первый
                    if len(matching) > 1:
                        LOG.warning(
                            f"[Manufacturer] Найдено {len(matching)} дублей с именем '{name}' (нормализованное: '{normalized}'). "
                            f"Используется первый (ID: {matching[0].get('id')})"
                        )
                    
                    manufacturer_id = matching[0].get("id")
                    if manufacturer_id:
                        # Сохраняем в кэш
                        self._manufacturers_cache[normalized] = manufacturer_id
                        return manufacturer_id
        except Exception as e:
            LOG.error(f"[Manufacturer] Ошибка нормализованного поиска '{name}': {e}")
        
        return None
    
    def create_manufacturer_if_missing(self, name: str) -> str:
        # INVARIANT: CanonRegistry РѕС‚РІРµС‡Р°РµС‚ Р·Р° СЃРѕР·РґР°РЅРёРµ РїСЂРѕРёР·РІРѕРґРёС‚РµР»РµР№.
        """
        Создает Manufacturer только если он не найден (с нормализацией).
        Использует кэш для избежания дублей в рамках одного запуска.
        
        Args:
            name: Имя производителя
            
        Returns:
            ID производителя (существующего или нового)
        """
        if not name or not name.strip():
            raise ValueError("Manufacturer name cannot be empty")
        
        normalized = self._normalize_name(name)
        if not normalized:
            raise ValueError("Manufacturer name cannot be empty after normalization")
        
        # Проверяем кэш
        if normalized in self._manufacturers_cache:
            return self._manufacturers_cache[normalized]
        
        # Ищем существующий
        existing_id = self.find_manufacturer_by_name_normalized(name)
        if existing_id:
            self._manufacturers_cache[normalized] = existing_id
            return existing_id
        
        # Создаем новый (используем оригинальное имя, не нормализованное)
        manufacturer_id = self.create_manufacturer(name.strip())
        self._manufacturers_cache[normalized] = manufacturer_id
        return manufacturer_id


    def delete_all_product_prices(self, product_id: str) -> int:
        """РЈРґР°Р»СЏРµС‚ РІСЃРµ advanced prices (product-price) С‚РѕРІР°СЂР° Рё РІРѕР·РІСЂР°С‰Р°РµС‚ РєРѕР»РёС‡РµСЃС‚РІРѕ СѓРґР°Р»С‘РЅРЅС‹С… Р·Р°РїРёСЃРµР№."""
        if not product_id:
            return 0

        deleted = 0
        page = 1
        limit = 500

        while True:
            try:
                response = self._request(
                    "POST",
                    "/api/search/product-price",
                    json={
                        "filter": [{"field": "productId", "type": "equals", "value": product_id}],
                        "limit": limit,
                        "page": page,
                        "includes": {"product_price": ["id"]},
                    },
                )
            except Exception as exc:
                LOG.error("[Product Price] РћС€РёР±РєР° РїРѕРёСЃРєР° С†РµРЅ РґР»СЏ С‚РѕРІР°СЂР° %s: %s", product_id, exc)
                break

            data = response.get("data", []) if isinstance(response, dict) else []
            if not data:
                break

            for entry in data:
                price_id = entry.get("id")
                if not price_id:
                    continue
                try:
                    self._request("DELETE", f"/api/product-price/{price_id}")
                    deleted += 1
                except Exception as exc:
                    LOG.warning("[Product Price] РќРµ СѓРґР°Р»РѕСЃСЊ СѓРґР°Р»РёС‚СЊ price %s: %s", price_id, exc)

            if len(data) < limit:
                break
            page += 1

        return deleted

    def delete_all_product_media(self, product_id: str) -> int:
        """Удаляет все product_media товара."""
        if not product_id:
            return 0

        deleted = 0
        page = 1
        limit = 100

        while True:
            try:
                response = self._request(
                    "POST",
                    "/api/search/product-media",
                    json={
                        "filter": [{"field": "productId", "type": "equals", "value": product_id}],
                        "limit": limit,
                        "page": page,
                        "includes": {"product_media": ["id"]},
                    },
                )
            except Exception as exc:
                LOG.error("[Product Media] Ошибка поиска медиа товара %s: %s", product_id, exc)
                break

            data = response.get("data", []) if isinstance(response, dict) else []
            if not data:
                break

            for entry in data:
                media_id = entry.get("id")
                if not media_id:
                    continue
                try:
                    self._request("DELETE", f"/api/product-media/{media_id}")
                    deleted += 1
                except Exception as exc:
                    LOG.warning("[Product Media] Не удалось удалить media %s: %s", media_id, exc)

            if len(data) < limit:
                break
            page += 1

        return deleted

    def delete_all_product_visibilities(self, product_id: str) -> int:
        """Удаляет все product_visibility записи товара."""
        if not product_id:
            return 0

        deleted = 0
        page = 1
        limit = 50

        while True:
            try:
                response = self._request(
                    "POST",
                    "/api/search/product-visibility",
                    json={
                        "filter": [{"field": "productId", "type": "equals", "value": product_id}],
                        "limit": limit,
                        "page": page,
                        "includes": {"product_visibility": ["id"]},
                    },
                )
            except Exception as exc:
                LOG.error("[Product Visibility] Ошибка поиска видимости товара %s: %s", product_id, exc)
                break

            data = response.get("data", []) if isinstance(response, dict) else []
            if not data:
                break

            for entry in data:
                visibility_id = entry.get("id")
                if not visibility_id:
                    continue
                try:
                    self._request("DELETE", f"/api/product-visibility/{visibility_id}")
                    deleted += 1
                except Exception as exc:
                    LOG.warning("[Product Visibility] Не удалось удалить visibility %s: %s", visibility_id, exc)

            if len(data) < limit:
                break
            page += 1

        return deleted

    def list_products(self, *, limit: int = 10, page: int = 1) -> Dict[str, Any]:
        params = {"limit": limit, "page": page}
        return self._request("GET", "/api/product", params=params)

    def get_product_media_folder_id(self) -> Optional[str]:
        """Находит папку 'Product Media' и возвращает её ID."""
        # Используем кэш, если уже найдена
        if self._product_media_folder_id:
            return self._product_media_folder_id
        
        try:
            response = self._request(
                "POST",
                "/api/search/media-folder",
                json={
                    "filter": [{"field": "name", "type": "equals", "value": "Product Media"}],
                    "limit": 1,
                    "includes": {"media_folder": ["id"]},
                },
            )
            # Проверяем data, а не total (total может быть null)
            data = response.get("data", [])
            if data and len(data) > 0:
                folder_id = data[0].get("id")
                if folder_id:
                    # Убеждаемся, что конфигурация создана и связана (только один раз)
                    if not self._product_media_config_id:
                        self.get_or_create_product_media_folder_configuration(folder_id)
                    self._product_media_folder_id = folder_id
                    return folder_id
        except Exception:
            pass
        
        # Если папка не найдена, создаём её с thumbnail sizes
        folder_id = self.create_product_media_folder()
        if folder_id:
            # Убеждаемся, что конфигурация создана и связана
            if not self._product_media_config_id:
                self.get_or_create_product_media_folder_configuration(folder_id)
            self._product_media_folder_id = folder_id
        return folder_id

    def get_or_create_product_media_folder_configuration(self, folder_id: str) -> Optional[str]:
        """Находит или создаёт конфигурацию для папки Product Media с thumbnail sizes."""
        import uuid
        
        try:
            # Проверяем, есть ли у папки уже конфигурация
            folder_response = self._request("GET", f"/api/media-folder/{folder_id}")
            folder_data = folder_response.get("data", {}) if isinstance(folder_response, dict) else folder_response
            existing_config_id = folder_data.get("configurationId")
            
            if existing_config_id:
                # Проверяем, что конфигурация имеет thumbnail sizes
                try:
                    config_response = self._request("GET", f"/api/media-folder-configuration/{existing_config_id}")
                    config_data = config_response.get("data", {}) if isinstance(config_response, dict) else config_response
                    sizes = config_data.get("thumbnailSizes", [])
                    if sizes and len(sizes) > 0:
                        print(f"[MEDIA_CONFIG] Папка уже имеет конфигурацию с {len(sizes)} размерами: {existing_config_id}")
                        return existing_config_id
                except:
                    pass
            
            # Создаём новую конфигурацию (без mediaFolderId - это поле не существует)
            config_id = str(uuid.uuid4().hex)
            thumbnail_sizes = [
                {"width": 1920, "height": 1920},
                {"width": 800, "height": 800},
                {"width": 400, "height": 400},
                {"width": 192, "height": 192},
            ]
            
            config_payload = {
                "id": config_id,
                "thumbnailSizes": thumbnail_sizes,
            }
            
            self._request("POST", "/api/media-folder-configuration", json=config_payload)
            print(f"[MEDIA_CONFIG] Создана новая конфигурация: {config_id}")
            
            # Связываем папку с конфигурацией через Sync API (PATCH не работает)
            # Получаем текущее имя папки как строку (не объект с переводами)
            folder_name_str = "Product Media"  # Используем простую строку для Sync API
            
            sync_payload = [
                {
                    "entity": "media_folder",
                    "action": "upsert",
                    "payload": [{
                        "id": folder_id,
                        "name": folder_name_str,  # СТРОКА, не объект!
                        "configurationId": config_id,
                    }]
                }
            ]
            
            self._request("POST", "/api/_action/sync", json=sync_payload)
            print(f"[MEDIA_CONFIG] Папка {folder_id} связана с конфигурацией {config_id} через Sync API")
            
            # Проверяем, что связь установилась
            verify_response = self._request("GET", f"/api/media-folder/{folder_id}")
            verify_data = verify_response.get("data", {}) if isinstance(verify_response, dict) else verify_response
            if verify_data.get("configurationId") == config_id:
                print(f"[MEDIA_CONFIG] ✓ Подтверждено: папка связана с конфигурацией")
            else:
                print(f"[MEDIA_CONFIG] ⚠ WARNING: Проверка не прошла. Текущий configId: {verify_data.get('configurationId')}")
            
            return config_id
        except Exception as e:
            print(f"[MEDIA_CONFIG] Ошибка создания конфигурации: {e}")
            return None

    def create_product_media_folder(self) -> Optional[str]:
        """Создаёт папку 'Product Media' с thumbnail sizes и возвращает её ID."""
        import uuid
        
        try:
            # 1. Создаём папку
            folder_id = str(uuid.uuid4().hex)
            folder_payload = {
                "id": folder_id,
                "name": {"ru-RU": "Product Media", "en-GB": "Product Media", "de-DE": "Product Media"},
            }
            
            self._request("POST", "/api/media-folder", json=folder_payload)
            print(f"[MEDIA_FOLDER] Создана папка: {folder_id}")
            
            # 2. Создаём конфигурацию с thumbnail sizes и связываем с папкой
            config_id = self.get_or_create_product_media_folder_configuration(folder_id)
            
            # 3. Обновляем папку, связывая её с конфигурацией
            if config_id:
                update_payload = {
                    "configurationId": config_id,
                }
                self._request("PATCH", f"/api/media-folder/{folder_id}", json=update_payload)
                print(f"[MEDIA_FOLDER] Папка {folder_id} связана с конфигурацией {config_id}")
            
            return folder_id
        except Exception as e:
            print(f"[MEDIA_FOLDER] Ошибка создания папки: {e}")
            return None

    def create_media(self, media_folder_id: Optional[str] = None) -> str:
        """Создает пустую Media Entity, возвращает media_id."""
        import uuid
        media_id = str(uuid.uuid4().hex)
        payload = {"id": media_id}
        if media_folder_id:
            payload["mediaFolderId"] = media_folder_id
        self._request("POST", "/api/media", json=payload)
        
        # Если папка не установилась при создании, пробуем обновить через PATCH
        if media_folder_id:
            try:
                # Проверяем, установилась ли папка
                check_response = self._request("GET", f"/api/media/{media_id}")
                check_data = check_response.get("data", {}) if isinstance(check_response, dict) else check_response
                current_folder_id = check_data.get("attributes", {}).get("mediaFolderId")
                if current_folder_id != media_folder_id:
                    # Пробуем обновить через PATCH с полным payload
                    update_payload = {
                        "id": media_id,
                        "mediaFolderId": media_folder_id,
                    }
                    self._request("PATCH", f"/api/media/{media_id}", json=update_payload)
                    # Проверяем еще раз
                    verify_response = self._request("GET", f"/api/media/{media_id}")
                    verify_data = verify_response.get("data", {}) if isinstance(verify_response, dict) else verify_response
                    final_folder_id = verify_data.get("attributes", {}).get("mediaFolderId")
                    if final_folder_id != media_folder_id:
                        print(f"[WARNING] Папка не установлена для медиа {media_id}. Текущая: {final_folder_id}, ожидалась: {media_folder_id}")
            except Exception as e:
                print(f"[WARNING] Не удалось установить папку для медиа {media_id}: {e}")
        
        return media_id

    def create_media_via_sync(self, media_folder_id: str) -> str:
        """
        Создает Media Entity через Sync API с mediaFolderId.
        Возвращает media_id.
        
        Используется для гарантированной установки mediaFolderId,
        так как POST /api/media может не устанавливать mediaFolderId корректно.
        """
        import uuid
        media_id = str(uuid.uuid4().hex)
        
        sync_payload = [
            {
                "entity": "media",
                "action": "upsert",
                "payload": [{
                    "id": media_id,
                    "mediaFolderId": media_folder_id
                }]
            }
        ]
        
        self._request("POST", "/api/_action/sync", json=sync_payload)
        
        # Проверяем, что mediaFolderId установлен
        try:
            check_response = self._request("GET", f"/api/media/{media_id}")
            check_data = check_response.get("data", {}) if isinstance(check_response, dict) else check_response
            current_folder_id = check_data.get("attributes", {}).get("mediaFolderId")
            if current_folder_id != media_folder_id:
                print(f"[WARNING] mediaFolderId не установлен для media {media_id}. Текущий: {current_folder_id}, ожидался: {media_folder_id}")
        except Exception as e:
            print(f"[WARNING] Не удалось проверить mediaFolderId для media {media_id}: {e}")
        
        return media_id

    def create_product_media_via_sync(
        self,
        product_id: str,
        media_id: str,
        position: int
    ) -> str:
        """
        Создает product_media связь через Sync API.
        Возвращает product_media_id.
        """
        import uuid
        product_media_id = str(uuid.uuid4().hex)
        
        sync_payload = [
            {
                "entity": "product_media",
                "action": "upsert",
                "payload": [{
                    "id": product_media_id,
                    "productId": product_id,
                    "mediaId": media_id,
                    "position": position
                }]
            }
        ]
        
        self._request("POST", "/api/_action/sync", json=sync_payload)
        
        return product_media_id

    def create_product_media(
        self,
        product_id: str,
        media_id: str,
        position: int = 0
    ) -> Optional[str]:
        """
        Создает product_media связь через POST /api/product-media (канонический способ Shopware 6).
        
        Args:
            product_id: ID товара
            media_id: ID media (изображения)
            position: Позиция изображения (0 для cover)
        
        Returns:
            product_media_id или None при ошибке
        """
        try:
            payload = {
                "productId": product_id,
                "mediaId": media_id,
                "position": position
            }
            
            # Выполняем запрос напрямую для обработки 204 No Content
            self._ensure_token()
            url = f"{self._config.api_base}/api/product-media"
            resp = self._session.post(
                url,
                json=payload,
                timeout=self._timeout,
                verify=False
            )
            
            if resp.status_code >= 400:
                raise ShopwareClientError(
                    f"Shopware API error {resp.status_code}: {resp.text.strip()}"
                )
            
            # Shopware 6 возвращает 204 No Content при успешном создании
            # ID находится в заголовке Location
            if resp.status_code == 204:
                location = resp.headers.get("Location", "")
                if location:
                    import re
                    match = re.search(r'/api/product-media/([a-f0-9]+)', location)
                    if match:
                        return match.group(1)
                
                # Если Location не содержит ID, ищем через поиск
                import time
                time.sleep(0.2)
                pm_search = self._request(
                    "POST",
                    "/api/search/product-media",
                    json={
                        "filter": [
                            {"field": "productId", "type": "equals", "value": product_id},
                            {"field": "mediaId", "type": "equals", "value": media_id},
                            {"field": "position", "type": "equals", "value": position}
                        ],
                        "limit": 1
                    }
                )
                if isinstance(pm_search, dict):
                    pm_list = pm_search.get("data", [])
                    if pm_list:
                        return pm_list[0].get("id")
            
            # Если ответ содержит JSON
            if resp.text:
                try:
                    response = resp.json()
                    if isinstance(response, dict):
                        data = response.get("data", {})
                        if isinstance(data, dict):
                            return data.get("id")
                        elif isinstance(data, list) and len(data) > 0:
                            return data[0].get("id")
                    elif isinstance(response, list) and len(response) > 0:
                        return response[0].get("id")
                except Exception:
                    pass
            
            return None
        except Exception as e:
            LOG.error(f"[Product Media] Ошибка создания product_media: {e}")
            return None
    
    def set_product_cover(
        self,
        product_id: str,
        product_media_id: str
    ) -> bool:
        """
        Устанавливает coverId товара через PATCH /api/product/{id} с использованием associations.cover.
        
        В Shopware 6.7 поле coverId является read-only при прямом PATCH.
        Необходимо использовать формат associations:
        {
          "cover": {
            "id": "product_media_id"
          }
        }
        
        Args:
            product_id: ID товара
            product_media_id: ID product_media (НЕ media_id!)
        
        Returns:
            True при успехе, False при ошибке
        """
        try:
            # ЗАЩИТА ОТ РЕГРЕССИИ: Проверяем, что не передается прямое поле coverId
            if not product_media_id:
                raise ValueError("product_media_id не может быть пустым")
            
            # Используем associations.cover вместо прямого поля coverId
            # В Shopware 6.7 прямое поле coverId является read-only и игнорируется
            payload = {
                "cover": {
                    "id": product_media_id
                }
            }
            
            # Дополнительная проверка: убеждаемся, что payload не содержит прямое поле coverId
            if "coverId" in payload:
                raise ValueError(
                    "[REGRESSION GUARD] Прямое поле coverId запрещено в Shopware 6.7. "
                    "Используйте только associations.cover: {'cover': {'id': '...'}}"
                )
            
            self._request("PATCH", f"/api/product/{product_id}", json=payload)
            return True
        except Exception as e:
            LOG.error(f"[Product Cover] Ошибка установки cover через associations: {e}")
            return False
    
    def update_product_custom_fields(
        self,
        product_id: str,
        custom_fields: Dict[str, Any]
    ) -> bool:
        """
        Обновляет customFields товара через отдельный PATCH /api/product/{id}.
        
        Args:
            product_id: ID товара
            custom_fields: Словарь customFields (например, {"internal_barcode": "123"})
        
        Returns:
            True при успехе, False при ошибке
        """
        try:
            payload = {"customFields": custom_fields}
            self._request("PATCH", f"/api/product/{product_id}", json=payload)
            return True
        except Exception as e:
            LOG.error(f"[Custom Fields] Ошибка обновления customFields: {e}")
            return False
    
    def set_product_media_and_cover(
        self,
        product_id: str,
        media_ids: List[str]
    ) -> Optional[str]:
        """
        DEPRECATED: Используйте create_product_media() + set_product_cover() вместо этого метода.
        Оставлен для обратной совместимости с CREATE логикой.
        
        Создает product_media связи и устанавливает coverId через канонические REST API.
        Использует associations.cover для установки coverId.
        
        Args:
            product_id: ID товара
            media_ids: Список media_id (изображений)
        
        Returns:
            product_media_id первого изображения (используется как coverId) или None
        """
        if not media_ids:
            return None
        
        # Создаем product_media для каждого изображения
        first_product_media_id = None
        
        for pos, media_id in enumerate(media_ids):
            product_media_id = self.create_product_media(
                product_id=product_id,
                media_id=media_id,
                position=pos
            )
            
            if product_media_id and pos == 0:
                first_product_media_id = product_media_id
        
        # Устанавливаем coverId для первого изображения через associations.cover
        if first_product_media_id:
            import time
            time.sleep(0.2)  # Небольшая задержка для применения изменений
            self.set_product_cover(product_id, first_product_media_id)
        
        return first_product_media_id

    def get_or_create_custom_field_barcode(self) -> bool:
        """
        Создает custom field internal_barcode для хранения пользовательского штрих-кода.
        
        Returns:
            True если custom field создан или уже существует, False при ошибке
        """
        # Проверяем кэш
        if self._barcode_custom_field_created:
            return True
        
        try:
            # Проверяем существование custom field
            search_response = self._request(
                "POST",
                "/api/search/custom-field",
                json={
                    "filter": [
                        {"field": "name", "type": "equals", "value": "internal_barcode"}
                    ],
                    "limit": 1
                }
            )
            
            if isinstance(search_response, dict):
                data = search_response.get("data", [])
                if data and len(data) > 0:
                    # Custom field уже существует
                    self._barcode_custom_field_created = True
                    LOG.info("[Custom Field] internal_barcode уже существует")
                    return True
            
            # Создаем custom field
            custom_field_payload = {
                "name": "internal_barcode",
                "type": "text",
                "config": {
                    "customFieldPosition": 1,
                    "label": {
                        "ru-RU": "Внутренний штрих-код"
                    },
                    "helpText": {
                        "ru-RU": "Пользовательский штрих-код из InSales"
                    }
                },
                "relations": [
                    {"entityName": "product"}
                ]
            }
            
            self._request("POST", "/api/custom-field", json=custom_field_payload)
            self._barcode_custom_field_created = True
            LOG.info("[Custom Field] internal_barcode успешно создан")
            return True
            
        except Exception as e:
            LOG.error(f"[Custom Field] Ошибка создания internal_barcode: {e}")
            return False

    def upload_media_blob(
        self,
        media_id: str,
        file_content: bytes,
        filename: str,
        content_type: str = "image/jpeg"
    ) -> None:
        """Загружает blob в Media Entity."""
        import mimetypes
        extension = mimetypes.guess_extension(content_type) or ".jpg"
        extension = extension.lstrip(".")
        
        url = f"/api/_action/media/{media_id}/upload"
        params = {"extension": extension, "fileName": filename}
        
        # Используем прямой запрос с бинарными данными
        self._ensure_token()
        full_url = f"{self._config.api_base}{url}"
        response = self._session.post(
            full_url,
            params=params,
            data=file_content,
            headers={"Content-Type": content_type},
            timeout=self._timeout,
            verify=False
        )
        if response.status_code >= 400:
            raise ShopwareClientError(
                f"Media upload failed {response.status_code}: {response.text}"
            )

    def get_default_tax_id(self) -> str:
        """Возвращает ID базовой налоговой ставки в Shopware."""
        if self._default_tax_id:
            return self._default_tax_id

        response = self._request(
            "POST",
            "/api/search/tax",
            json={"limit": 1, "includes": {"tax": ["id"]}},
        )
        data = response.get("data") if isinstance(response, dict) else None
        if data:
            tax_id = data[0]["id"]
            self._default_tax_id = tax_id
            return tax_id

        raise ShopwareClientError("No tax rates available in Shopware instance")
    
    def get_standard_tax_id(self) -> str:
        """
        Возвращает ID стандартной налоговой ставки (Standard rate) в Shopware.
        Ищет СТРОГО по имени "Standard rate". Если не найден - ERROR и остановка.
        
        Returns:
            ID налоговой ставки
            
        Raises:
            ShopwareClientError: Если налог "Standard rate" не найден
        """
        if self._standard_tax_id:
            return self._standard_tax_id
        
        try:
            # Ищем "Standard rate" СТРОГО по имени
            response = self._request(
                "POST",
                "/api/search/tax",
                json={
                    "filter": [
                        {"field": "name", "type": "equals", "value": "Standard rate"}
                    ],
                    "limit": 1,
                    "includes": {"tax": ["id", "name", "taxRate", "position"]},
                },
            )
            
            # Проверяем наличие data (total может быть None в некоторых версиях Shopware)
            if response.get("data"):
                tax_data = response["data"][0]
                # name может быть в attributes или в корне
                tax_name = tax_data.get("name") or tax_data.get("attributes", {}).get("name", "")
                # Проверяем точное совпадение имени
                if tax_name == "Standard rate":
                    tax_id = tax_data.get("id")
                    if tax_id:
                        tax_rate = tax_data.get("taxRate") or tax_data.get("attributes", {}).get("taxRate", 0)
                        self._standard_tax_id = tax_id
                        LOG.info(f"[Tax] Найден Standard rate: ID={tax_id}, rate={tax_rate}")
                        return tax_id
            
            # НЕ НАЙДЕН - ERROR и остановка
            error_msg = "[Tax] ERROR: Налог 'Standard rate' не найден в Shopware. Импорт остановлен."
            LOG.error(error_msg)
            raise ShopwareClientError(error_msg)
            
        except ShopwareClientError:
            raise
        except Exception as e:
            error_msg = f"[Tax] ERROR: Ошибка поиска налога 'Standard rate': {e}. Импорт остановлен."
            LOG.error(error_msg)
            raise ShopwareClientError(error_msg)

    def get_currency_id(self, iso_code: str) -> str:
        """Возвращает ID валюты по ISO-коду (например, RUB)."""
        normalized = (iso_code or "").upper()
        if not normalized:
            return self.get_system_currency_id()
        if normalized in self._currency_cache:
            return self._currency_cache[normalized]

        response = self._request(
            "POST",
            "/api/search/currency",
            json={
                "filter": [{"field": "isoCode", "type": "equals", "value": normalized}],
                "includes": {"currency": ["id"]},
                "limit": 1,
            },
        )
        if response.get("total"):
            currency_id = response["data"][0]["id"]
            self._currency_cache[normalized] = currency_id
            return currency_id

        return self.get_system_currency_id()

    def get_sales_channel_currency_id(self) -> Optional[str]:
        """Возвращает ID валюты из первого Sales Channel."""
        try:
            response = self._request("GET", "/api/sales-channel")
            sales_channels = response.get("data", []) if isinstance(response, dict) else []
            if sales_channels:
                # Получаем детали первого Sales Channel
                sc_id = sales_channels[0].get('id')
                if sc_id:
                    detail_response = self._request("GET", f"/api/sales-channel/{sc_id}")
                    sc_data = detail_response.get("data", {}) if isinstance(detail_response, dict) else {}
                    attributes = sc_data.get("attributes", {})
                    currency_id = attributes.get("currencyId")
                    if currency_id:
                        return currency_id
        except Exception:
            pass
        return None

    def get_storefront_sales_channel_id(self) -> Optional[str]:
        """Возвращает ID первого активного Storefront Sales Channel."""
        try:
            response = self._request("GET", "/api/sales-channel")
            sales_channels = response.get("data", []) if isinstance(response, dict) else []
            # Ищем активный Storefront Sales Channel
            for sc in sales_channels:
                if sc.get("active", False):
                    # Проверяем, что это Storefront (обычно typeId указывает на тип)
                    sc_id = sc.get("id")
                    if sc_id:
                        return sc_id
            # Если не нашли активный, берем первый
            if sales_channels:
                return sales_channels[0].get("id")
        except Exception:
            pass
        return None

    def get_system_currency_id(self) -> str:
        if self._system_currency_id:
            return self._system_currency_id
        
        # Пробуем найти валюту RUB через поиск по ISO коду
        try:
            rub_response = self._request(
                "POST",
                "/api/search/currency",
                json={
                    "filter": [{"field": "isoCode", "type": "equals", "value": "RUB"}],
                    "includes": {"currency": ["id", "isoCode", "factor"]},
                    "limit": 1,
                },
            )
            if rub_response.get("total") and rub_response.get("data"):
                rub_curr = rub_response["data"][0]
                # Если RUB найдена и имеет factor=1.0, используем её
                if rub_curr.get("factor") == 1.0:
                    self._system_currency_id = rub_curr["id"]
                    return self._system_currency_id
        except Exception:
            pass  # Игнорируем ошибки поиска RUB
        
        # Получаем все валюты через search API с includes
        try:
            response = self._request(
                "POST",
                "/api/search/currency",
                json={
                    "includes": {"currency": ["id", "isoCode", "factor"]},
                    "limit": 100,
                },
            )
            data = response.get("data") if isinstance(response, dict) else []
            if data:
                # Ищем валюту с factor=1.0 (обычно это системная)
                for curr in data:
                    if curr.get("factor") == 1.0:
                        self._system_currency_id = curr["id"]
                        return self._system_currency_id
                # Fallback: берем первую валюту
                self._system_currency_id = data[0]["id"]
                return self._system_currency_id
        except Exception:
            pass
        
        raise ShopwareClientError("Unable to determine default currency in Shopware")
    
    def find_price_rule_by_name(self, name: str) -> Optional[str]:
        """
        Ищет Price Rule по имени, возвращает ruleId или None.
        
        Args:
            name: Название правила
            
        Returns:
            ID правила или None, если не найдено
        """
        try:
            response = self._request(
                "POST",
                "/api/search/rule",
                json={
                    "filter": [{"field": "name", "type": "equals", "value": name}],
                    "limit": 1,
                    "includes": {"rule": ["id", "name"]},
                },
            )
            if response.get("total") and response.get("data"):
                return response["data"][0]["id"]
        except Exception as e:
            LOG.error(f"[Price Rule] Ошибка поиска правила '{name}': {e}")
        return None
    
    def find_rule_by_name_normalized(self, name: str) -> Optional[str]:
        """
        Ищет Price Rule по нормализованному имени (case-insensitive, trim, collapse spaces).
        Если найдено несколько правил с одинаковым именем, выбирает одно (самое раннее по createdAt, иначе первое).
        Использует кэш для избежания повторных запросов.
        
        Args:
            name: Название правила
            
        Returns:
            ID правила или None, если не найдено
        """
        normalized = self._normalize_name(name)
        if not normalized:
            return None
        
        # Проверяем кэш
        if normalized in self._price_rules_cache:
            return self._price_rules_cache[normalized]
        
        try:
            # Ищем все правила с похожим именем
            response = self._request(
                "POST",
                "/api/search/rule",
                json={
                    "filter": [{"field": "name", "type": "contains", "value": normalized}],
                    "limit": 100,  # Получаем все для проверки нормализации
                    "includes": {"rule": ["id", "name", "createdAt"]},
                },
            )
            
            if response.get("total") and response.get("data"):
                # Фильтруем по точному совпадению после нормализации
                matching_rules = []
                for rule in response["data"]:
                    rule_name = rule.get("name", "")
                    if self._normalize_name(rule_name) == normalized:
                        matching_rules.append(rule)
                
                if matching_rules:
                    # Если несколько правил, выбираем самое раннее по createdAt
                    if len(matching_rules) > 1:
                        # Сортируем по createdAt (если есть)
                        matching_rules.sort(key=lambda r: r.get("createdAt", ""))
                        if len(matching_rules) > 1:
                            LOG.warning(
                                f"[Price Rule] Найдено {len(matching_rules)} правил с именем '{name}'. "
                                f"Используется самое раннее (createdAt: {matching_rules[0].get('createdAt', 'N/A')})"
                            )
                    
                    rule_id = matching_rules[0].get("id")
                    if rule_id:
                        # Сохраняем в кэш
                        self._price_rules_cache[normalized] = rule_id
                        return rule_id
        except Exception as e:
            LOG.error(f"[Price Rule] Ошибка нормализованного поиска правила '{name}': {e}")
        
        return None
    
    def create_rule_if_missing(self, name: str, priority: int = 100, description: Optional[str] = None) -> str:
        # INVARIANT: РЅРѕРІС‹Рµ РїСЂР°РІРёР»Р° РґРѕР»Р¶РЅС‹ СЂРµРіРёСЃС‚СЂРёСЂРѕРІР°С‚СЊСЃСЏ С‡РµСЂРµР· CanonRegistry.
        """
        Создает Price Rule только если оно не найдено (с нормализацией).
        Использует кэш для избежания дублей в рамках одного запуска.
        
        Args:
            name: Название правила
            priority: Приоритет правила
            description: Описание правила
            
        Returns:
            ID правила (существующего или нового)
        """
        normalized = self._normalize_name(name)
        if not normalized:
            raise ValueError("Rule name cannot be empty after normalization")
        
        # Проверяем кэш
        if normalized in self._price_rules_cache:
            return self._price_rules_cache[normalized]
        
        # Ищем существующее
        existing_id = self.find_rule_by_name_normalized(name)
        if existing_id:
            self._price_rules_cache[normalized] = existing_id
            return existing_id
        
        # Создаем новое (используем оригинальное имя, не нормализованное)
        rule_id = self.create_price_rule(name.strip(), description, priority)
        self._price_rules_cache[normalized] = rule_id
        return rule_id
    
    def create_price_rule(self, name: str, description: Optional[str] = None, priority: int = 100) -> str:
        """
        Создает новое Price Rule для Marketplace цен.
        
        Args:
            name: Название правила
            description: Описание правила
            priority: Приоритет правила (по умолчанию 100)
            
        Returns:
            ID созданного правила
        """
        import uuid
        rule_id = uuid.uuid4().hex
        
        payload = {
            "id": rule_id,
            "name": name,
            "priority": priority,
            "description": description or f"Price rule for {name} (from InSales price2)",
            "conditions": [
                {
                    "type": "orContainer",
                    "children": []
                }
            ],
            "active": True
        }
        
        try:
            self._request("POST", "/api/rule", json=payload)
            LOG.info(f"[Price Rule] Создано правило '{name}' с ID: {rule_id}")
            return rule_id
        except Exception as e:
            LOG.error(f"[Price Rule] Ошибка создания правила '{name}': {e}")
            raise ShopwareClientError(f"Failed to create price rule '{name}': {e}")
    
    def find_product_by_number(self, product_number: str) -> Optional[str]:
        """
        Находит товар в Shopware по productNumber (SKU).
        
        Учитывает формат JSON:API Shopware:
        - Search API возвращает данные в includes (productNumber в корне)
        - GET API возвращает данные в attributes (attributes.productNumber)
        
        Args:
            product_number: Product number (SKU) товара
            
        Returns:
            ID товара или None, если не найден
        """
        try:
            # Шаг 1: Поиск через Search API
            response = self._request(
                "POST",
                "/api/search/product",
                json={
                    "filter": [{"field": "productNumber", "type": "equals", "value": product_number}],
                    "limit": 1,
                    "includes": {"product": ["id", "productNumber"]},
                },
            )
            
            data = response.get("data") or []
            if not data:
                return None
            
            product = data[0]
            product_id = product.get("id")
            
            if not product_id:
                return None
            
            # Шаг 2: Получаем полные данные через GET API для валидации
            # (в формате JSON:API данные находятся в attributes)
            try:
                full_response = self._request("GET", f"/api/product/{product_id}")
                full_data = full_response.get("data", {}) if isinstance(full_response, dict) else {}
                
                # Проверяем оба возможных формата:
                # 1. attributes.productNumber (JSON:API формат GET API)
                # 2. productNumber (Search API с includes)
                found_product_number = None
                
                if isinstance(full_data, dict):
                    # Формат JSON:API: данные в attributes
                    attributes = full_data.get("attributes", {})
                    if attributes:
                        found_product_number = attributes.get("productNumber")
                    # Fallback: проверяем корневой productNumber (если формат другой)
                    if not found_product_number:
                        found_product_number = full_data.get("productNumber")
                
                # Шаг 3: Валидация - проверяем, что productNumber действительно совпадает
                if found_product_number == product_number:
                    return product_id
                else:
                    LOG.warning(
                        f"[Product] Найден товар с несовпадающим productNumber: "
                        f"запрошено '{product_number}', получено '{found_product_number}' (product_id: {product_id})"
                    )
                    return None
                    
            except Exception as e:
                # Если не удалось получить полные данные, используем данные из Search API
                LOG.warning(
                    f"[Product] Не удалось получить полные данные для валидации (product_id: {product_id}): {e}. "
                    f"Используем данные из Search API."
                )
                # Валидация по данным из Search API
                found_product_number = product.get("productNumber")
                if found_product_number == product_number:
                    return product_id
                else:
                    LOG.warning(
                        f"[Product] Найден товар с несовпадающим productNumber (Search API): "
                        f"запрошено '{product_number}', получено '{found_product_number}'"
                    )
                    return None
                    
        except Exception as e:
            LOG.error(f"[Product] Ошибка поиска товара по productNumber '{product_number}': {e}")
        return None

    def get_system_language_id(self) -> str:
        if self._system_language_id:
            return self._system_language_id
        response = self._request("GET", "/api/language", params={"limit": 1})
        data = response.get("data") if isinstance(response, dict) else None
        if data:
            self._system_language_id = data[0]["id"]
            return self._system_language_id
        raise ShopwareClientError("Unable to determine default language in Shopware")
    
    def get_product_prices(self, product_id: str) -> List[Dict[str, Any]]:
        """
        Получает все advanced prices товара (product.prices).
        
        Args:
            product_id: ID товара
            
        Returns:
            Список цен в формате [{"ruleId": "...", "quantityStart": 1, "price": [...]}, ...]
        """
        try:
            response = self._request(
                "GET",
                f"/api/product/{product_id}",
                params={"associations[prices]": "{}"}
            )
            
            if isinstance(response, dict):
                data = response.get("data", {})
                if isinstance(data, dict):
                    attributes = data.get("attributes", {})
                    prices = attributes.get("prices", [])
                    if prices:
                        return prices
        except Exception as e:
            LOG.error(f"[Product Prices] Ошибка получения prices для товара {product_id}: {e}")
        
        return []
    
    def get_tax_info(self, tax_id: str) -> Dict[str, Any]:
        """
        Получает информацию о налоговой ставке (name, rate).
        
        Args:
            tax_id: ID налоговой ставки
            
        Returns:
            Словарь с полями "id", "name", "taxRate" или пустой словарь при ошибке
        """
        try:
            response = self._request("GET", f"/api/tax/{tax_id}")
            if isinstance(response, dict):
                data = response.get("data", {})
                if isinstance(data, dict):
                    attributes = data.get("attributes", {})
                    return {
                        "id": tax_id,
                        "name": attributes.get("name", "N/A"),
                        "taxRate": attributes.get("taxRate", 0.0)
                    }
        except Exception as e:
            LOG.error(f"[Tax] Ошибка получения информации о налоге {tax_id}: {e}")
        
        return {"id": tax_id, "name": "N/A", "taxRate": 0.0}
    
    def get_product_prices(self, product_id: str) -> List[Dict[str, Any]]:
        """
        Получает все advanced prices товара (product.prices).
        
        Args:
            product_id: ID товара
            
        Returns:
            Список цен в формате [{"ruleId": "...", "quantityStart": 1, "price": [...]}, ...]
        """
        try:
            response = self._request(
                "GET",
                f"/api/product/{product_id}",
                params={"associations[prices]": "{}"}
            )
            
            if isinstance(response, dict):
                data = response.get("data", {})
                if isinstance(data, dict):
                    attributes = data.get("attributes", {})
                    prices = attributes.get("prices", [])
                    if prices:
                        return prices
        except Exception as e:
            LOG.error(f"[Product Prices] Ошибка получения prices для товара {product_id}: {e}")
        
        return []
    
    def get_tax_info(self, tax_id: str) -> Dict[str, Any]:
        """
        Получает информацию о налоговой ставке (name, rate).
        
        Args:
            tax_id: ID налоговой ставки
            
        Returns:
            Словарь с полями "id", "name", "taxRate" или пустой словарь при ошибке
        """
        try:
            response = self._request("GET", f"/api/tax/{tax_id}")
            if isinstance(response, dict):
                data = response.get("data", {})
                if isinstance(data, dict):
                    attributes = data.get("attributes", {})
                    return {
                        "id": tax_id,
                        "name": attributes.get("name", "N/A"),
                        "taxRate": attributes.get("taxRate", 0.0)
                    }
        except Exception as e:
            LOG.error(f"[Tax] Ошибка получения информации о налоге {tax_id}: {e}")
        
        return {"id": tax_id, "name": "N/A", "taxRate": 0.0}

    def sync_products(
        self,
        data: Union[str, Path, Sequence[Mapping[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """
        Запускает импорт товаров через Sync API.

        Параметр `data` может быть:
        - путём к CSV файлу;
        - последовательностью готовых payload'ов для Sync API.
        """

        if isinstance(data, (str, Path)):
            payload = self._load_products_from_csv(Path(data))
        else:
            payload = list(data)

        if not payload:
            return []

        sync_body = [
            {
                "action": "upsert",
                "entity": "product",
                "payload": payload,
            }
        ]
        response = self._request("POST", "/api/_action/sync", json=sync_body)
        if isinstance(response, list):
            return response
        return [response]

    # ------------------------------------------------------------------ #
    # CSV helpers
    # ------------------------------------------------------------------ #
    def _load_products_from_csv(self, csv_path: Path) -> List[Dict[str, Any]]:
        if not csv_path.exists():
            raise ShopwareClientError(f"CSV file not found: {csv_path}")
        rows: List[Dict[str, Any]] = []
        with csv_path.open("r", encoding="utf-8", newline="") as handler:
            reader = csv.DictReader(handler)
            for raw_row in reader:
                product_payload = self._translate_csv_row(raw_row)
                if product_payload:
                    rows.append(product_payload)
        return rows

    def _translate_csv_row(self, row: MutableMapping[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Базовое преобразование строки CSV в payload для Sync API.

        CSV должен содержать следующие колонки:
        - productNumber
        - name
        - description
        - price
        - stock
        Дополнительные поля (categoryIds, propertyIds, media) обрабатываются, если присутствуют.
        """

        product_number = (row.get("productNumber") or "").strip()
        name = (row.get("name") or "").strip()
        if not product_number or not name:
            LOG.warning("CSV row skipped: missing productNumber or name")
            return None

        payload: Dict[str, Any] = {
            "productNumber": product_number,
            "name": {"ru-RU": name},
            "description": {"ru-RU": (row.get("description") or "").strip()},
            "stock": int(row.get("stock") or 0),
            "price": [
                {
                    "currencyId": row.get("currencyId"),
                    "gross": float(row.get("price") or 0),
                    "net": float(row.get("price") or 0),
                    "linked": False,
                }
            ],
            "active": True,
        }

        if row.get("id"):
            payload["id"] = row["id"].strip()
        if row.get("taxId"):
            payload["taxId"] = row["taxId"].strip()

        category_ids = self._split_values(row.get("categoryIds"))
        if category_ids:
            payload["categories"] = [{"id": cat_id} for cat_id in category_ids]

        property_ids = self._split_values(row.get("propertyIds"))
        if property_ids:
            payload["properties"] = [{"id": prop_id} for prop_id in property_ids]

        media_urls = self._split_values(row.get("media"))
        if media_urls:
            payload["media"] = [{"url": url} for url in media_urls]

        return payload

    @staticmethod
    def _split_values(value: Optional[str]) -> List[str]:
        if not value:
            return []
        separators = [",", ";", "|"]
        normalized = value
        for sep in separators:
            normalized = normalized.replace(sep, "|")
        result = [token.strip() for token in normalized.split("|")]
        return [token for token in result if token]


__all__ = [
    "ShopwareClient",
    "ShopwareClientError",
    "ShopwareConfig",
]


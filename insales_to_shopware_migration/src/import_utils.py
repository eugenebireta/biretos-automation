from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from clients import ShopwareClient
from category_utils import is_leaf_category, get_category_chain


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path, *, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as handler:
        return json.load(handler)


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handler:
        json.dump(payload, handler, ensure_ascii=False, indent=2)


def split_pipe(value: str) -> List[str]:
    if not value:
        return []
    return [token.strip() for token in value.split("|") if token.strip()]


def load_properties(json_blob: str) -> List[Dict[str, Any]]:
    if not json_blob:
        return []
    try:
        data = json.loads(json_blob)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return []


def ensure_property_option(
    shopware_client: ShopwareClient,
    option_map: Dict[str, str],
    property_entry: Dict[str, Any],
) -> Optional[str]:
    value = (property_entry.get("value") or "").strip()
    group_id = property_entry.get("group_id")
    if not value or not group_id:
        return None

    key = f"{property_entry.get('property_id')}::{value}"
    if key in option_map:
        return option_map[key]

    existing = shopware_client.find_property_option_id(group_id, value)
    if existing:
        option_map[key] = existing
        return existing

    new_id = uuid4().hex
    payload = {
        "id": new_id,
        "groupId": group_id,
        "name": value,
        "translations": {
            shopware_client.get_system_language_id(): {"name": value},
        },
    }
    shopware_client.create_property_option(payload)
    option_map[key] = new_id
    return new_id


def build_payload(
    row: Dict[str, Any],
    *,
    shopware_client: ShopwareClient,
    option_map: Dict[str, str],
    storefront_sales_channel_id: Optional[str] = None,
) -> Dict[str, Any]:
    # Приоритет: валюта из Sales Channel (там установлен RUB)
    default_currency_id = None
    
    # Сначала пробуем получить валюту из Sales Channel
    try:
        sales_channel_currency = shopware_client.get_sales_channel_currency_id()
        if sales_channel_currency:
            default_currency_id = sales_channel_currency
            print(f"DEBUG: Found currency from Sales Channel: {default_currency_id}")
    except Exception:
        pass
    
    # Если не найдена в Sales Channel, пробуем найти RUB по ISO коду
    if not default_currency_id:
        try:
            rub_currency_id = shopware_client.get_currency_id("RUB")
            print(f"DEBUG: Found RUB currency by ISO code: {rub_currency_id}")
            default_currency_id = rub_currency_id
        except Exception:
            pass
    
    # Если RUB не найдена, используем системную валюту
    if not default_currency_id:
        system_currency_id = shopware_client.get_system_currency_id()
        print(f"DEBUG: Using system currency ID: {system_currency_id}")
        default_currency_id = system_currency_id
    
    print(f"DEBUG: Using default currency ID: {default_currency_id}")
    
    currency_id = shopware_client.get_currency_id(row.get("currencyIso", ""))
    price_value = float(row.get("price") or 0)
    stock_value = int(float(row.get("stock") or 0))
    active_flag = bool(int(row.get("active") or 0))

    # Получаем категории из CSV
    category_ids_raw = split_pipe(row.get("categoryIds") or "")
    
    # Выбираем только листовую категорию (самую глубокую)
    leaf_category_id = None
    if category_ids_raw:
        # Берем первую категорию (в CSV уже должна быть только листовая)
        candidate_id = category_ids_raw[0]
        
        # Проверяем, что категория листовая
        if is_leaf_category(shopware_client, candidate_id):
            leaf_category_id = candidate_id
        else:
            # Если не листовая - это ошибка, товар не должен попасть сюда
            product_name = row.get("name", "Unknown")
            raise ValueError(
                f"[SKIP_PARENT_CATEGORY] Товар '{product_name}' не может быть в родительской категории {candidate_id}"
            )
    
    # КАНОНИЧЕСКАЯ ЛОГИКА SHOPWARE 6:
    # Товар должен быть привязан ко ВСЕМ категориям цепочки (от root до leaf)
    # Это необходимо для корректной работы breadcrumbs и навигации
    categories = []
    if leaf_category_id:
        # Получаем цепочку категорий от root до leaf
        category_chain = get_category_chain(shopware_client, leaf_category_id)
        # Формируем массив categories для payload
        categories = [{"id": cat_id} for cat_id in category_chain]

    property_payload = []
    for entry in load_properties(row.get("propertiesJson") or ""):
        option_id = ensure_property_option(shopware_client, option_map, entry)
        if option_id:
            property_payload.append({"id": option_id})

    description = (row.get("description") or "").strip()
    name = (row.get("name") or "").strip()

    # ВАЛИДАЦИЯ: Обязательно должна быть цена для default валюты
    if not default_currency_id:
        raise ValueError("Default currency ID not found - cannot create product price")

    price_entries: List[Dict[str, Any]] = []
    # ВАЖНО: Используем ТОЛЬКО валюту из Sales Channel (RUB)
    # Не добавляем другие валюты, чтобы избежать путаницы
    price_entries.append(
        {
            "currencyId": default_currency_id,
            "gross": float(price_value),
            "net": float(price_value),
            "linked": False,
        }
    )
    # НЕ добавляем валюту из CSV, используем только валюту из Sales Channel

    # Финальная валидация
    if not price_entries:
        raise ValueError("Unable to resolve price currencies for product payload")
    
    # Проверяем, что default валюта присутствует
    if not any(entry["currencyId"] == default_currency_id for entry in price_entries):
        raise ValueError(f"Default currency {default_currency_id} not found in price entries")

    payload = {
        "productNumber": row.get("productNumber"),
        "name": name,
        "description": description,
        "stock": stock_value,
        "active": active_flag,
        "taxId": row.get("taxId"),
        "price": price_entries,
    }
    
    # НЕ добавляем ID при создании нового товара
    # Shopware автоматически создаст новый товар, если productNumber уникален
    # ID нужен только для обновления существующего товара через PATCH

    # Добавляем категории и mainCategories (только листовая категория)
    if categories:
        payload["categories"] = categories
        # mainCategoryId - основная категория товара (для обратной совместимости)
        payload["mainCategoryId"] = leaf_category_id
        
        # mainCategories - массив для привязки к Sales Channels (Shopware 6)
        # Используем storefront sales channel ID из параметра или получаем из API
        if not storefront_sales_channel_id:
            storefront_sales_channel_id = shopware_client.get_storefront_sales_channel_id()
        if storefront_sales_channel_id and leaf_category_id:
            payload["mainCategories"] = [
                {
                    "categoryId": leaf_category_id,
                    "salesChannelId": storefront_sales_channel_id
                }
            ]
    
    if property_payload:
        payload["properties"] = property_payload
    
    # Обработка изображений из CSV (imageUrls)
    # ВАЖНО: Shopware НЕ принимает {"url": "..."} при создании товара через API
    # Медиа должны загружаться отдельно через Media API (add_media_to_products.py)
    # Поэтому НЕ добавляем media в payload при создании товара
    
    # Привязка к Sales Channel (visibilities) - обязательно для видимости на фронтенде
    # КАНОНИЧЕСКАЯ ЛОГИКА SHOPWARE 6:
    # product_visibility.categoryId = самая глубокая категория (leaf)
    # Это используется для breadcrumbs и SEO
    try:
        sc_response = shopware_client._request("GET", "/api/sales-channel")
        sales_channels = sc_response.get("data", []) if isinstance(sc_response, dict) else []
        
        # Получаем storefront sales channel ID
        if not storefront_sales_channel_id:
            storefront_sales_channel_id = shopware_client.get_storefront_sales_channel_id()
        
        # Формируем visibilities для всех sales channels
        visibilities = []
        for sc in sales_channels:
            sc_id = sc.get("id")
            if not sc_id:
                continue
            
            # Для storefront sales channel устанавливаем categoryId (leaf категория)
            # Для остальных sales channels - без categoryId
            item: Dict[str, Any] = {
                "salesChannelId": sc_id,
                "visibility": 30  # 30 = all
            }
            
            # categoryId устанавливаем только для storefront sales channel
            if sc_id == storefront_sales_channel_id and leaf_category_id:
                item["categoryId"] = leaf_category_id
            
            visibilities.append(item)
        
        if visibilities:
            payload["visibilities"] = visibilities
    except Exception as e:
        # Если не удалось получить Sales Channels, пропускаем
        pass

    return payload





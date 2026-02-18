#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЭТАЛОННЫЙ импорт ОДНОГО товара из InSales в Shopware 6
с ПОЛНЫМ набором обязательных полей через VARIANT структуру.
"""

import json
import sys
import time
import uuid
import re
import requests
from pathlib import Path
from typing import Dict, Any, Optional, List

# Добавляем путь к src
sys.path.insert(0, str(Path(__file__).parent / "src"))

from clients.shopware_client import ShopwareClient, ShopwareConfig
from category_utils import get_category_chain, find_category_by_path, is_leaf_category


def find_product_with_all_fields(products_file: Path) -> Optional[Dict[str, Any]]:
    """Находит товар с заполненными всеми обязательными полями."""
    products = []
    with open(products_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                product = json.loads(line)
                products.append(product)
            except json.JSONDecodeError:
                continue
    
    # Ищем товар с нужными полями
    for product in products:
        variants = product.get('variants', [])
        if not variants or len(variants) == 0:
            continue
        
        variant = variants[0]
        sku = variant.get('sku')
        price = variant.get('price')
        price2 = variant.get('price2')
        barcode = variant.get('barcode')
        quantity = variant.get('quantity')
        weight = variant.get('weight')
        dimensions = variant.get('dimensions')
        category_id = product.get('category_id')
        images = product.get('images', [])
        vendor = product.get('vendor') or product.get('brand')
        
        # Проверяем все обязательные поля
        if all([
            sku,
            price is not None,
            price2 is not None,
            barcode,
            quantity is not None,
            weight is not None,
            category_id,
            len(images) > 0
        ]):
            return product
    
    return None


def delete_product_by_sku(client: ShopwareClient, sku: str) -> bool:
    """Удаляет товар из Shopware по SKU (productNumber)."""
    import time
    
    # Пробуем найти товар несколькими способами
    product_id = None
    
    # Способ 1: через find_product_by_number
    try:
        product_id = client.find_product_by_number(sku)
    except Exception:
        pass
    
    # Способ 2: через прямой Search API
    if not product_id:
        try:
            response = client._request(
                "POST",
                "/api/search/product",
                json={
                    "filter": [{"field": "productNumber", "type": "equals", "value": sku}],
                    "limit": 1,
                    "includes": {"product": ["id", "productNumber"]},
                },
            )
            if response.get("total", 0) > 0 and response.get("data"):
                product_id = response["data"][0].get("id")
        except Exception as e:
            print(f"[DELETE] Ошибка поиска через Search API: {e}")
    
    # Способ 3: через GET /api/product с фильтром (если доступно)
    if not product_id:
        try:
            list_response = client.list_products(limit=100, page=1)
            if isinstance(list_response, dict):
                products_list = list_response.get("data", [])
                for p in products_list:
                    p_attrs = p.get("attributes", {})
                    if p_attrs and p_attrs.get("productNumber") == sku:
                        product_id = p.get("id")
                        break
        except Exception as e:
            print(f"[DELETE] Ошибка поиска через list_products: {e}")
    
    if not product_id:
        print(f"[DELETE] Товар с SKU '{sku}' не найден в Shopware. Пропускаем удаление.")
        return True
    
    # Удаляем товар
    print(f"[DELETE] Найден товар с ID: {product_id}, удаляем...")
    try:
        client._request("DELETE", f"/api/product/{product_id}")
        print(f"[DELETE] Товар успешно удален.")
        
        # Проверяем, что товар действительно удален
        time.sleep(1.0)
        
        verify_response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [{"field": "productNumber", "type": "equals", "value": sku}],
                "limit": 1,
            },
        )
        if verify_response.get("total", 0) > 0:
            print(f"[DELETE] WARNING: Товар все еще существует после удаления.")
            return False
        else:
            print(f"[DELETE] Подтверждено: товар удален.")
            return True
    except Exception as e:
        print(f"[DELETE] Ошибка при удалении товара: {e}")
        return False


def get_or_create_manufacturer(client: ShopwareClient, brand_name: str) -> Optional[str]:
    """Находит или создает Manufacturer (brand)."""
    if not brand_name or not brand_name.strip():
        return None
    
    try:
        manufacturer_id = client.get_or_create_manufacturer(brand_name.strip())
        print(f"[MANUFACTURER] Найден/создан: '{brand_name}' → {manufacturer_id}")
        return manufacturer_id
    except Exception as e:
        print(f"[MANUFACTURER] Ошибка: {e}")
        return None


def restore_category_chain(
    client: ShopwareClient,
    category_id: int,
    category_id_to_path: Dict[str, str],
    root_category_id: str
) -> tuple[Optional[List[str]], Optional[str]]:
    """Восстанавливает полную цепочку категорий и возвращает leaf категорию."""
    category_id_str = str(category_id)
    category_value = category_id_to_path.get(category_id_str)
    
    if not category_value:
        print(f"[CATEGORIES] Категория для category_id={category_id} не найдена")
        return None, None
    
    # Проверяем, является ли значение UUID (32 hex символа) или путь
    is_uuid = len(category_value) == 32 and all(c in '0123456789abcdef' for c in category_value.lower())
    
    if is_uuid:
        # Это UUID категории Shopware - используем напрямую
        leaf_category_id = category_value
        print(f"[CATEGORIES] Найден UUID категории: {leaf_category_id}")
    else:
        # Это путь - находим категорию по пути
        full_path = category_value
        print(f"[CATEGORIES] Путь: {full_path}")
        leaf_category_id = find_category_by_path(client, full_path, root_category_id)
        
        if not leaf_category_id:
            print(f"[CATEGORIES] Leaf категория не найдена для пути: {full_path}")
            return None, None
    
    # Проверяем, что категория существует
    try:
        cat_response = client._request("GET", f"/api/category/{leaf_category_id}")
        if not cat_response:
            print(f"[CATEGORIES] Категория {leaf_category_id} не существует")
            return None, None
    except Exception as e:
        print(f"[CATEGORIES] Ошибка проверки категории {leaf_category_id}: {e}")
        return None, None
    
    # Проверяем, что категория листовая
    if not is_leaf_category(client, leaf_category_id):
        print(f"[CATEGORIES] Категория {leaf_category_id} не листовая")
        return None, None
    
    # Получаем полную цепочку категорий
    category_chain = get_category_chain(client, leaf_category_id)
    
    print(f"[CATEGORIES] Цепочка категорий: {len(category_chain)} категорий")
    print(f"[CATEGORIES] Leaf категория: {leaf_category_id}")
    
    return category_chain, leaf_category_id


def get_or_create_marketplace_price_rule(client: ShopwareClient) -> str:
    """Находит или создает Price Rule 'Marketplace Price'."""
    rule_name = "Marketplace Price"
    rule_id = client.find_price_rule_by_name(rule_name)
    
    if rule_id:
        print(f"[PRICE RULE] Найдено правило '{rule_name}' с ID: {rule_id}")
        return rule_id
    
    print(f"[PRICE RULE] Создаем правило '{rule_name}'...")
    rule_id = client.create_price_rule(rule_name, "Price rule for marketplace prices from InSales price2")
    print(f"[PRICE RULE] Правило создано с ID: {rule_id}")
    return rule_id


def download_and_upload_image(client: ShopwareClient, image_url: str, product_number: str, index: int = 0) -> Optional[str]:
    """Загружает изображение из URL и возвращает media_id."""
    try:
        # Получаем папку Product Media
        media_folder_id = client.get_product_media_folder_id()
        if not media_folder_id:
            print(f"[IMAGE] Не удалось получить папку Product Media")
            return None
        
        # Создаем Media Entity
        media_id = client.create_media_via_sync(media_folder_id)
        
        # Загружаем изображение
        response = requests.get(image_url, timeout=30, verify=False)
        if response.status_code != 200:
            print(f"[IMAGE] Ошибка загрузки изображения: {response.status_code}")
            return None
        
        # Определяем content type
        content_type = response.headers.get('Content-Type', 'image/jpeg')
        # Используем уникальное имя файла с timestamp и индексом
        import time as time_module
        timestamp = int(time_module.time() * 1000) % 1000000  # Последние 6 цифр timestamp
        original_filename = image_url.split('/')[-1] or f"{product_number}.jpg"
        # Убираем расширение если оно уже есть
        if '.' in original_filename:
            base_name = original_filename.rsplit('.', 1)[0]
            ext = original_filename.rsplit('.', 1)[1]
        else:
            base_name = original_filename
            ext = 'jpg'
        # Очищаем base_name от недопустимых символов
        base_name = re.sub(r'[^\w\-_]', '_', base_name)
        filename = f"{product_number}_{timestamp}_{index}.{ext}"
        
        # Загружаем blob
        client.upload_media_blob(media_id, response.content, filename, content_type)
        
        print(f"[IMAGE] Загружено: {filename} -> {media_id}")
        return media_id
    except Exception as e:
        error_msg = str(e).encode('ascii', 'ignore').decode('ascii')
        print(f"[IMAGE] Ошибка загрузки изображения: {error_msg}")
        return None


def create_variant_product(
    client: ShopwareClient,
    product: Dict[str, Any],
    variant: Dict[str, Any],
    manufacturer_id: Optional[str],
    category_chain: List[str],
    leaf_category_id: str,
    marketplace_rule_id: str,
    media_ids: List[str],
    storefront_sales_channel_id: Optional[str]
) -> Optional[str]:
    """Создает товар в Shopware (как простой product, но с полным набором полей)."""
    sku = variant['sku']
    title = product.get('title', '')
    price = float(variant['price'])
    price2 = float(variant['price2'])
    barcode = variant['barcode']
    quantity = int(variant.get('quantity', 0) or 0)
    weight = float(variant.get('weight', 0) or 0)
    
    # Получаем необходимые ID
    tax_id = client.get_default_tax_id()
    currency_id = client.get_system_currency_id()
    
    # Создаем UUID для product
    product_id = str(uuid.uuid4().hex)
    
    # PRODUCT payload (с полным набором полей)
    product_payload = {
        "id": product_id,
        "productNumber": sku,
        "name": {"ru-RU": title},
        "active": True,
        "taxId": tax_id,
        "stock": quantity,
        "price": [{
            "currencyId": currency_id,
            "gross": price,
            "net": price,
            "linked": False,
        }],
    }
    
    # Добавляем manufacturer
    if manufacturer_id:
        product_payload["manufacturerId"] = manufacturer_id
    
    # Добавляем категории (вся цепочка)
    if category_chain:
        product_payload["categories"] = [{"id": cat_id} for cat_id in category_chain]
    
    # Добавляем mainCategory
    if storefront_sales_channel_id and leaf_category_id:
        product_payload["mainCategories"] = [{
            "salesChannelId": storefront_sales_channel_id,
            "categoryId": leaf_category_id
        }]
    
    # Добавляем manufacturerNumber (партномер)
    manufacturer_number = variant.get('manufacturer_number') or variant.get('part_number') or sku
    product_payload["manufacturerNumber"] = manufacturer_number
    
    # Добавляем barcode (EAN)
    product_payload["ean"] = barcode
    
    # Добавляем вес
    if weight > 0:
        product_payload["weight"] = weight
    
    # Добавляем габариты
    dimensions = variant.get('dimensions')
    if dimensions:
        try:
            if isinstance(dimensions, str):
                dims = re.findall(r'[\d.]+', dimensions)
                if len(dims) >= 3:
                    product_payload["width"] = float(dims[0])
                    product_payload["height"] = float(dims[1])
                    product_payload["length"] = float(dims[2])
            elif isinstance(dimensions, dict):
                for key in ["width", "height", "length"]:
                    val = dimensions.get(key)
                    if val is not None:
                        val_float = float(val)
                        if val_float > 0:
                            product_payload[key] = val_float
        except (ValueError, TypeError):
            pass
    
    # Добавляем Marketplace цену
    if price2 > 0:
        product_payload["prices"] = [{
            "ruleId": marketplace_rule_id,
            "quantityStart": 1,
            "price": [{
                "currencyId": currency_id,
                "gross": price2,
                "net": price2,
                "linked": False,
            }]
        }]
    
    # Создаем через Sync API
    sync_body = [
        {
            "action": "upsert",
            "entity": "product",
            "payload": [product_payload]
        }
    ]
    
    try:
        print(f"[CREATE] Создаем product: {product_id} (SKU: {sku})")
        response = client._request("POST", "/api/_action/sync", json=sync_body)
        
        # Получаем product_id из ответа
        created_product_id = None
        if isinstance(response, dict):
            data = response.get("data", {})
            if isinstance(data, dict):
                product_list = data.get("product", [])
                if product_list and len(product_list) > 0:
                    created_product_id = product_list[0]
        
        if not created_product_id:
            time.sleep(1.0)
            found_id = client.find_product_by_number(sku)
            if found_id:
                created_product_id = found_id
            else:
                created_product_id = product_id
        
        print(f"[CREATE] Товар создан: product_id={created_product_id}")
        
        # Устанавливаем Marketplace цену отдельным PATCH (если не установилась)
        if price2 > 0:
            time.sleep(0.5)
            prices_payload = {
                "prices": [{
                    "ruleId": marketplace_rule_id,
                    "quantityStart": 1,
                    "price": [{
                        "currencyId": currency_id,
                        "gross": price2,
                        "net": price2,
                        "linked": False
                    }]
                }]
            }
            try:
                client._request("PATCH", f"/api/product/{created_product_id}", json=prices_payload)
                print(f"[CREATE] Marketplace цена установлена: {price2}")
            except Exception as e:
                print(f"[CREATE] WARNING: Не удалось установить Marketplace цену: {e}")
        
        # Устанавливаем customFields (internal_barcode)
        client.get_or_create_custom_field_barcode()
        client.update_product_custom_fields(
            product_id=created_product_id,
            custom_fields={"internal_barcode": str(barcode).strip()}
        )
        
        # Привязываем изображения
        if media_ids:
            first_product_media_id = None
            for pos, media_id in enumerate(media_ids):
                product_media_id = client.create_product_media(
                    product_id=created_product_id,
                    media_id=media_id,
                    position=pos
                )
                if product_media_id and pos == 0:
                    first_product_media_id = product_media_id
            
            # Устанавливаем cover image
            if first_product_media_id:
                time.sleep(0.5)
                client.set_product_cover(created_product_id, first_product_media_id)
                print(f"[CREATE] Cover image установлен: {first_product_media_id}")
        
        return created_product_id
    except Exception as e:
        print(f"[CREATE] Ошибка создания товара: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_product_with_associations(
    client: ShopwareClient,
    product_id: str
) -> Optional[Dict[str, Any]]:
    """Получает товар с associations: variants, prices, media, manufacturer, categories."""
    try:
        # Пробуем через Search API с associations (более надежно)
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [{"field": "id", "type": "equals", "value": product_id}],
                "limit": 1,
                "associations": {
                    "prices": {},
                    "media": {},
                    "manufacturer": {},
                    "categories": {}
                }
            }
        )
        if isinstance(response, dict):
            data_list = response.get("data", [])
            if data_list and len(data_list) > 0:
                product_data = data_list[0]
                # Добавляем included для полноты
                included = response.get("included", [])
                if included:
                    product_data["included"] = included
                return product_data
        
        # Fallback: через GET API
        response = client._request(
            "GET",
            f"/api/product/{product_id}",
            params={
                "associations[variants]": "{}",
                "associations[prices]": "{}",
                "associations[media]": "{}",
                "associations[manufacturer]": "{}",
                "associations[categories]": "{}"
            }
        )
        if isinstance(response, dict):
            return response.get("data", {})
        return response
    except Exception as e:
        print(f"[GET] Ошибка при получении товара: {e}")
        return None


def extract_product_info(
    client: ShopwareClient,
    product_data: Dict[str, Any],
    marketplace_rule_id: str
) -> Dict[str, Any]:
    """Извлекает нужные поля из данных товара."""
    attributes = product_data.get("attributes", {})
    
    # Название
    name_raw = attributes.get("name", "")
    if isinstance(name_raw, dict):
        name = name_raw.get("ru-RU", "")
    else:
        name = str(name_raw) if name_raw else ""
    
    # Manufacturer
    manufacturer = None
    relationships = product_data.get("relationships", {})
    manufacturer_rel = relationships.get("manufacturer", {})
    if manufacturer_rel:
        manufacturer_data = manufacturer_rel.get("data", {})
        if manufacturer_data:
            # Нужно получить через included или отдельным запросом
            manufacturer_id = manufacturer_data.get("id")
            if manufacturer_id:
                try:
                    mf_response = client._request("GET", f"/api/product-manufacturer/{manufacturer_id}")
                    if isinstance(mf_response, dict):
                        mf_data = mf_response.get("data", {})
                        if mf_data:
                            mf_attrs = mf_data.get("attributes", {})
                            manufacturer = mf_attrs.get("name", "")
                except Exception:
                    pass
    
    # ProductNumber (из variant)
    product_number = attributes.get("productNumber", "")
    
    # ManufacturerNumber
    manufacturer_number = attributes.get("manufacturerNumber", "")
    
    # Barcode (EAN)
    ean = attributes.get("ean", "")
    custom_fields = attributes.get("customFields", {})
    internal_barcode = custom_fields.get("internal_barcode", "")
    barcode = ean or internal_barcode
    
    # Base price
    base_price_list = attributes.get("price", [])
    base_price = None
    if base_price_list and len(base_price_list) > 0:
        base_price = base_price_list[0].get("gross")
    
    # Marketplace price - пробуем через included
    marketplace_price = None
    found_rule_id = None
    
    included = product_data.get("included", [])
    if included:
        for item in included:
            if item.get("type") == "product_price":
                price_attrs = item.get("attributes", {})
                if price_attrs:
                    rule_id = price_attrs.get("ruleId")
                    if rule_id == marketplace_rule_id:
                        price_list = price_attrs.get("price", [])
                        if price_list and len(price_list) > 0:
                            marketplace_price = price_list[0].get("gross")
                            found_rule_id = rule_id
                            break
    
    # Если не нашли в included, пробуем через attributes.prices
    if marketplace_price is None:
        advanced_prices = attributes.get("prices", [])
        if advanced_prices:
            for price_entry in advanced_prices:
                rule_id = price_entry.get("ruleId")
                if rule_id == marketplace_rule_id:
                    price_list = price_entry.get("price", [])
                    if price_list and len(price_list) > 0:
                        marketplace_price = price_list[0].get("gross")
                        found_rule_id = rule_id
                        break
    
    # Stock
    stock = attributes.get("stock", 0)
    
    # Weight
    weight = attributes.get("weight", 0)
    
    # Dimensions
    width = attributes.get("width", 0)
    height = attributes.get("height", 0)
    length = attributes.get("length", 0)
    dimensions = f"{width}x{height}x{length}" if (width or height or length) else None
    
    # Categories - получаем из included или через отдельный запрос
    categories = []
    included = product_data.get("included", [])
    if included:
        for item in included:
            if item.get("type") == "category":
                cat_attrs = item.get("attributes", {})
                if cat_attrs:
                    cat_name = cat_attrs.get("name", {})
                    if isinstance(cat_name, dict):
                        cat_name = cat_name.get("ru-RU", "")
                    elif isinstance(cat_name, str):
                        pass
                    else:
                        cat_name = ""
                    if cat_name:
                        categories.append(cat_name)
    
    # Если не нашли в included, пробуем через relationships
    if not categories:
        categories_rel = relationships.get("categories", {})
        if categories_rel:
            categories_data = categories_rel.get("data", [])
            if isinstance(categories_data, list):
                for cat in categories_data:
                    cat_id = cat.get("id")
                    if cat_id:
                        try:
                            cat_response = client._request("GET", f"/api/category/{cat_id}")
                            if isinstance(cat_response, dict):
                                cat_data = cat_response.get("data", {})
                                if cat_data:
                                    cat_attrs = cat_data.get("attributes", {})
                                    cat_name = cat_attrs.get("name", {})
                                    if isinstance(cat_name, dict):
                                        cat_name = cat_name.get("ru-RU", "")
                                    categories.append(cat_name)
                        except Exception:
                            pass
    
    # MainCategory
    main_category = None
    main_categories = attributes.get("mainCategories", [])
    if main_categories and len(main_categories) > 0:
        main_cat = main_categories[0]
        main_cat_id = main_cat.get("categoryId")
        if main_cat_id:
            try:
                cat_response = client._request("GET", f"/api/category/{main_cat_id}")
                if isinstance(cat_response, dict):
                    cat_data = cat_response.get("data", {})
                    if cat_data:
                        cat_attrs = cat_data.get("attributes", {})
                        cat_name = cat_attrs.get("name", {})
                        if isinstance(cat_name, dict):
                            cat_name = cat_name.get("ru-RU", "")
                        main_category = cat_name
            except Exception:
                pass
    
    # Images - получаем из included или через relationships
    images_count = 0
    cover_image = None
    cover_id = attributes.get("coverId")
    
    # Пробуем через included
    included = product_data.get("included", [])
    if included:
        for item in included:
            if item.get("type") == "product_media":
                images_count += 1
                if cover_id and item.get("id") == cover_id:
                    cover_image = f"Cover: {item.get('id', 'N/A')}"
    
    # Если не нашли в included, пробуем через relationships
    if images_count == 0:
        media_rel = relationships.get("media", {})
        if media_rel:
            media_data = media_rel.get("data", [])
            if isinstance(media_data, list):
                images_count = len(media_data)
                if cover_id:
                    cover_image = f"Cover ID: {cover_id}"
    
    return {
        "name": name,
        "manufacturer": manufacturer or "N/A",
        "productNumber": product_number,
        "manufacturerNumber": manufacturer_number or "N/A",
        "barcode": barcode or "N/A",
        "base_price": base_price,
        "marketplace_price": marketplace_price,
        "price_rule_id": found_rule_id or "N/A",
        "stock": stock,
        "weight": weight,
        "dimensions": dimensions or "N/A",
        "categories": " > ".join(categories) if categories else "N/A",
        "mainCategory": main_category or "N/A",
        "images_count": images_count,
        "cover_image": cover_image or "N/A",
    }


def print_control_table(shopware_data: Dict[str, Any]):
    """Выводит контрольную таблицу."""
    print("\n" + "=" * 80)
    print("КОНТРОЛЬНАЯ ТАБЛИЦА")
    print("=" * 80)
    print(f"{'Поле':<40} | {'Значение'}")
    print("-" * 80)
    print(f"{'name':<40} | {shopware_data.get('name', 'N/A')}")
    print(f"{'manufacturer (brand)':<40} | {shopware_data.get('manufacturer', 'N/A')}")
    print(f"{'productNumber (SKU)':<40} | {shopware_data.get('productNumber', 'N/A')}")
    print(f"{'manufacturerNumber (part number)':<40} | {shopware_data.get('manufacturerNumber', 'N/A')}")
    print(f"{'barcode (EAN)':<40} | {shopware_data.get('barcode', 'N/A')}")
    print(f"{'base price':<40} | {shopware_data.get('base_price', 'N/A')}")
    print(f"{'marketplace price (1 раз)':<40} | {shopware_data.get('marketplace_price', 'N/A')}")
    print(f"{'price rule id':<40} | {shopware_data.get('price_rule_id', 'N/A')}")
    print(f"{'stock':<40} | {shopware_data.get('stock', 'N/A')}")
    print(f"{'weight':<40} | {shopware_data.get('weight', 'N/A')}")
    print(f"{'dimensions':<40} | {shopware_data.get('dimensions', 'N/A')}")
    print(f"{'categories (полная цепочка)':<40} | {shopware_data.get('categories', 'N/A')}")
    print(f"{'mainCategory':<40} | {shopware_data.get('mainCategory', 'N/A')}")
    print(f"{'images count':<40} | {shopware_data.get('images_count', 'N/A')}")
    print(f"{'cover image':<40} | {shopware_data.get('cover_image', 'N/A')}")
    print("=" * 80)


def compare_with_insales(shopware_data: Dict[str, Any], insales_data: Dict[str, Any]):
    """Сравнивает данные Shopware с InSales."""
    variant = insales_data['variants'][0]
    
    print("\n" + "=" * 80)
    print("СРАВНЕНИЕ С INSALES")
    print("=" * 80)
    
    # SKU
    insales_sku = variant.get('sku', '')
    shopware_sku = shopware_data.get('productNumber', '')
    sku_ok = shopware_sku == insales_sku
    print(f"SKU:            {'OK' if sku_ok else 'FAIL'} (InSales: {insales_sku}, Shopware: {shopware_sku})")
    
    # PartNumber
    insales_part = variant.get('manufacturer_number') or variant.get('part_number') or insales_sku
    shopware_part = shopware_data.get('manufacturerNumber', '')
    part_ok = shopware_part == insales_part or (not insales_part and shopware_part == insales_sku)
    print(f"PartNumber:     {'OK' if part_ok else 'FAIL'} (InSales: {insales_part}, Shopware: {shopware_part})")
    
    # Barcode
    insales_barcode = variant.get('barcode', '')
    shopware_barcode = shopware_data.get('barcode', '')
    barcode_ok = shopware_barcode == insales_barcode
    print(f"Barcode:        {'OK' if barcode_ok else 'FAIL'} (InSales: {insales_barcode}, Shopware: {shopware_barcode})")
    
    # Base price
    insales_price = variant.get('price')
    shopware_price = shopware_data.get('base_price')
    base_price_ok = False
    if shopware_price is not None and insales_price is not None:
        base_price_ok = abs(float(shopware_price) - float(insales_price)) < 0.01
    print(f"Base price:     {'OK' if base_price_ok else 'FAIL'} (InSales: {insales_price}, Shopware: {shopware_price})")
    
    # Marketplace price
    insales_price2 = variant.get('price2')
    shopware_price2 = shopware_data.get('marketplace_price')
    marketplace_price_ok = False
    if shopware_price2 is not None and insales_price2 is not None:
        marketplace_price_ok = abs(float(shopware_price2) - float(insales_price2)) < 0.01
    print(f"Marketplace price: {'OK' if marketplace_price_ok else 'FAIL'} (InSales: {insales_price2}, Shopware: {shopware_price2})")
    
    # Brand
    insales_brand = insales_data.get('vendor') or insales_data.get('brand', '')
    shopware_brand = shopware_data.get('manufacturer', '')
    brand_ok = (not insales_brand) or (shopware_brand and shopware_brand.lower() == insales_brand.lower())
    print(f"Brand:          {'OK' if brand_ok else 'FAIL'} (InSales: {insales_brand}, Shopware: {shopware_brand})")
    
    # Categories (проверяем наличие)
    insales_cat_id = insales_data.get('category_id')
    shopware_cats = shopware_data.get('categories', '')
    categories_ok = bool(shopware_cats and shopware_cats != 'N/A')
    print(f"Categories:     {'OK' if categories_ok else 'FAIL'} (InSales: category_id={insales_cat_id}, Shopware: {shopware_cats})")
    
    # Stock
    insales_stock = variant.get('quantity', 0)
    shopware_stock = shopware_data.get('stock', 0)
    stock_ok = int(shopware_stock) == int(insales_stock or 0)
    print(f"Stock:          {'OK' if stock_ok else 'FAIL'} (InSales: {insales_stock}, Shopware: {shopware_stock})")
    
    # Images
    insales_images = len(insales_data.get('images', []))
    shopware_images = shopware_data.get('images_count', 0)
    images_ok = shopware_images == insales_images
    print(f"Images:         {'OK' if images_ok else 'FAIL'} (InSales: {insales_images}, Shopware: {shopware_images})")
    
    print("=" * 80)


def main():
    """Основная функция."""
    # Загружаем конфигурацию
    config_path = Path(__file__).parent / "config.json"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # Инициализируем клиент Shopware
    sw_config = ShopwareConfig(
        url=config['shopware']['url'],
        access_key_id=config['shopware']['access_key_id'],
        secret_access_key=config['shopware']['secret_access_key'],
    )
    client = ShopwareClient(sw_config, timeout=30)
    
    # Загружаем category_id_to_path
    category_path_file = Path(__file__).parent / "insales_snapshot" / "category_id_to_path.json"
    with open(category_path_file, 'r', encoding='utf-8') as f:
        category_id_to_path = json.load(f)
    
    root_category_id = config['shopware']['root_category_id']
    
    # Находим товар
    products_file = Path(__file__).parent / "insales_snapshot" / "products.ndjson"
    print(f"[STEP 1] Ищем товар с полным набором полей в {products_file}...")
    product = find_product_with_all_fields(products_file)
    
    if not product:
        print("[ERROR] Не найден товар с заполненными полями")
        return 1
    
    variant = product['variants'][0]
    sku = variant['sku']
    print(f"[STEP 1] Найден товар: SKU={sku}, title={product.get('title', '')}")
    print(f"  - price: {variant.get('price')}")
    print(f"  - price2: {variant.get('price2')}")
    print(f"  - barcode: {variant.get('barcode')}")
    print(f"  - quantity: {variant.get('quantity')}")
    print(f"  - weight: {variant.get('weight')}")
    print(f"  - category_id: {product.get('category_id')}")
    print(f"  - images: {len(product.get('images', []))}")
    
    # Удаляем товар, если существует
    print(f"\n[STEP 2] Удаляем товар из Shopware (если существует)...")
    for attempt in range(3):
        if delete_product_by_sku(client, sku):
            break
        if attempt < 2:
            time.sleep(2)
            print(f"[DELETE] Повторная попытка {attempt + 2}...")
    
    # Подготовка справочников
    print(f"\n[STEP 3] Подготовка справочников...")
    
    # Manufacturer
    brand_name = product.get('vendor') or product.get('brand', '')
    manufacturer_id = None
    if brand_name:
        manufacturer_id = get_or_create_manufacturer(client, brand_name)
    
    # Categories
    category_id = product.get('category_id')
    category_chain, leaf_category_id = restore_category_chain(
        client, category_id, category_id_to_path, root_category_id
    )
    
    if not category_chain or not leaf_category_id:
        print("[ERROR] Не удалось восстановить цепочку категорий")
        return 1
    
    # Price Rule
    marketplace_rule_id = get_or_create_marketplace_price_rule(client)
    
    # Storefront Sales Channel
    storefront_sales_channel_id = client.get_storefront_sales_channel_id()
    
    # Загружаем изображения
    print(f"\n[STEP 4] Загрузка изображений...")
    media_ids = []
    images = product.get('images', [])
    for idx, img in enumerate(images):
        url = img.get('original_url')
        if url:
            media_id = download_and_upload_image(client, url, sku, idx)
            if media_id:
                media_ids.append(media_id)
    
    print(f"[STEP 4] Загружено изображений: {len(media_ids)}")
    
    # Создаем товар
    print(f"\n[STEP 5] Создание товара с полным набором полей...")
    product_id = create_variant_product(
        client, product, variant, manufacturer_id,
        category_chain, leaf_category_id, marketplace_rule_id,
        media_ids, storefront_sales_channel_id
    )
    
    if not product_id:
        print("[ERROR] Не удалось создать товар")
        return 1
    
    # Получаем данные товара
    print(f"\n[STEP 6] Получение данных товара с associations...")
    time.sleep(3)  # Увеличиваем задержку для индексации
    product_data = get_product_with_associations(client, product_id)
    
    if not product_data:
        print("[ERROR] Не удалось получить данные товара")
        return 1
    
    # Извлекаем информацию
    shopware_info = extract_product_info(client, product_data, marketplace_rule_id)
    
    # Выводим контрольную таблицу
    print_control_table(shopware_info)
    
    # Сравнение с InSales
    compare_with_insales(shopware_info, product)
    
    print("\n[SUCCESS] Эталонный импорт завершен.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


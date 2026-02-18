#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Контрольный импорт ОДНОГО товара из InSales в Shopware.
Проверяет все канонические поля.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Добавляем путь к src
sys.path.insert(0, str(Path(__file__).parent / "src"))

from clients.shopware_client import ShopwareClient, ShopwareConfig


def find_product_with_all_fields(products_file: Path) -> Optional[Dict[str, Any]]:
    """Находит товар с заполненными полями: sku, price, price2, barcode."""
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
        
        if all([sku, price is not None, price2 is not None, barcode]):
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
            print(f"[DELETE] Search API response: total={response.get('total', 0)}, data={response.get('data', [])}")
            if response.get("total", 0) > 0 and response.get("data"):
                product_id = response["data"][0].get("id")
                print(f"[DELETE] Найден товар через Search API: {product_id}")
        except Exception as e:
            print(f"[DELETE] Ошибка поиска через Search API: {e}")
    
    # Способ 3: через GET /api/product с фильтром (если доступно)
    if not product_id:
        try:
            # Пробуем получить список товаров и найти по SKU
            list_response = client.list_products(limit=100, page=1)
            if isinstance(list_response, dict):
                products_list = list_response.get("data", [])
                for p in products_list:
                    p_attrs = p.get("attributes", {})
                    if p_attrs and p_attrs.get("productNumber") == sku:
                        product_id = p.get("id")
                        print(f"[DELETE] Найден товар через list_products: {product_id}")
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
        time.sleep(1.0)  # Увеличиваем задержку
        
        # Проверяем через Search API
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


def import_single_product(
    client: ShopwareClient,
    product: Dict[str, Any],
    marketplace_rule_id: str
) -> Optional[str]:
    """Импортирует один товар в Shopware."""
    variant = product['variants'][0]
    sku = variant['sku']
    title = product.get('title', '')
    price = float(variant['price'])
    price2 = float(variant['price2'])
    barcode = variant['barcode']
    
    # Получаем необходимые ID
    tax_id = client.get_default_tax_id()
    currency_id = client.get_system_currency_id()
    
    # Создаем custom field для barcode, если нужно
    client.get_or_create_custom_field_barcode()
    
    # Формируем payload для Sync API
    import uuid
    product_id = str(uuid.uuid4().hex)
    
    payload = {
        "id": product_id,
        "productNumber": sku,
        "name": {"ru-RU": title},
        "taxId": tax_id,
        "stock": 0,
        "active": True,
        "price": [
            {
                "currencyId": currency_id,
                "gross": price,
                "net": price,
                "linked": False,
            }
        ],
        "customFields": {
            "internal_barcode": barcode
        }
    }
    
    # Добавляем marketplace price через prices с ruleId
    # В Shopware 6.7 prices - это массив объектов с ruleId, quantityStart, price (массив)
    payload["prices"] = [
        {
            "ruleId": marketplace_rule_id,
            "quantityStart": 1,
            "price": [
                {
                    "currencyId": currency_id,
                    "gross": price2,
                    "net": price2,
                    "linked": False,
                }
            ]
        }
    ]
    
    # Импортируем через Sync API (более надежно для создания товаров)
    try:
        print(f"[IMPORT] Импортируем товар: SKU={sku}, name={title}, price={price}, price2={price2}, barcode={barcode}")
        
        # Используем Sync API с action "upsert"
        sync_body = [
            {
                "action": "upsert",
                "entity": "product",
                "payload": [payload],
            }
        ]
        
        response = client._request("POST", "/api/_action/sync", json=sync_body)
        print(f"[IMPORT] Sync API response: {response}")
        
        # Извлекаем product_id из ответа Sync API
        created_product_id = None
        if isinstance(response, dict):
            data = response.get("data", {})
            if isinstance(data, dict):
                product_list = data.get("product", [])
                if product_list and len(product_list) > 0:
                    created_product_id = product_list[0]
        
        # Если не получили ID из ответа, ищем товар по SKU
        if not created_product_id:
            import time
            time.sleep(1.5)  # Задержка для индексации
            created_product_id = client.find_product_by_number(sku)
            if not created_product_id:
                # Пробуем через прямой Search API
                search_response = client._request(
                    "POST",
                    "/api/search/product",
                    json={
                        "filter": [{"field": "productNumber", "type": "equals", "value": sku}],
                        "limit": 1,
                        "includes": {"product": ["id"]},
                    },
                )
                if search_response.get("total", 0) > 0 and search_response.get("data"):
                    created_product_id = search_response["data"][0].get("id")
        
        if created_product_id:
            print(f"[IMPORT] Товар успешно импортирован с ID: {created_product_id}")
            
            # Устанавливаем Marketplace цену отдельным PATCH (как в full_import.py)
            if price2 > 0:
                import time
                time.sleep(1.0)  # Увеличиваем задержку
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
                    print(f"[IMPORT] Устанавливаем Marketplace цену через PATCH: {prices_payload}")
                    patch_response = client._request("PATCH", f"/api/product/{created_product_id}", json=prices_payload)
                    print(f"[IMPORT] PATCH response: {patch_response}")
                    print(f"[IMPORT] Marketplace цена установлена: {price2}")
                    
                    # Проверяем, что цена установилась
                    time.sleep(1.0)
                    check_data = get_product_data(client, created_product_id)
                    if check_data:
                        check_attrs = check_data.get("attributes", {})
                        check_prices = check_attrs.get("prices", [])
                        print(f"[IMPORT] Проверка prices после PATCH: {check_prices}")
                except Exception as e:
                    print(f"[IMPORT] WARNING: Не удалось установить Marketplace цену: {e}")
                    import traceback
                    traceback.print_exc()
            
            return created_product_id
        else:
            print(f"[IMPORT] ERROR: Товар импортирован, но не удалось получить ID. Response: {response}")
            return None
    except Exception as e:
        print(f"[IMPORT] Ошибка при импорте товара: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_product_data(client: ShopwareClient, product_id: str) -> Optional[Dict[str, Any]]:
    """Получает данные товара через GET /api/product/{id} и Search API."""
    try:
        # Пробуем через GET API
        response = client._request("GET", f"/api/product/{product_id}")
        product_data = None
        if isinstance(response, dict):
            product_data = response.get("data", {})
        else:
            product_data = response
        
        # Если prices пустой, пробуем через Search API с associations
        if product_data:
            attributes = product_data.get("attributes", {})
            prices = attributes.get("prices", [])
            if not prices:
                # Пробуем через Search API с associations
                try:
                    search_response = client._request(
                        "POST",
                        "/api/search/product",
                        json={
                            "filter": [{"field": "id", "type": "equals", "value": product_id}],
                            "limit": 1,
                            "associations": {
                                "prices": {}
                            }
                        }
                    )
                    if isinstance(search_response, dict):
                        search_data = search_response.get("data", [])
                        if search_data and len(search_data) > 0:
                            # Объединяем данные
                            search_attrs = search_data[0].get("attributes", {})
                            if search_attrs:
                                search_prices = search_attrs.get("prices", [])
                                if search_prices:
                                    attributes["prices"] = search_prices
                                    product_data["attributes"] = attributes
                except Exception as e:
                    print(f"[GET] WARNING: Не удалось получить prices через Search API: {e}")
        
        return product_data
    except Exception as e:
        print(f"[GET] Ошибка при получении товара: {e}")
        return None


def extract_product_info(product_data: Dict[str, Any], marketplace_rule_id: str) -> Dict[str, Any]:
    """Извлекает нужные поля из данных товара."""
    attributes = product_data.get("attributes", {})
    custom_fields = attributes.get("customFields", {})
    
    # Получаем название (может быть строкой или словарем)
    name_raw = attributes.get("name", "")
    if isinstance(name_raw, dict):
        name = name_raw.get("ru-RU", "")
    else:
        name = str(name_raw) if name_raw else ""
    
    # Получаем базовую цену
    base_price_list = attributes.get("price", [])
    base_price = None
    if base_price_list and len(base_price_list) > 0:
        base_price = base_price_list[0].get("gross")
    
    # Получаем Marketplace цену из prices
    advanced_prices = attributes.get("prices", [])
    marketplace_price = None
    found_rule_id = None
    
    if advanced_prices:
        for price_entry in advanced_prices:
            rule_id = price_entry.get("ruleId")
            if rule_id == marketplace_rule_id:
                price_list = price_entry.get("price", [])
                if price_list and len(price_list) > 0:
                    marketplace_price = price_list[0].get("gross")
                    found_rule_id = rule_id
                    break
    
    return {
        "name": name,
        "productNumber": attributes.get("productNumber", ""),
        "internal_barcode": custom_fields.get("internal_barcode", ""),
        "price_gross": base_price,
        "marketplace_price": marketplace_price,
        "marketplace_rule_id": found_rule_id,
    }


def print_comparison_table(shopware_data: Dict[str, Any], insales_data: Dict[str, Any]):
    """Выводит таблицу сравнения."""
    print("\n" + "=" * 80)
    print("ТАБЛИЦА СРАВНЕНИЯ")
    print("=" * 80)
    print(f"{'Поле':<40} | {'Значение'}")
    print("-" * 80)
    print(f"{'name':<40} | {shopware_data.get('name', 'N/A')}")
    print(f"{'attributes.productNumber':<40} | {shopware_data.get('productNumber', 'N/A')}")
    print(f"{'customFields.internal_barcode':<40} | {shopware_data.get('internal_barcode', 'N/A')}")
    print(f"{'price (gross)':<40} | {shopware_data.get('price_gross', 'N/A')}")
    print(f"{'prices (Marketplace)':<40} | {shopware_data.get('marketplace_price', 'N/A')}")
    print(f"{'ruleId Marketplace':<40} | {shopware_data.get('marketplace_rule_id', 'N/A')}")
    print("=" * 80)
    
    # Сравнение с InSales
    print("\n" + "=" * 80)
    print("СРАВНЕНИЕ С INSALES")
    print("=" * 80)
    
    variant = insales_data['variants'][0]
    insales_sku = variant.get('sku', '')
    insales_barcode = variant.get('barcode', '')
    insales_price = variant.get('price')
    insales_price2 = variant.get('price2')
    
    # Проверки
    sku_ok = shopware_data.get('productNumber') == insales_sku
    barcode_ok = shopware_data.get('internal_barcode') == insales_barcode
    
    base_price_sw = shopware_data.get('price_gross')
    base_price_ok = False
    if base_price_sw is not None and insales_price is not None:
        base_price_ok = abs(float(base_price_sw) - float(insales_price)) < 0.01
    
    marketplace_price_sw = shopware_data.get('marketplace_price')
    marketplace_price_ok = False
    if marketplace_price_sw is not None and insales_price2 is not None:
        marketplace_price_ok = abs(float(marketplace_price_sw) - float(insales_price2)) < 0.01
    
    print(f"SKU:            {'OK' if sku_ok else 'FAIL'} (InSales: {insales_sku}, Shopware: {shopware_data.get('productNumber', 'N/A')})")
    print(f"Barcode:        {'OK' if barcode_ok else 'FAIL'} (InSales: {insales_barcode}, Shopware: {shopware_data.get('internal_barcode', 'N/A')})")
    print(f"Base price:     {'OK' if base_price_ok else 'FAIL'} (InSales: {insales_price}, Shopware: {shopware_data.get('price_gross', 'N/A')})")
    print(f"Marketplace price: {'OK' if marketplace_price_ok else 'FAIL'} (InSales: {insales_price2}, Shopware: {shopware_data.get('marketplace_price', 'N/A')})")
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
    
    # Находим товар
    products_file = Path(__file__).parent / "insales_snapshot" / "products.ndjson"
    print(f"[STEP 1] Ищем товар с заполненными полями в {products_file}...")
    product = find_product_with_all_fields(products_file)
    
    if not product:
        print("[ERROR] Не найден товар с заполненными полями: sku, price, price2, barcode")
        return 1
    
    variant = product['variants'][0]
    sku = variant['sku']
    print(f"[STEP 1] Найден товар: SKU={sku}, title={product.get('title', '')}")
    print(f"  - price: {variant.get('price')}")
    print(f"  - price2: {variant.get('price2')}")
    print(f"  - barcode: {variant.get('barcode')}")
    
    # Удаляем товар, если существует
    print(f"\n[STEP 2] Удаляем товар из Shopware (если существует)...")
    # Пробуем удалить несколько раз с разными методами
    for attempt in range(3):
        if delete_product_by_sku(client, sku):
            break
        if attempt < 2:
            import time
            time.sleep(2)
            print(f"[DELETE] Повторная попытка {attempt + 2}...")
    
    # Получаем или создаем Price Rule
    print(f"\n[STEP 3] Получаем или создаем Price Rule 'Marketplace Price'...")
    marketplace_rule_id = get_or_create_marketplace_price_rule(client)
    
    # Импортируем товар
    print(f"\n[STEP 4] Импортируем товар в Shopware...")
    product_id = import_single_product(client, product, marketplace_rule_id)
    
    if not product_id:
        print("[ERROR] Не удалось импортировать товар")
        return 1
    
    # Получаем данные товара
    print(f"\n[STEP 5] Получаем данные товара через GET /api/product/{product_id}...")
    import time
    time.sleep(2)  # Увеличиваем задержку для применения изменений и индексации
    product_data = get_product_data(client, product_id)
    
    if not product_data:
        print("[ERROR] Не удалось получить данные товара")
        return 1
    
    # Отладочный вывод структуры данных
    attributes = product_data.get("attributes", {})
    print(f"[DEBUG] Attributes keys: {list(attributes.keys())}")
    print(f"[DEBUG] prices structure: {attributes.get('prices', [])}")
    print(f"[DEBUG] price structure: {attributes.get('price', [])}")
    
    # Извлекаем информацию
    shopware_info = extract_product_info(product_data, marketplace_rule_id)
    
    # Выводим таблицу сравнения
    print_comparison_table(shopware_info, product)
    
    print("\n[SUCCESS] Контрольный импорт завершен.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


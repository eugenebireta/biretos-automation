"""
Проверка фактического состояния импортированного товара в Shopware через API.
Только чтение данных, без внесения изменений.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Добавляем текущую директорию в sys.path
sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from category_utils import is_leaf_category, get_category_chain
from import_utils import ROOT

CONFIG_PATH = ROOT / "config.json"

def main():
    # Загружаем конфигурацию
    with CONFIG_PATH.open(encoding="utf-8") as f:
        config = json.load(f)
    
    # Создаем клиент
    client = ShopwareClient(
        ShopwareConfig(
            url=config["shopware"]["url"],
            access_key_id=config["shopware"]["access_key_id"],
            secret_access_key=config["shopware"]["secret_access_key"]
        )
    )
    
    # SKU товара для проверки (можно передать как аргумент)
    sku = sys.argv[1] if len(sys.argv) > 1 else "500944222"
    
    print("=" * 80)
    print(f"ПРОВЕРКА ТОВАРА В SHOPWARE (SKU: {sku})")
    print("=" * 80)
    print()
    
    # 1. Находим товар по SKU
    product_id = client.find_product_by_number(sku)
    
    # Если не нашли через find_product_by_number, пробуем прямой поиск
    if not product_id:
        try:
            resp = client._request("POST", "/api/search/product", json={
                "limit": 100,
                "includes": {"product": ["id"]}
            })
            products = resp.get("data", [])
            for p in products:
                pid = p.get("id")
                if pid:
                    try:
                        full = client._request("GET", f"/api/product/{pid}")
                        data = full.get("data", {})
                        attrs = data.get("attributes", {})
                        pn = attrs.get("productNumber") or data.get("productNumber")
                        if pn == sku:
                            product_id = pid
                            break
                    except:
                        pass
        except:
            pass
    
    if not product_id:
        print(f"[ERROR] Товар с SKU '{sku}' не найден в Shopware")
        return 1
    
    print(f"[OK] Товар найден: product_id = {product_id}")
    print()
    
    # 2. Получаем полные данные товара с associations
    product_response = client._request(
        "GET",
        f"/api/product/{product_id}?associations[manufacturer]=&associations[categories]=&associations[categories][associations][parent]=&associations[media]=&associations[cover]=&associations[properties]="
    )
    
    if not isinstance(product_response, dict) or "data" not in product_response:
        print("[ERROR] Не удалось получить данные товара из Shopware")
        return 1
    
    product_data = product_response.get("data", {})
    attributes = product_data.get("attributes", {}) if isinstance(product_data, dict) else {}
    
    # Строим индекс included
    included_index = {}
    included_list = product_response.get("included", [])
    if isinstance(included_list, list):
        for item in included_list:
            if isinstance(item, dict):
                item_type = item.get("type")
                item_id = item.get("id")
                if item_type and item_id:
                    included_index[(item_type, item_id)] = item
    
    print("=" * 80)
    print("ОТЧЁТ ПРОВЕРКИ")
    print("=" * 80)
    print()
    
    # ============================================
    # 1) MANUFACTURER
    # ============================================
    print("1) MANUFACTURER")
    print("-" * 80)
    manufacturer_id = product_data.get("manufacturerId") or attributes.get("manufacturerId")
    manufacturer_name = "N/A"
    manufacturer_count = 0
    
    if manufacturer_id:
        # Получаем данные manufacturer из included или отдельным запросом
        man_item = included_index.get(("product_manufacturer", manufacturer_id))
        if man_item:
            man_attrs = man_item.get("attributes", {})
            manufacturer_name = man_attrs.get("name", "N/A")
        else:
            try:
                man_response = client._request("GET", f"/api/product-manufacturer/{manufacturer_id}")
                if isinstance(man_response, dict) and "data" in man_response:
                    man_attrs = man_response["data"].get("attributes", {})
                    manufacturer_name = man_attrs.get("name", "N/A")
            except:
                pass
        
        # Проверяем количество дублей
        if manufacturer_name != "N/A":
            try:
                normalized_name = client._normalize_name(manufacturer_name)
                man_search = client._request(
                    "POST",
                    "/api/search/product-manufacturer",
                    json={
                        "filter": [{"field": "name", "type": "contains", "value": normalized_name}],
                        "limit": 100,
                        "includes": {"product_manufacturer": ["id", "name"]},
                    }
                )
                if man_search.get("total"):
                    matching = [m for m in man_search.get("data", [])
                               if client._normalize_name(m.get("name", "")) == normalized_name]
                    manufacturer_count = len(matching)
            except:
                pass
    
    manufacturer_status = "OK" if (manufacturer_id and manufacturer_name != "N/A") else "FAIL"
    if manufacturer_count > 1:
        manufacturer_status = "WARNING"
    
    print(f"  Статус: [{manufacturer_status}]")
    print(f"  ID: {manufacturer_id or 'N/A'}")
    print(f"  Name: {manufacturer_name}")
    print(f"  Количество дублей: {manufacturer_count}")
    print()
    
    # ============================================
    # 2) TAX
    # ============================================
    print("2) TAX")
    print("-" * 80)
    tax_id = product_data.get("taxId") or attributes.get("taxId")
    tax_info = client.get_tax_info(tax_id) if tax_id else {"name": "N/A", "taxRate": 0.0}
    
    # Получаем Standard rate для сравнения
    try:
        standard_tax_id = client.get_standard_tax_id()
        standard_tax_info = client.get_tax_info(standard_tax_id)
        tax_status = "OK" if tax_id == standard_tax_id else "FAIL"
    except:
        standard_tax_info = {"name": "N/A", "taxRate": 0.0}
        tax_status = "FAIL"
    
    print(f"  Статус: [{tax_status}]")
    print(f"  Tax ID: {tax_id or 'N/A'}")
    print(f"  Tax Name: {tax_info.get('name', 'N/A')}")
    print(f"  Tax Rate: {tax_info.get('taxRate', 0.0)}%")
    print(f"  Ожидается: Standard rate ({standard_tax_info.get('name', 'N/A')}, {standard_tax_info.get('taxRate', 0.0)}%)")
    print()
    
    # ============================================
    # 3) VISIBILITY
    # ============================================
    print("3) VISIBILITY")
    print("-" * 80)
    
    # Получаем storefront_sales_channel_id
    storefront_sales_channel_id = config.get("shopware", {}).get("storefront_sales_channel_id")
    if not storefront_sales_channel_id:
        storefront_sales_channel_id = client.get_storefront_sales_channel_id()
    
    # Получаем visibilities ТОЛЬКО через Search API (канонический способ)
    visibilities = []
    try:
        vis_search = client._request(
            "POST",
            "/api/search/product-visibility",
            json={
                "filter": [{"field": "productId", "type": "equals", "value": product_id}],
                "limit": 100,
                "includes": {"product_visibility": ["id", "productId", "salesChannelId", "visibility", "categoryId"]},
            }
        )
        if isinstance(vis_search, dict) and "data" in vis_search:
            raw_visibilities = vis_search.get("data", [])
            # Извлекаем данные из Search API формата (может быть в attributes или напрямую)
            for vis in raw_visibilities:
                vis_data = {}
                if isinstance(vis, dict):
                    # Проверяем, есть ли attributes
                    if "attributes" in vis:
                        attrs = vis["attributes"]
                        vis_data["id"] = vis.get("id")
                        vis_data["productId"] = attrs.get("productId") or vis.get("productId")
                        vis_data["salesChannelId"] = attrs.get("salesChannelId") or vis.get("salesChannelId")
                        vis_data["visibility"] = attrs.get("visibility") or vis.get("visibility", 0)
                        # TODO-BLOCK: DO NOT ADD visibility.categoryId CHECK (Shopware 6 limitation)
                        # categoryId извлекается только для отображения, НЕ для проверки
                        # Shopware 6 REST API не сохраняет visibility.categoryId через POST/PATCH
                        vis_data["categoryId"] = attrs.get("categoryId") if "categoryId" in attrs else (vis.get("categoryId") if "categoryId" in vis else None)
                    else:
                        # Данные напрямую в объекте
                        vis_data = vis.copy()
                        # TODO-BLOCK: DO NOT ADD visibility.categoryId CHECK (Shopware 6 limitation)
                        # categoryId извлекается только для отображения, НЕ для проверки
                        if "categoryId" not in vis_data:
                            vis_data["categoryId"] = None
                visibilities.append(vis_data)
    except Exception as e:
        print(f"  [ERROR] Ошибка получения visibilities: {e}")
        visibilities = []
    
    # Проверяем условие OK: ровно 1 запись, salesChannelId == storefront, visibility == 30
    storefront_visibility = None
    for vis in visibilities:
        sc_id = vis.get("salesChannelId")
        if sc_id == storefront_sales_channel_id:
            storefront_visibility = vis
            break
    
    vis_count = len(visibilities)
    vis_has_storefront = storefront_visibility is not None
    vis_value = storefront_visibility.get("visibility", 0) if storefront_visibility else 0
    
    visibility_status = "OK" if (vis_count == 1 and vis_has_storefront and vis_value == 30) else "FAIL"
    
    print(f"  Статус: [{visibility_status}]")
    print(f"  Всего visibilities: {vis_count} (ожидается: 1)")
    print(f"  Storefront найден: {'Да' if vis_has_storefront else 'Нет'}")
    if storefront_visibility:
        print(f"  Visibility: {vis_value} (ожидается: 30)")
        # TODO-BLOCK: DO NOT ADD visibility.categoryId CHECK (Shopware 6 limitation)
        # categoryId отображается только для информации, НЕ для проверки
        print(f"  Category ID: {storefront_visibility.get('categoryId', 'N/A')}")
    for vis in visibilities:
        sc_id = vis.get("salesChannelId", "N/A")
        vis_val = vis.get("visibility", 0)
        # TODO-BLOCK: DO NOT ADD visibility.categoryId CHECK (Shopware 6 limitation)
        # categoryId отображается только для информации, НЕ для проверки
        cat_id = vis.get("categoryId", "N/A")
        print(f"    - SalesChannel: {sc_id}, Visibility: {vis_val}, Category: {cat_id}")
    print()
    
    # ============================================
    # 4) CATEGORIES
    # ============================================
    print("4) CATEGORIES")
    print("-" * 80)
    
    # Извлекаем categories из product.categories (канонический способ)
    category_ids = []
    # Пробуем через relationships
    relationships = product_data.get("relationships", {})
    if isinstance(relationships, dict):
        categories_rel = relationships.get("categories", {})
        if isinstance(categories_rel, dict):
            categories_data = categories_rel.get("data", [])
            if isinstance(categories_data, list):
                for cat_ref in categories_data:
                    if isinstance(cat_ref, dict):
                        cat_id = cat_ref.get("id")
                        if cat_id:
                            category_ids.append(cat_id)
    
    # Если не нашли через relationships, пробуем через included
    if not category_ids:
        for item in included_list:
            if isinstance(item, dict) and item.get("type") == "category":
                cat_id = item.get("id")
                if cat_id:
                    category_ids.append(cat_id)
    
    # Если все еще не нашли, пробуем через GET с associations (более надежный способ)
    if not category_ids:
        try:
            product_with_cats = client._request("GET", f"/api/product/{product_id}?associations[categories]=")
            if isinstance(product_with_cats, dict):
                prod_data = product_with_cats.get("data", {})
                prod_relationships = prod_data.get("relationships", {})
                if isinstance(prod_relationships, dict):
                    cats_rel = prod_relationships.get("categories", {})
                    if isinstance(cats_rel, dict):
                        cats_data = cats_rel.get("data", [])
                        if isinstance(cats_data, list):
                            for cat_ref in cats_data:
                                if isinstance(cat_ref, dict):
                                    cat_id = cat_ref.get("id")
                                    if cat_id and cat_id not in category_ids:
                                        category_ids.append(cat_id)
        except:
            pass
    
    # КАНОНИЧЕСКИЙ СПОСОБ: GET /api/product/{id}/categories
    if not category_ids:
        try:
            categories_response = client._request("GET", f"/api/product/{product_id}/categories")
            if isinstance(categories_response, dict) and "data" in categories_response:
                for cat_item in categories_response.get("data", []):
                    if isinstance(cat_item, dict):
                        cat_id = cat_item.get("id")
                        if cat_id:
                            category_ids.append(cat_id)
        except Exception:
            pass
    
    # Определяем leaf категорию из categories
    leaf_category_id = None
    if category_ids:
        for cat_id in category_ids:
            if is_leaf_category(client, cat_id):
                leaf_category_id = cat_id
                break
        # Если не нашли leaf, берем последнюю
        if not leaf_category_id:
            leaf_category_id = category_ids[-1]
    
    # Получаем полную цепочку для leaf
    category_chain = []
    if leaf_category_id:
        category_chain = get_category_chain(client, leaf_category_id)
    
    # КАНОНИЧЕСКАЯ ПРОВЕРКА CATEGORIES:
    # Shopware 6 REST API НЕ сохраняет visibility.categoryId через POST/PATCH /api/product-visibility.
    # Это системное ограничение Shopware 6, а не баг.
    # Breadcrumb определяется внутренней логикой storefront на основе product.categories.
    # 
    # Categories считаются OK, если:
    # a) product.categories.length > 0 (проверяется через GET /api/product/{id}/categories)
    # 
    # ПРОВЕРКА visibility.categoryId ЗАПРЕЩЕНА в проекте.
    # Categories проверяются НЕЗАВИСИМО от Visibility (для batch-импорта).
    
    cat_has_categories = len(category_ids) > 0
    categories_status = "OK" if cat_has_categories else "FAIL"
    
    print(f"  Статус: [{categories_status}]")
    print(f"  Всего категорий: {len(category_ids)}")
    print(f"  Category IDs: {category_ids}")
    print(f"  Leaf категория: {leaf_category_id or 'N/A'}")
    print(f"  Полная цепочка: {category_chain}")
    print(f"  Примечание: visibility.categoryId не проверяется (ограничение Shopware 6 REST API)")
    print()
    
    # ============================================
    # 5) PRICES
    # ============================================
    print("5) PRICES")
    print("-" * 80)
    
    # Базовая цена
    base_price = attributes.get("price", [])
    base_price_value = None
    if isinstance(base_price, list) and len(base_price) > 0:
        base_price_obj = base_price[0]
        if isinstance(base_price_obj, dict):
            base_price_value = base_price_obj.get("gross")
    
    print(f"  Базовая цена: {base_price_value or 'N/A'}")
    
    # Получаем marketplace price rule ID и имя
    marketplace_rule_id = None
    marketplace_rule_name = None
    try:
        marketplace_rule_id = client.find_rule_by_name_normalized("Marketplace Price")
    except:
        pass
    
    # Если не нашли через нормализованный поиск, пробуем прямой поиск
    if not marketplace_rule_id:
        try:
            rule_search = client._request(
                "POST",
                "/api/search/rule",
                json={
                    "filter": [{"field": "name", "type": "equals", "value": "Marketplace Price"}],
                    "limit": 1
                }
            )
            if isinstance(rule_search, dict) and "data" in rule_search:
                rules = rule_search.get("data", [])
                if rules:
                    marketplace_rule_id = rules[0].get("id")
        except:
            pass
    
    # Получаем имя правила
    if marketplace_rule_id:
        try:
            rule_response = client._request("GET", f"/api/rule/{marketplace_rule_id}")
            if isinstance(rule_response, dict) and "data" in rule_response:
                rule_data = rule_response["data"]
                if isinstance(rule_data, dict):
                    rule_attrs = rule_data.get("attributes", {})
                    marketplace_rule_name = rule_attrs.get("name")
                    if not marketplace_rule_name:
                        marketplace_rule_name = rule_data.get("name")
        except:
            marketplace_rule_name = "Marketplace Price"  # Fallback
    
    # Получаем advanced prices ТОЛЬКО через Search API (канонический способ)
    all_prices = []
    try:
        price_search = client._request(
            "POST",
            "/api/search/product-price",
            json={
                "filter": [{"field": "productId", "type": "equals", "value": product_id}],
                "limit": 100,
                "includes": {"product_price": ["id", "productId", "ruleId", "quantityStart", "price"]},
            }
        )
        if isinstance(price_search, dict) and "data" in price_search:
            raw_prices = price_search.get("data", [])
            # Извлекаем данные из Search API формата (может быть в attributes или напрямую)
            for price in raw_prices:
                price_data = {}
                if isinstance(price, dict):
                    # Проверяем, есть ли attributes
                    if "attributes" in price:
                        attrs = price["attributes"]
                        price_data["id"] = price.get("id")
                        price_data["productId"] = attrs.get("productId") or price.get("productId")
                        price_data["ruleId"] = attrs.get("ruleId") or price.get("ruleId")
                        price_data["quantityStart"] = attrs.get("quantityStart") or price.get("quantityStart", 0)
                        price_data["price"] = attrs.get("price") or price.get("price", [])
                    else:
                        # Данные напрямую в объекте
                        price_data = price
                all_prices.append(price_data)
    except Exception as e:
        print(f"  [ERROR] Ошибка получения prices: {e}")
        all_prices = []
    
    # Фильтруем marketplace prices по ruleId или по имени правила
    marketplace_prices = []
    for price in all_prices:
        p_rule_id = price.get("ruleId")
        # Сначала пробуем сравнить по ruleId
        if p_rule_id and marketplace_rule_id:
            if str(p_rule_id).lower() == str(marketplace_rule_id).lower():
                marketplace_prices.append(price)
                continue
        
        # Если не совпало по ruleId, проверяем по имени правила
        if p_rule_id:
            try:
                rule_resp = client._request("GET", f"/api/rule/{p_rule_id}")
                if isinstance(rule_resp, dict) and "data" in rule_resp:
                    rule_data = rule_resp["data"]
                    if isinstance(rule_data, dict):
                        rule_attrs = rule_data.get("attributes", {})
                        rule_name = rule_attrs.get("name") or rule_data.get("name", "")
                        if rule_name == "Marketplace Price":
                            marketplace_prices.append(price)
                            if not marketplace_rule_id:
                                marketplace_rule_id = p_rule_id
                            if not marketplace_rule_name:
                                marketplace_rule_name = rule_name
            except:
                pass
    
    # Проверяем условие OK: ровно 1 запись, rule == "Marketplace Price", quantityStart == 1
    mp_count = len(marketplace_prices)
    mp_quantity_start = marketplace_prices[0].get("quantityStart", 0) if mp_count > 0 else 0
    # Получаем имя правила для первой marketplace price, если еще не получено
    if mp_count > 0 and not marketplace_rule_name:
        mp_rule_id = marketplace_prices[0].get("ruleId")
        if mp_rule_id:
            try:
                rule_resp = client._request("GET", f"/api/rule/{mp_rule_id}")
                if isinstance(rule_resp, dict) and "data" in rule_resp:
                    rule_data = rule_resp["data"]
                    if isinstance(rule_data, dict):
                        rule_attrs = rule_data.get("attributes", {})
                        marketplace_rule_name = rule_attrs.get("name") or rule_data.get("name", "")
            except:
                pass
    mp_rule_correct = (marketplace_rule_name == "Marketplace Price") if marketplace_rule_name else False
    
    prices_status = "OK" if (mp_count == 1 and mp_quantity_start == 1 and mp_rule_correct) else "FAIL"
    
    print(f"  Всего advanced prices: {len(all_prices)}")
    print(f"  Marketplace prices: {mp_count} (ожидается: 1)")
    print(f"  Rule: {marketplace_rule_name or 'N/A'} (ожидается: Marketplace Price)")
    print(f"  quantityStart: {mp_quantity_start} (ожидается: 1)")
    
    for price in all_prices:
        rule_id = price.get("ruleId", "N/A")
        quantity_start = price.get("quantityStart", 0)
        price_array = price.get("price", [])
        price_value = None
        if isinstance(price_array, list) and len(price_array) > 0:
            price_obj = price_array[0]
            if isinstance(price_obj, dict):
                price_value = price_obj.get("gross")
        print(f"    - ruleId: {rule_id}, quantityStart: {quantity_start}, price: {price_value}")
    
    print(f"  Статус: [{prices_status}]")
    print()
    
    # ============================================
    # 6) IDENTIFIERS
    # ============================================
    print("6) IDENTIFIERS")
    print("-" * 80)
    
    product_number = product_data.get("productNumber") or attributes.get("productNumber", "")
    manufacturer_number = product_data.get("manufacturerNumber") or attributes.get("manufacturerNumber", "")
    ean = product_data.get("ean") or attributes.get("ean", "")
    custom_fields = product_data.get("customFields", {}) or attributes.get("customFields", {})
    if not isinstance(custom_fields, dict):
        custom_fields = {}
    internal_barcode = custom_fields.get("internal_barcode", "")
    
    identifiers_status = "OK"
    if ean:
        identifiers_status = "FAIL"  # EAN должен быть пустым
    
    print(f"  Статус: [{identifiers_status}]")
    print(f"  productNumber (SKU): {product_number}")
    print(f"  manufacturerNumber: {manufacturer_number or 'N/A'}")
    print(f"  ean (GTIN/EAN): {ean or 'NULL'} {'[FAIL - должен быть пустым]' if ean else '[OK]'}")
    print(f"  customFields.internal_barcode: {internal_barcode or 'N/A'}")
    print()
    
    # ============================================
    # 7) STOCK & STATUS
    # ============================================
    print("7) STOCK & STATUS")
    print("-" * 80)
    
    active = product_data.get("active") or attributes.get("active", False)
    stock = product_data.get("stock") or attributes.get("stock", 0)
    
    stock_status = "OK" if (active and stock > 0) else "FAIL"
    
    print(f"  Статус: [{stock_status}]")
    print(f"  active: {active}")
    print(f"  stock (quantity): {stock}")
    print()
    
    # ============================================
    # ИТОГОВЫЙ ЧЕКЛИСТ
    # ============================================
    print("=" * 80)
    print("ИТОГОВЫЙ ЧЕКЛИСТ")
    print("=" * 80)
    
    # Предварительно вычисляем статусы для manufacturerNumber и internal_barcode
    # (они будут использованы в детальном чеклисте)
    mpn_actual_pre = manufacturer_number or ""
    mpn_status_pre = "OK" if (mpn_actual_pre and isinstance(mpn_actual_pre, str) and len(mpn_actual_pre.strip()) > 0) else "FAIL"
    barcode_actual_pre = internal_barcode or ""
    barcode_status_pre = "OK" if (barcode_actual_pre and isinstance(barcode_actual_pre, str) and len(barcode_actual_pre.strip()) > 0) else "FAIL"
    
    checklist = {
        "manufacturerNumber (RELAXED)": mpn_status_pre,
        "ean (GTIN/EAN) (STRICT)": identifiers_status,
        "customFields.internal_barcode (RELAXED)": barcode_status_pre,
        "Tax (STRICT)": tax_status,
        "Visibility (STRICT)": visibility_status,
        "Categories (STRICT)": categories_status,
        "Marketplace price (STRICT)": prices_status,
        "Manufacturer (RELAXED)": manufacturer_status,
        "Stock & Status (STRICT)": stock_status,
    }
    
    for item, status in checklist.items():
        symbol = "[OK]" if status == "OK" else ("[WARN]" if status == "WARNING" else "[FAIL]")
        print(f"  {symbol} {item}")
    
    print()
    print("=" * 80)
    
    # ============================================
    # ДЕТАЛЬНЫЙ ЧЕКЛИСТ СООТВЕТСТВИЯ КАНОНИЧЕСКОЙ МОДЕЛИ
    # ============================================
    print()
    print("=" * 80)
    print("ДЕТАЛЬНЫЙ ЧЕКЛИСТ СООТВЕТСТВИЯ КАНОНИЧЕСКОЙ МОДЕЛИ")
    print("=" * 80)
    print()
    
    # 1) manufacturerNumber (RELAXED: наличие и формат)
    mpn_actual = manufacturer_number or ""
    mpn_status = "OK" if (mpn_actual and isinstance(mpn_actual, str) and len(mpn_actual.strip()) > 0) else "FAIL"
    
    # 2) ean (GTIN/EAN) (STRICT: должен быть пустым)
    ean_actual = ean or ""
    ean_status = "OK" if not ean_actual else "FAIL"
    
    # 3) customFields.internal_barcode (RELAXED: наличие и формат)
    barcode_actual = internal_barcode or ""
    barcode_status = "OK" if (barcode_actual and isinstance(barcode_actual, str) and len(barcode_actual.strip()) > 0) else "FAIL"
    
    # 4) Tax (STRICT: должен быть Standard rate, 19%)
    tax_name_actual = tax_info.get("name", "N/A")
    tax_rate_actual = tax_info.get("taxRate", 0.0)
    tax_status_detailed = "OK" if (tax_name_actual == "Standard rate" and abs(tax_rate_actual - 19.0) < 0.1) else "FAIL"
    
    # 5) Visibilities (STRICT: ровно 1 запись, Storefront, visibility=30)
    vis_count_actual = len(visibilities)
    vis_has_storefront = storefront_visibility is not None
    vis_value_actual = storefront_visibility.get("visibility", 0) if storefront_visibility else 0
    vis_status_detailed = "OK" if (vis_count_actual == 1 and vis_has_storefront and vis_value_actual == 30) else "FAIL"
    
    # 6) Categories (STRICT: наличие через GET /api/product/{id}/categories)
    # КАНОНИЧЕСКАЯ ПРОВЕРКА: product.categories > 0 (независимо от Visibility)
    # visibility.categoryId НЕ проверяется (ограничение Shopware 6 REST API)
    cat_has_categories = len(category_ids) > 0
    cat_status_detailed = "OK" if cat_has_categories else "FAIL"
    
    # 7) Marketplace price (STRICT: ровно 1 запись, rule="Marketplace Price", quantityStart=1)
    mp_count_actual = len(marketplace_prices)
    mp_quantity_start_actual = marketplace_prices[0].get("quantityStart", 0) if mp_count_actual > 0 else 0
    mp_rule_name_actual = marketplace_rule_name or "N/A"
    mp_status_detailed = "OK" if (mp_count_actual == 1 and mp_quantity_start_actual == 1 and mp_rule_name_actual == "Marketplace Price") else "FAIL"
    
    # 8) Manufacturer (RELAXED: наличие manufacturerId, name не пусто, дублей=0)
    man_name_actual = manufacturer_name
    man_duplicates_actual = manufacturer_count
    man_status_detailed = "OK" if (manufacturer_id and man_name_actual and man_name_actual != "N/A" and man_duplicates_actual == 0) else "FAIL"
    
    # Вывод детального чеклиста
    print("№  | Параметр                          | Режим    | Статус")
    print("-" * 80)
    print(f"1  | manufacturerNumber                | RELAXED  | [{mpn_status}]")
    print(f"2  | ean (GTIN/EAN)                    | STRICT   | [{ean_status}]")
    print(f"3  | customFields.internal_barcode      | RELAXED  | [{barcode_status}]")
    print(f"4  | Tax                               | STRICT   | [{tax_status_detailed}]")
    print(f"5  | Visibilities                      | STRICT   | [{vis_status_detailed}]")
    print(f"6  | Categories                        | STRICT   | [{cat_status_detailed}]")
    print(f"7  | Marketplace price                 | STRICT   | [{mp_status_detailed}]")
    print(f"8  | Manufacturer                      | RELAXED  | [{man_status_detailed}]")
    print("=" * 80)
    print()
    
    # Детальная информация по каждому пункту
    print("ДЕТАЛЬНАЯ ИНФОРМАЦИЯ:")
    print("-" * 80)
    print(f"1) manufacturerNumber (RELAXED): [{mpn_status}]")
    print(f"   Ожидается: наличие (не пусто), формат (строка)")
    print(f"   Фактически: {mpn_actual or 'N/A'}")
    print()
    print(f"2) ean (GTIN/EAN) (STRICT): [{ean_status}]")
    print(f"   Ожидается: NULL / пусто")
    print(f"   Фактически: {ean_actual or 'NULL'}")
    print()
    print(f"3) customFields.internal_barcode (RELAXED): [{barcode_status}]")
    print(f"   Ожидается: наличие (не пусто), формат (строка)")
    print(f"   Фактически: {barcode_actual or 'N/A'}")
    print()
    print(f"4) Tax (STRICT): [{tax_status_detailed}]")
    print(f"   Ожидается: name='Standard rate', rate=19%")
    print(f"   Фактически: name='{tax_name_actual}', rate={tax_rate_actual}%")
    print()
    print(f"5) Visibilities (STRICT): [{vis_status_detailed}]")
    print(f"   Ожидается: ровно 1 запись, Storefront есть, visibility=30")
    print(f"   Фактически: количество={vis_count_actual}, Storefront={'есть' if vis_has_storefront else 'нет'}, visibility={vis_value_actual}")
    print()
    print(f"6) Categories (STRICT): [{cat_status_detailed}]")
    print(f"   Ожидается: категории есть (через GET /api/product/{{id}}/categories)")
    print(f"   Фактически: категорий={len(category_ids)}")
    print(f"   Примечание: visibility.categoryId не проверяется (ограничение Shopware 6 REST API)")
    print()
    print(f"7) Marketplace price (STRICT): [{mp_status_detailed}]")
    print(f"   Ожидается: ровно 1 запись, rule='Marketplace Price', quantityStart=1")
    print(f"   Фактически: количество={mp_count_actual}, rule='{mp_rule_name_actual}', quantityStart={mp_quantity_start_actual}")
    print()
    print(f"8) Manufacturer (RELAXED): [{man_status_detailed}]")
    print(f"   Ожидается: manufacturerId != null, name не пусто, дублей=0")
    print(f"   Фактически: name='{man_name_actual}', дублей={man_duplicates_actual}")
    print()
    print("=" * 80)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())


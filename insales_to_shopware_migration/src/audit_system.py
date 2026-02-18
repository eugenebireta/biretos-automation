"""
Аудит системы Shopware 6: Manufacturers, Marketplace Price Rules, Products.
Только чтение данных, без изменений.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from import_utils import ROOT, load_json

REPORTS_DIR = ROOT / "_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def audit_manufacturers(client: ShopwareClient) -> List[Dict[str, Any]]:
    """ШАГ A: Аудит Manufacturers с именем 'Boeing'."""
    print("=" * 80)
    print("ШАГ A: АУДИТ MANUFACTURERS")
    print("=" * 80)
    print()
    
    # Ищем все manufacturers с именем "Boeing" (нормализованно)
    print("1) Поиск manufacturers с именем 'Boeing'...")
    
    normalized_target = client._normalize_name("Boeing")
    
    try:
        # В Shopware 6 используется /api/product-manufacturer для поиска
        response = client._request(
            "POST",
            "/api/search/product-manufacturer",
            json={
                "filter": [
                    {"field": "name", "type": "contains", "value": "Boeing"}
                ],
                "limit": 100,
            }
        )
        
        manufacturers = []
        if isinstance(response, dict) and "data" in response:
            for item in response.get("data", []):
                manufacturer_id = item.get("id")
                attrs = item.get("attributes", {})
                name = attrs.get("name") or item.get("name", "")
                
                # Проверяем нормализованное имя
                if client._normalize_name(name) == normalized_target:
                    # Подсчитываем количество товаров
                    product_count = 0
                    try:
                        product_search = client._request(
                            "POST",
                            "/api/search/product",
                            json={
                                "filter": [
                                    {"field": "manufacturerId", "type": "equals", "value": manufacturer_id}
                                ],
                                "limit": 1,
                                "totalCountMode": 1,  # Точный подсчёт
                            }
                        )
                        if isinstance(product_search, dict):
                            product_count = product_search.get("total", 0)
                    except Exception as e:
                        # Пробуем через GET /api/product-manufacturer/{id}
                        try:
                            mfr_response = client._request("GET", f"/api/product-manufacturer/{manufacturer_id}")
                            if isinstance(mfr_response, dict):
                                mfr_data = mfr_response.get("data", {})
                                mfr_attrs = mfr_data.get("attributes", {})
                                # В некоторых версиях Shopware есть поле productCount
                                product_count = mfr_attrs.get("productCount", 0)
                        except Exception:
                            pass
                    
                    manufacturers.append({
                        "id": manufacturer_id,
                        "name": name,
                        "product_count": product_count
                    })
        
        # Сортируем по product_count DESC
        manufacturers.sort(key=lambda x: x["product_count"], reverse=True)
        
        print(f"   [OK] Найдено manufacturers: {len(manufacturers)}")
        print()
        
        return manufacturers
        
    except Exception as e:
        print(f"   [ERROR] Ошибка поиска manufacturers: {e}")
        return []


def audit_marketplace_rules(client: ShopwareClient) -> List[Dict[str, Any]]:
    """ШАГ B: Аудит Marketplace Price Rules."""
    print("=" * 80)
    print("ШАГ B: АУДИТ MARKETPLACE PRICE RULES")
    print("=" * 80)
    print()
    
    # Ищем все rules с именем "Marketplace Price"
    print("1) Поиск rules с именем 'Marketplace Price'...")
    
    normalized_target = client._normalize_name("Marketplace Price")
    
    try:
        response = client._request(
            "POST",
            "/api/search/rule",
            json={
                "filter": [
                    {"field": "name", "type": "contains", "value": "Marketplace Price"}
                ],
                "limit": 100,
            }
        )
        
        rules = []
        if isinstance(response, dict) and "data" in response:
            for item in response.get("data", []):
                rule_id = item.get("id")
                attrs = item.get("attributes", {})
                name = attrs.get("name") or item.get("name", "")
                
                # Проверяем нормализованное имя
                if client._normalize_name(name) == normalized_target:
                    # Подсчитываем количество product-price записей
                    price_count = 0
                    unique_products = set()
                    
                    try:
                        price_search = client._request(
                            "POST",
                            "/api/search/product-price",
                            json={
                                "filter": [
                                    {"field": "ruleId", "type": "equals", "value": rule_id}
                                ],
                                "limit": 500,  # Максимальный лимит Shopware
                                "totalCountMode": 1,
                            }
                        )
                        if isinstance(price_search, dict):
                            price_count = price_search.get("total", 0)
                            # Собираем уникальные productId
                            for price_item in price_search.get("data", []):
                                price_attrs = price_item.get("attributes", {})
                                product_id = price_attrs.get("productId") or price_item.get("productId")
                                if product_id:
                                    unique_products.add(product_id)
                    except Exception as e:
                        print(f"   [WARNING] Ошибка подсчёта prices для rule {rule_id}: {e}")
                    
                    rules.append({
                        "ruleId": rule_id,
                        "name": name,
                        "price_count": price_count,
                        "unique_products": len(unique_products)
                    })
        
        print(f"   [OK] Найдено rules: {len(rules)}")
        print()
        
        return rules
        
    except Exception as e:
        print(f"   [ERROR] Ошибка поиска rules: {e}")
        return []


def audit_products_sample(client: ShopwareClient, manufacturer_id: str) -> List[Dict[str, Any]]:
    """ШАГ C: Аудит 20 случайных товаров Boeing."""
    print("=" * 80)
    print("ШАГ C: АУДИТ ТОВАРОВ (SAMPLE)")
    print("=" * 80)
    print()
    
    print(f"1) Поиск товаров с manufacturerId = {manufacturer_id}...")
    
    try:
        # Получаем товары Boeing (используем manufacturer.name для более надёжного поиска)
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [
                    {"field": "manufacturer.name", "type": "equals", "value": "Boeing"}
                ],
                "limit": 500,  # Максимальный лимит Shopware
                "includes": {"product": ["id", "productNumber", "manufacturerId"]},
            }
        )
        
        products = []
        if isinstance(response, dict) and "data" in response:
            all_products = response.get("data", [])
            
            # Берём первые 20 (или все, если меньше)
            sample_size = min(20, len(all_products))
            sample_products = all_products[:sample_size]
            
            print(f"   [OK] Найдено товаров: {len(all_products)}, берём sample: {sample_size}")
            print()
            
            for i, item in enumerate(sample_products, 1):
                product_id = item.get("id")
                attrs = item.get("attributes", {})
                sku = attrs.get("productNumber") or item.get("productNumber", "")
                mfr_id = attrs.get("manufacturerId") or item.get("manufacturerId", "")
                
                print(f"   [{i}/{sample_size}] Обработка SKU: {sku}...", end=" ", flush=True)
                
                # Подсчитываем marketplace prices
                marketplace_prices_count = 0
                rule_ids = set()
                
                try:
                    price_search = client._request(
                        "POST",
                        "/api/search/product-price",
                        json={
                            "filter": [
                                {"field": "productId", "type": "equals", "value": product_id}
                            ],
                            "limit": 100,
                        }
                    )
                    if isinstance(price_search, dict) and "data" in price_search:
                        for price_item in price_search.get("data", []):
                            price_attrs = price_item.get("attributes", {})
                            rule_id = price_attrs.get("ruleId") or price_item.get("ruleId")
                            if rule_id:
                                rule_ids.add(rule_id)
                                # Проверяем, является ли это Marketplace Price
                                try:
                                    rule_response = client._request("GET", f"/api/rule/{rule_id}")
                                    if isinstance(rule_response, dict):
                                        rule_data = rule_response.get("data", {})
                                        rule_attrs = rule_data.get("attributes", {})
                                        rule_name = rule_attrs.get("name") or rule_data.get("name", "")
                                        if client._normalize_name(rule_name) == client._normalize_name("Marketplace Price"):
                                            marketplace_prices_count += 1
                                except Exception:
                                    pass
                except Exception as e:
                    print(f"[ERROR: {str(e)[:30]}]", end=" ")
                
                # Получаем категории
                categories = []
                category_count = 0
                try:
                    product_response = client._request(
                        "GET",
                        f"/api/product/{product_id}",
                        params={"associations[categories]": "{}"}
                    )
                    if isinstance(product_response, dict):
                        product_data = product_response.get("data", {})
                        product_attrs = product_data.get("attributes", {})
                        categories_list = product_attrs.get("categories", [])
                        if categories_list:
                            for cat in categories_list:
                                cat_id = cat.get("id")
                                if cat_id:
                                    categories.append(cat_id)
                            category_count = len(categories)
                except Exception as e:
                    pass
                
                products.append({
                    "sku": sku,
                    "productId": product_id,
                    "manufacturerId": mfr_id,
                    "marketplace_prices_count": marketplace_prices_count,
                    "rule_ids": list(rule_ids),
                    "categories": categories,
                    "category_count": category_count
                })
                
                print("[OK]")
        
        print()
        return products
        
    except Exception as e:
        print(f"   [ERROR] Ошибка поиска товаров: {e}")
        return []


def save_report_manufacturers(manufacturers: List[Dict[str, Any]]):
    """Сохраняет отчёт по manufacturers."""
    file_path = REPORTS_DIR / "audit_manufacturers.md"
    
    with file_path.open("w", encoding="utf-8") as f:
        f.write("# Аудит Manufacturers: Boeing\n\n")
        f.write(f"**Дата:** {Path(__file__).stat().st_mtime}\n\n")
        f.write(f"**Всего найдено:** {len(manufacturers)}\n\n")
        f.write("## Таблица результатов\n\n")
        f.write("| ID | Name | Product Count |\n")
        f.write("|----|------|---------------|\n")
        
        for mfr in manufacturers:
            f.write(f"| {mfr['id']} | {mfr['name']} | {mfr['product_count']} |\n")
        
        f.write("\n## Детальная информация\n\n")
        for i, mfr in enumerate(manufacturers, 1):
            f.write(f"### {i}. {mfr['name']}\n\n")
            f.write(f"- **ID:** {mfr['id']}\n")
            f.write(f"- **Name:** {mfr['name']}\n")
            f.write(f"- **Product Count:** {mfr['product_count']}\n\n")
    
    print(f"[OK] Отчёт сохранен: {file_path}")


def save_report_marketplace_rules(rules: List[Dict[str, Any]]):
    """Сохраняет отчёт по Marketplace Price Rules."""
    file_path = REPORTS_DIR / "audit_marketplace_rules.md"
    
    with file_path.open("w", encoding="utf-8") as f:
        f.write("# Аудит Marketplace Price Rules\n\n")
        f.write(f"**Дата:** {Path(__file__).stat().st_mtime}\n\n")
        f.write(f"**Всего найдено:** {len(rules)}\n\n")
        f.write("## Таблица результатов\n\n")
        f.write("| Rule ID | Name | Price Count | Unique Products |\n")
        f.write("|---------|------|-------------|-----------------|\n")
        
        for rule in rules:
            f.write(f"| {rule['ruleId']} | {rule['name']} | {rule['price_count']} | {rule['unique_products']} |\n")
        
        f.write("\n## Детальная информация\n\n")
        for i, rule in enumerate(rules, 1):
            f.write(f"### {i}. {rule['name']}\n\n")
            f.write(f"- **Rule ID:** {rule['ruleId']}\n")
            f.write(f"- **Name:** {rule['name']}\n")
            f.write(f"- **Price Count:** {rule['price_count']}\n")
            f.write(f"- **Unique Products:** {rule['unique_products']}\n\n")
    
    print(f"[OK] Отчёт сохранен: {file_path}")


def save_report_products_sample(products: List[Dict[str, Any]]):
    """Сохраняет отчёт по sample товаров."""
    file_path = REPORTS_DIR / "audit_products_sample.md"
    
    with file_path.open("w", encoding="utf-8") as f:
        f.write("# Аудит товаров (Sample): Boeing\n\n")
        f.write(f"**Дата:** {Path(__file__).stat().st_mtime}\n\n")
        f.write(f"**Всего в sample:** {len(products)}\n\n")
        f.write("## Таблица результатов\n\n")
        f.write("| SKU | Manufacturer ID | Marketplace Prices | Rule IDs | Categories Count |\n")
        f.write("|-----|-----------------|-------------------|----------|------------------|\n")
        
        for product in products:
            rule_ids_str = ", ".join(product['rule_ids'][:3])
            if len(product['rule_ids']) > 3:
                rule_ids_str += f" ... (+{len(product['rule_ids']) - 3})"
            f.write(f"| {product['sku']} | {product['manufacturerId']} | {product['marketplace_prices_count']} | {rule_ids_str} | {product['category_count']} |\n")
        
        f.write("\n## Детальная информация\n\n")
        for i, product in enumerate(products, 1):
            f.write(f"### {i}. SKU: {product['sku']}\n\n")
            f.write(f"- **Product ID:** {product['productId']}\n")
            f.write(f"- **Manufacturer ID:** {product['manufacturerId']}\n")
            f.write(f"- **Marketplace Prices Count:** {product['marketplace_prices_count']}\n")
            f.write(f"- **Rule IDs:** {', '.join(product['rule_ids'])}\n")
            f.write(f"- **Categories:** {', '.join(product['categories'])}\n")
            f.write(f"- **Category Count:** {product['category_count']}\n\n")
    
    print(f"[OK] Отчёт сохранен: {file_path}")


def main():
    print("=" * 80)
    print("АУДИТ СИСТЕМЫ SHOPWARE 6")
    print("=" * 80)
    print()
    print("Режим: ТОЛЬКО ЧТЕНИЕ (без изменений)")
    print()
    
    # Загружаем конфигурацию
    config_data = load_json(ROOT / "config.json")
    shopware_data = config_data.get("shopware", {})
    config = ShopwareConfig(
        url=shopware_data.get("url", ""),
        access_key_id=shopware_data.get("access_key_id", ""),
        secret_access_key=shopware_data.get("secret_access_key", ""),
    )
    client = ShopwareClient(config)
    
    # ШАГ A: Manufacturers
    manufacturers = audit_manufacturers(client)
    if manufacturers:
        save_report_manufacturers(manufacturers)
        # Ищем manufacturer с товарами через поиск товаров Boeing
        main_manufacturer_id = None
        try:
            # Ищем товары с manufacturer name "Boeing"
            product_search = client._request(
                "POST",
                "/api/search/product",
                json={
                    "filter": [
                        {"field": "manufacturer.name", "type": "equals", "value": "Boeing"}
                    ],
                    "limit": 20,  # Берём больше для sample
                    "includes": {"product": ["manufacturerId"]},
                }
            )
            if isinstance(product_search, dict) and "data" in product_search:
                products = product_search.get("data", [])
                if products:
                    product_item = products[0]
                    attrs = product_item.get("attributes", {})
                    main_manufacturer_id = attrs.get("manufacturerId") or product_item.get("manufacturerId")
                    print(f"[INFO] Найден manufacturer с товарами: {main_manufacturer_id}")
        except Exception as e:
            print(f"[WARNING] Ошибка поиска manufacturer с товарами: {e}")
        
        if not main_manufacturer_id and manufacturers:
            # Если не нашли, используем первый
            main_manufacturer_id = manufacturers[0]["id"]
    else:
        print("[WARNING] Manufacturers не найдены, пропускаем шаг C")
        main_manufacturer_id = None
    
    print()
    
    # ШАГ B: Marketplace Price Rules
    rules = audit_marketplace_rules(client)
    if rules:
        save_report_marketplace_rules(rules)
    
    print()
    
    # ШАГ C: Products Sample
    if main_manufacturer_id:
        products = audit_products_sample(client, main_manufacturer_id)
        if products:
            save_report_products_sample(products)
    
    print()
    print("=" * 80)
    print("АУДИТ ЗАВЕРШЕН")
    print("=" * 80)
    print()
    print("Отчёты сохранены в:")
    print(f"  - {REPORTS_DIR / 'audit_manufacturers.md'}")
    print(f"  - {REPORTS_DIR / 'audit_marketplace_rules.md'}")
    print(f"  - {REPORTS_DIR / 'audit_products_sample.md'}")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

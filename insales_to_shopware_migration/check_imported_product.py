"""
Проверяет импортированный товар в Shopware
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from clients import ShopwareClient, ShopwareConfig

# Загружаем конфигурацию
config = json.load(open(Path(__file__).parent / "config.json", encoding="utf-8"))
shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

# Ищем товар по SKU
product_number = "500944170"
print(f"Поиск товара по SKU: {product_number}")

try:
    # Пробуем найти товар по SKU используя функцию из full_import.py
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    from full_import import find_product_by_number
    
    product_id = find_product_by_number(client, product_number)
    
    if product_id:
        print(f"\n✓ Товар найден по SKU:")
        print(f"  UUID: {product_id}")
        
        # Получаем полную информацию о товаре
        full_product = client._request("GET", f"/api/product/{product_id}")
        if full_product and "data" in full_product:
            product_data = full_product["data"]
            print(f"  SKU: {product_data.get('productNumber')}")
            print(f"  Название: {product_data.get('name')}")
            print(f"  mainCategoryId: {product_data.get('mainCategoryId')}")
            
            categories = product_data.get("categories", [])
            print(f"  categories (количество): {len(categories)}")
            if categories:
                print(f"  categories (UUID): {[cat.get('id') for cat in categories]}")
            
            main_category_id = product_data.get("mainCategoryId")
            expected_category_id = "e56b3914e6544f5a9f4fe29adb759c2e"
            
            print(f"\nПроверка категорий:")
            print(f"  Ожидаемый mainCategoryId: {expected_category_id}")
            print(f"  Фактический mainCategoryId: {main_category_id}")
            print(f"  ✓ mainCategoryId совпадает: {main_category_id == expected_category_id}")
            if categories:
                cat_ids = [cat.get('id') for cat in categories]
                is_only_leaf = len(categories) == 1 and cat_ids[0] == expected_category_id
                print(f"  ✓ categories содержит ТОЛЬКО leaf-категорию: {is_only_leaf}")
                if not is_only_leaf:
                    print(f"    Проблема: categories содержит {len(categories)} категорий, ожидалась 1")
                    print(f"    UUID категорий: {cat_ids}")
            else:
                print(f"  ✗ categories пуст")
    else:
        print("✗ Товар не найден")
    
    # Альтернативный способ поиска
    if not product_id:
        print("\nПробуем альтернативный способ поиска...")
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [{"field": "productNumber", "type": "equals", "value": product_number}],
                "includes": {"product": ["id", "productNumber", "name", "mainCategoryId", "categories"]},
                "limit": 1,
            },
        )
    
    if response.get("total") and response.get("data"):
        product = response["data"][0]
        product_id = product.get("id")
    else:
        # Если не найден по SKU, пробуем найти последние товары
        print("Товар не найден по SKU, ищем последние товары...")
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "limit": 5,
                "sort": [{"field": "createdAt", "order": "DESC"}],
                "includes": {"product": ["id", "productNumber", "name"]},
            },
        )
        if response.get("total") and response.get("data"):
            products = response["data"]
            print(f"Найдено последних товаров: {len(products)}")
            for p in products:
                print(f"  - {p.get('productNumber')}: {p.get('name')} (ID: {p.get('id')})")
            # Используем первый товар
            product_id = products[0].get("id") if products else None
        else:
            product_id = None
    
    if product_id:
        print(f"\n✓ Товар найден:")
        print(f"  UUID: {product_id}")
        
        # Получаем полную информацию о товаре
        full_product = client._request("GET", f"/api/product/{product_id}")
        if full_product and "data" in full_product:
            product_data = full_product["data"]
            print(f"  SKU: {product_data.get('productNumber')}")
            print(f"  Название: {product_data.get('name')}")
            print(f"  mainCategoryId: {product_data.get('mainCategoryId')}")
            
            categories = product_data.get("categories", [])
            print(f"  categories (количество): {len(categories)}")
            if categories:
                print(f"  categories (UUID): {[cat.get('id') for cat in categories]}")
            
            main_category_id = product_data.get("mainCategoryId")
            expected_category_id = "e56b3914e6544f5a9f4fe29adb759c2e"
            
            print(f"\nПроверка категорий:")
            print(f"  Ожидаемый mainCategoryId: {expected_category_id}")
            print(f"  Фактический mainCategoryId: {main_category_id}")
            print(f"  mainCategoryId совпадает: {main_category_id == expected_category_id}")
            if categories:
                cat_ids = [cat.get('id') for cat in categories]
                print(f"  categories содержит только leaf-категорию: {len(categories) == 1 and cat_ids[0] == expected_category_id}")
            else:
                print(f"  categories пуст")
    else:
        print("✗ Товар не найден")
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()


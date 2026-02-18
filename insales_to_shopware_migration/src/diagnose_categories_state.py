"""
ЧИСТАЯ ДИАГНОСТИКА состояния категорий в Shopware 6.
ТОЛЬКО чтение данных, НИКАКИХ изменений.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig


def load_config() -> ShopwareConfig:
    """Загружает конфигурацию Shopware."""
    config_path = Path(__file__).parent.parent / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Конфигурация не найдена: {config_path}")
    
    with config_path.open(encoding="utf-8") as f:
        config = json.load(f)
    
    sw = config["shopware"]
    return ShopwareConfig(
        url=sw["url"],
        access_key_id=sw["access_key_id"],
        secret_access_key=sw["secret_access_key"],
    )


def get_category(client: ShopwareClient, category_id: str) -> Optional[Dict[str, Any]]:
    """Получает категорию по ID."""
    try:
        response = client._request("GET", f"/api/category/{category_id}")
        if isinstance(response, dict) and "data" in response:
            return response["data"]
        return response
    except Exception:
        return None


def check_category_hierarchy(client: ShopwareClient, category_id: str) -> Dict[str, Any]:
    """Проверяет иерархию категории."""
    cat = get_category(client, category_id)
    if not cat:
        return {"exists": False}
    
    parent_id = cat.get("parentId")
    child_count = cat.get("childCount", 0)
    
    # Проверяем наличие детей через API
    children_response = client._request(
        "POST",
        "/api/search/category",
        json={
            "filter": [
                {"field": "parentId", "type": "equals", "value": category_id},
            ],
            "limit": 1,
        },
    )
    
    has_children = False
    if isinstance(children_response, dict):
        has_children = children_response.get("total", 0) > 0
    
    return {
        "exists": True,
        "id": category_id,
        "name": cat.get("name", ""),
        "parentId": parent_id,
        "childCount": child_count,
        "has_children": has_children,
        "is_leaf": not has_children and child_count == 0,
    }


def get_product_full(client: ShopwareClient, product_id: str) -> Optional[Dict[str, Any]]:
    """Получает полные данные товара."""
    try:
        response = client._request(
            "GET",
            f"/api/product/{product_id}",
            params={
                "associations[categories]": "{}",
                "associations[visibilities]": "{}",
            },
        )
        if isinstance(response, dict) and "data" in response:
            return response["data"]
        return response
    except Exception:
        return None


def get_product_visibilities(client: ShopwareClient, product_id: str) -> List[Dict[str, Any]]:
    """Получает все visibilities товара."""
    try:
        response = client._request(
            "POST",
            "/api/search/product-visibility",
            json={
                "filter": [
                    {"field": "productId", "type": "equals", "value": product_id},
                ],
                "limit": 100,
            },
        )
        
        if isinstance(response, dict) and "data" in response:
            return response.get("data", [])
        return []
    except Exception:
        return []


def search_products_by_category(client: ShopwareClient, category_id: str) -> Dict[str, Any]:
    """Ищет товары по категории через Search API."""
    try:
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [
                    {"field": "categories.id", "type": "equals", "value": category_id},
                ],
                "limit": 10,
            },
        )
        
        if isinstance(response, dict):
            return {
                "total": response.get("total", 0),
                "count": len(response.get("data", [])),
                "product_ids": [p.get("id") for p in response.get("data", []) if p.get("id")],
            }
        return {"total": 0, "count": 0, "product_ids": []}
    except Exception as e:
        return {"error": str(e)}


def main():
    """Основная функция диагностики."""
    print("=" * 80)
    print("ДИАГНОСТИКА СОСТОЯНИЯ КАТЕГОРИЙ В SHOPWARE 6")
    print("=" * 80)
    print()
    
    # Загружаем конфигурацию
    try:
        config = load_config()
        client = ShopwareClient(config)
    except Exception as e:
        print(f"[ERROR] Не удалось загрузить конфигурацию: {e}")
        return
    
    # Получаем storefront sales channel ID
    try:
        storefront_sales_channel_id = client.get_storefront_sales_channel_id()
        print(f"[FACT] Storefront Sales Channel ID: {storefront_sales_channel_id}")
    except Exception as e:
        print(f"[ERROR] Не удалось получить storefront sales channel ID: {e}")
        storefront_sales_channel_id = None
    
    print()
    
    # 1. КАТЕГОРИИ КАК СУЩНОСТИ
    print("=" * 80)
    print("1. КАТЕГОРИИ КАК СУЩНОСТИ")
    print("=" * 80)
    print()
    
    # Загружаем migration_map для проверки категорий из InSales
    map_path = Path(__file__).parent.parent / "migration_map.json"
    if map_path.exists():
        with map_path.open(encoding="utf-8") as f:
            migration_map = json.load(f)
        
        categories_map = migration_map.get("categories", {})
        print(f"[FACT] Категорий в migration_map.json: {len(categories_map)}")
        print()
        
        # Проверяем первые 5 категорий
        sample_categories = list(categories_map.items())[:5]
        for insales_id, shopware_id in sample_categories:
            print(f"Категория InSales {insales_id} -> Shopware {shopware_id}:")
            hierarchy = check_category_hierarchy(client, shopware_id)
            if hierarchy.get("exists"):
                print(f"  [FACT] exists: True")
                print(f"  [FACT] name: {hierarchy.get('name', 'N/A')}")
                print(f"  [FACT] parentId: {hierarchy.get('parentId', 'None')}")
                print(f"  [FACT] childCount: {hierarchy.get('childCount', 0)}")
                print(f"  [FACT] has_children (API check): {hierarchy.get('has_children', False)}")
                print(f"  [FACT] is_leaf: {hierarchy.get('is_leaf', False)}")
            else:
                print(f"  [FACT] exists: False")
            print()
    else:
        print("[WARNING] migration_map.json не найден")
    
    # 2. ТОВАРЫ → КАТЕГОРИИ (ДАННЫЕ)
    print("=" * 80)
    print("2. ТОВАРЫ -> КАТЕГОРИИ (ДАННЫЕ)")
    print("=" * 80)
    print()
    
    # Получаем несколько товаров
    print("[INFO] Загрузка товаров из Shopware...")
    products_response = client._request(
        "POST",
        "/api/search/product",
        json={
            "limit": 5,
            "includes": {
                "product": ["id", "productNumber", "name"],
            },
        },
    )
    
    product_ids = []
    if isinstance(products_response, dict) and "data" in products_response:
        products = products_response["data"]
        product_ids = [p.get("id") for p in products if p.get("id")]
        print(f"[FACT] Загружено товаров для проверки: {len(product_ids)}")
        print()
    
    for product_id in product_ids[:5]:
        print(f"Товар ID: {product_id}")
        product = get_product_full(client, product_id)
        
        if not product:
            print("  [FACT] GET /api/product/{id}: товар не найден")
            print()
            continue
        
        product_number = product.get("productNumber", "N/A")
        product_name = product.get("name", "N/A")
        print(f"  [FACT] productNumber: {product_number}")
        print(f"  [FACT] name: {product_name}")
        
        # categories
        relationships = product.get("relationships", {})
        categories_rel = relationships.get("categories", {})
        category_ids = []
        if categories_rel:
            category_ids = [c.get("id") for c in categories_rel.get("data", []) if c.get("id")]
        
        print(f"  [FACT] categories (relationships.data): {category_ids}")
        print(f"  [FACT] categories count: {len(category_ids)}")
        
        # mainCategoryId
        main_category_id = product.get("mainCategoryId")
        print(f"  [FACT] mainCategoryId: {main_category_id}")
        
        # visibilities
        visibilities = get_product_visibilities(client, product_id)
        print(f"  [FACT] visibilities count: {len(visibilities)}")
        
        storefront_visibility = None
        for vis in visibilities:
            vis_data = vis.get("attributes", {}) if "attributes" in vis else vis
            sc_id = vis_data.get("salesChannelId")
            cat_id = vis_data.get("categoryId")
            visibility = vis_data.get("visibility")
            
            print(f"    visibility: salesChannelId={sc_id}, categoryId={cat_id}, visibility={visibility}")
            
            if sc_id == storefront_sales_channel_id:
                storefront_visibility = vis_data
                print(f"      [FACT] Это storefront visibility")
        
        if storefront_visibility:
            vis_cat_id = storefront_visibility.get("categoryId")
            vis_visibility = storefront_visibility.get("visibility")
            print(f"  [FACT] storefront visibility.categoryId: {vis_cat_id}")
            print(f"  [FACT] storefront visibility.visibility: {vis_visibility}")
            
            # Сравниваем с leaf-категорией
            if category_ids:
                # Находим leaf (проверяем каждую категорию)
                leaf_category_id = None
                for cat_id in category_ids:
                    hierarchy = check_category_hierarchy(client, cat_id)
                    if hierarchy.get("is_leaf"):
                        leaf_category_id = cat_id
                        break
                
                if leaf_category_id:
                    print(f"  [FACT] leaf category (из categories): {leaf_category_id}")
                    print(f"  [FACT] visibility.categoryId == leaf: {vis_cat_id == leaf_category_id}")
        else:
            print(f"  [FACT] storefront visibility: отсутствует")
        
        print()
    
    # 3. STOREFRONT-ЛОГИКА
    print("=" * 80)
    print("3. STOREFRONT-ЛОГИКА")
    print("=" * 80)
    print()
    
    if storefront_sales_channel_id:
        print(f"[FACT] Storefront Sales Channel ID: {storefront_sales_channel_id}")
        
        # Проверяем visibilities для всех проверенных товаров
        storefront_visibilities_count = 0
        storefront_visibilities_with_category = 0
        
        for product_id in product_ids[:5]:
            visibilities = get_product_visibilities(client, product_id)
            for vis in visibilities:
                vis_data = vis.get("attributes", {}) if "attributes" in vis else vis
                if vis_data.get("salesChannelId") == storefront_sales_channel_id:
                    storefront_visibilities_count += 1
                    if vis_data.get("categoryId"):
                        storefront_visibilities_with_category += 1
        
        print(f"[FACT] Товаров с storefront visibility: {storefront_visibilities_count}")
        print(f"[FACT] Товаров с storefront visibility.categoryId: {storefront_visibilities_with_category}")
    else:
        print("[FACT] Storefront Sales Channel ID: не определён")
    
    print()
    
    # 4. ПОИСК / ВЫБОРКА
    print("=" * 80)
    print("4. ПОИСК / ВЫБОРКА")
    print("=" * 80)
    print()
    
    # Берём первую категорию из migration_map
    if map_path.exists() and categories_map:
        sample_category_id = list(categories_map.values())[0]
        print(f"Тестовая категория: {sample_category_id}")
        
        # Проверяем иерархию
        hierarchy = check_category_hierarchy(client, sample_category_id)
        print(f"[FACT] Категория существует: {hierarchy.get('exists', False)}")
        print(f"[FACT] Категория is_leaf: {hierarchy.get('is_leaf', False)}")
        
        # Поиск товаров по этой категории
        search_result = search_products_by_category(client, sample_category_id)
        print(f"[FACT] Товаров в категории (Search API): {search_result.get('total', 0)}")
        print(f"[FACT] Товаров возвращено: {search_result.get('count', 0)}")
        if search_result.get("product_ids"):
            print(f"[FACT] Product IDs: {search_result['product_ids'][:5]}")
        
        # Если категория не leaf, проверяем поиск по parent
        if not hierarchy.get("is_leaf") and hierarchy.get("parentId"):
            parent_id = hierarchy.get("parentId")
            print()
            print(f"Родительская категория: {parent_id}")
            parent_search = search_products_by_category(client, parent_id)
            print(f"[FACT] Товаров в parent категории: {parent_search.get('total', 0)}")
    
    print()
    
    # 5. КЭШ / ИНДЕКСАЦИЯ (ТОЛЬКО ФАКТЫ)
    print("=" * 80)
    print("5. КЭШ / ИНДЕКСАЦИЯ (ТОЛЬКО ФАКТЫ)")
    print("=" * 80)
    print()
    
    # Проверяем время ответа Search API vs GET API
    # Search API (использует индексы)
    start = time.time()
    search_response = client._request(
        "POST",
        "/api/search/product",
        json={
            "limit": 1,
        },
    )
    search_time = time.time() - start
    
    # GET API (прямой доступ)
    if product_ids:
        start = time.time()
        get_response = client._request("GET", f"/api/product/{product_ids[0]}")
        get_time = time.time() - start
        
        print(f"[FACT] Search API время ответа: {search_time:.3f}s")
        print(f"[FACT] GET API время ответа: {get_time:.3f}s")
        print(f"[FACT] Search API использует индексы: True (DAL)")
    
    print()
    print("=" * 80)
    print("ДИАГНОСТИКА ЗАВЕРШЕНА")
    print("=" * 80)


if __name__ == "__main__":
    main()


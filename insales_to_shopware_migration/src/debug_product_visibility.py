"""
Отладочный скрипт для проверки product_visibility товаров.
Показывает детальную информацию о visibility для каждого товара.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from category_utils import get_category_chain, is_leaf_category


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


def get_all_products(client: ShopwareClient, limit: int = 5) -> List[Dict[str, Any]]:
    """Получает товары из Shopware."""
    try:
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "limit": limit,
                "includes": {
                    "product": [
                        "id",
                        "productNumber",
                        "name",
                        "categories",
                    ],
                },
            },
        )
        
        if isinstance(response, dict) and "data" in response:
            return response.get("data", [])
        return []
    except Exception as e:
        print(f"[ERROR] Ошибка при получении товаров: {e}")
        return []


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
                "includes": {
                    "product_visibility": [
                        "id",
                        "productId",
                        "salesChannelId",
                        "categoryId",
                        "visibility",
                    ],
                },
            },
        )
        
        if isinstance(response, dict) and "data" in response:
            return response.get("data", [])
        return []
    except Exception:
        return []


def find_leaf_category(client: ShopwareClient, product: Dict[str, Any]) -> Optional[str]:
    """Находит leaf-категорию для товара."""
    categories = product.get("categories", [])
    if not categories:
        return None
    
    category_ids = [cat.get("id") for cat in categories if cat.get("id")]
    if not category_ids:
        return None
    
    for cat_id in category_ids:
        if is_leaf_category(client, cat_id):
            return cat_id
    
    if category_ids:
        chain = get_category_chain(client, category_ids[-1])
        if chain:
            return chain[-1]
    
    return None


def main():
    """Основная функция отладки."""
    print("=" * 80)
    print("ОТЛАДКА PRODUCT_VISIBILITY")
    print("=" * 80)
    print()
    
    try:
        config = load_config()
        client = ShopwareClient(config)
    except Exception as e:
        print(f"[ERROR] Не удалось загрузить конфигурацию: {e}")
        return
    
    try:
        storefront_sales_channel_id = client.get_storefront_sales_channel_id()
        print(f"[INFO] Storefront Sales Channel ID: {storefront_sales_channel_id}")
    except Exception as e:
        print(f"[ERROR] Не удалось получить storefront sales channel ID: {e}")
        return
    
    print()
    print("[INFO] Загрузка товаров...")
    
    products = get_all_products(client, limit=5)
    print(f"[INFO] Загружено товаров: {len(products)}")
    print()
    
    for product in products:
        product_id = product.get("id", "")
        product_number = product.get("productNumber", "")
        product_name = product.get("name", "")
        
        print(f"Товар: {product_number} - {product_name}")
        print(f"  ID: {product_id}")
        
        # Категории товара
        categories = product.get("categories", [])
        category_ids = [cat.get("id") for cat in categories if cat.get("id")]
        print(f"  Категории (product.categories): {len(category_ids)}")
        for cat_id in category_ids:
            is_leaf = is_leaf_category(client, cat_id)
            print(f"    - {cat_id} (leaf: {is_leaf})")
        
        # Leaf категория
        leaf_category_id = find_leaf_category(client, product)
        print(f"  Leaf категория: {leaf_category_id}")
        
        # Visibilities
        visibilities = get_product_visibilities(client, product_id)
        print(f"  Visibilities: {len(visibilities)}")
        
        storefront_visibility = None
        for vis in visibilities:
            sc_id = vis.get("salesChannelId")
            cat_id = vis.get("categoryId")
            visibility = vis.get("visibility")
            
            print(f"    - Sales Channel: {sc_id}")
            print(f"      categoryId: {cat_id}")
            print(f"      visibility: {visibility}")
            
            if sc_id == storefront_sales_channel_id:
                storefront_visibility = vis
                print(f"      [STOREFRONT]")
        
        # Проверка
        print()
        if storefront_visibility:
            vis_cat_id = storefront_visibility.get("categoryId")
            vis_visibility = storefront_visibility.get("visibility")
            
            if vis_cat_id == leaf_category_id and vis_visibility == 30:
                print(f"  [OK] Visibility корректна")
            else:
                print(f"  [PROBLEM] Visibility некорректна:")
                if vis_cat_id != leaf_category_id:
                    print(f"    - categoryId: {vis_cat_id} (ожидается {leaf_category_id})")
                if vis_visibility != 30:
                    print(f"    - visibility: {vis_visibility} (ожидается 30)")
        else:
            print(f"  [PROBLEM] Visibility для storefront отсутствует")
        
        print()
        print("-" * 80)
        print()


if __name__ == "__main__":
    main()




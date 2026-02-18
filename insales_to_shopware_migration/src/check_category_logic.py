"""
Dry-run проверка канонической логики категорий в Shopware 6.

Проверяет:
1. Товар должен быть во ВСЕХ категориях цепочки (product.categories)
2. product_visibility.categoryId = самая глубокая категория (leaf)
3. mainCategoryId = leaf категория

Выводит статистику:
- Сколько товаров проверено
- Сколько имеют неверную mainCategoryId
- Сколько имеют неполную цепочку категорий
- Сколько имеют неверный categoryId в visibility
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


def get_all_products(client: ShopwareClient, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Получает все товары из Shopware."""
    all_products = []
    page = 1
    per_page = 100
    
    while True:
        try:
            response = client._request(
                "POST",
                "/api/search/product",
                json={
                    "limit": per_page,
                    "page": page,
                    "includes": {
                        "product": [
                            "id",
                            "productNumber",
                            "name",
                            "mainCategoryId",
                            "categories",
                        ],
                    },
                },
            )
            
            if isinstance(response, dict) and "data" in response:
                data = response.get("data", [])
                if not data:
                    break
                
                all_products.extend(data)
                
                if limit and len(all_products) >= limit:
                    all_products = all_products[:limit]
                    break
                
                if len(data) < per_page:
                    break
                
                page += 1
            else:
                break
        except Exception as e:
            print(f"[ERROR] Ошибка при получении товаров: {e}")
            break
    
    return all_products


def get_product_visibilities(client: ShopwareClient, product_id: str) -> List[Dict[str, Any]]:
    """Получает visibilities товара."""
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


def check_product_categories(
    client: ShopwareClient,
    product: Dict[str, Any],
    storefront_sales_channel_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Проверяет каноническую логику категорий для товара.
    
    Returns:
        Словарь с результатами проверки:
        {
            "product_id": str,
            "product_number": str,
            "product_name": str,
            "is_valid": bool,
            "issues": List[str],
            "main_category_id": Optional[str],
            "expected_main_category_id": Optional[str],
            "categories_count": int,
            "expected_categories_count": int,
            "visibility_category_id": Optional[str],
            "expected_visibility_category_id": Optional[str],
        }
    """
    product_id = product.get("id", "")
    product_number = product.get("productNumber", "")
    product_name = product.get("name", "")
    main_category_id = product.get("mainCategoryId")
    categories = product.get("categories", [])
    
    issues: List[str] = []
    
    # Получаем категории товара
    category_ids = [cat.get("id") for cat in categories if cat.get("id")]
    
    # Находим leaf категорию (самую глубокую)
    leaf_category_id = None
    if category_ids:
        # Проверяем каждую категорию, находим leaf
        for cat_id in category_ids:
            if is_leaf_category(client, cat_id):
                leaf_category_id = cat_id
                break
        
        # Если не нашли leaf среди категорий товара, берем последнюю (предполагаем, что она leaf)
        if not leaf_category_id:
            leaf_category_id = category_ids[-1]
    
    # Ожидаемая цепочка категорий
    expected_category_chain: List[str] = []
    if leaf_category_id:
        expected_category_chain = get_category_chain(client, leaf_category_id)
    
    # Проверка 1: mainCategoryId должен быть leaf категорией
    expected_main_category_id = leaf_category_id
    if main_category_id != expected_main_category_id:
        issues.append(
            f"mainCategoryId неверный: {main_category_id} (ожидается {expected_main_category_id})"
        )
    
    # Проверка 2: товар должен быть во ВСЕХ категориях цепочки
    expected_category_ids = set(expected_category_chain)
    actual_category_ids = set(category_ids)
    
    missing_categories = expected_category_ids - actual_category_ids
    extra_categories = actual_category_ids - expected_category_ids
    
    if missing_categories:
        issues.append(
            f"Отсутствуют категории цепочки: {list(missing_categories)}"
        )
    
    if extra_categories:
        # Это не критично, но стоит отметить
        issues.append(
            f"Лишние категории (не в цепочке): {list(extra_categories)}"
        )
    
    # Проверка 3: product_visibility.categoryId должен быть leaf категорией
    visibilities = get_product_visibilities(client, product_id)
    visibility_category_id = None
    
    if storefront_sales_channel_id:
        for vis in visibilities:
            if vis.get("salesChannelId") == storefront_sales_channel_id:
                visibility_category_id = vis.get("categoryId")
                break
    
    expected_visibility_category_id = leaf_category_id
    if visibility_category_id != expected_visibility_category_id:
        issues.append(
            f"product_visibility.categoryId неверный: {visibility_category_id} "
            f"(ожидается {expected_visibility_category_id})"
        )
    
    return {
        "product_id": product_id,
        "product_number": product_number,
        "product_name": product_name,
        "is_valid": len(issues) == 0,
        "issues": issues,
        "main_category_id": main_category_id,
        "expected_main_category_id": expected_main_category_id,
        "categories_count": len(category_ids),
        "expected_categories_count": len(expected_category_chain),
        "visibility_category_id": visibility_category_id,
        "expected_visibility_category_id": expected_visibility_category_id,
    }


def main():
    """Основная функция dry-run проверки."""
    print("=" * 80)
    print("DRY-RUN: Проверка канонической логики категорий в Shopware 6")
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
        print(f"[INFO] Storefront Sales Channel ID: {storefront_sales_channel_id}")
    except Exception as e:
        print(f"[WARNING] Не удалось получить storefront sales channel ID: {e}")
        storefront_sales_channel_id = None
    
    print()
    print("[INFO] Загрузка товаров из Shopware...")
    
    # Получаем все товары (можно ограничить для теста)
    products = get_all_products(client, limit=None)
    total_products = len(products)
    
    print(f"[INFO] Загружено товаров: {total_products}")
    print()
    
    if total_products == 0:
        print("[WARNING] Товары не найдены")
        return
    
    # Проверяем каждый товар
    print("[INFO] Проверка товаров...")
    print()
    
    results: List[Dict[str, Any]] = []
    valid_count = 0
    invalid_count = 0
    
    for idx, product in enumerate(products, 1):
        if idx % 100 == 0:
            print(f"[INFO] Проверено товаров: {idx}/{total_products}")
        
        result = check_product_categories(client, product, storefront_sales_channel_id)
        results.append(result)
        
        if result["is_valid"]:
            valid_count += 1
        else:
            invalid_count += 1
    
    print()
    print("=" * 80)
    print("РЕЗУЛЬТАТЫ ПРОВЕРКИ")
    print("=" * 80)
    print()
    
    print(f"Всего товаров проверено: {total_products}")
    print(f"  [OK] Валидных: {valid_count}")
    print(f"  [ERROR] Невалидных: {invalid_count}")
    print()
    
    # Группируем проблемы
    main_category_issues = 0
    categories_chain_issues = 0
    visibility_category_issues = 0
    
    for result in results:
        if not result["is_valid"]:
            for issue in result["issues"]:
                if "mainCategoryId" in issue:
                    main_category_issues += 1
                elif "Отсутствуют категории" in issue or "Лишние категории" in issue:
                    categories_chain_issues += 1
                elif "product_visibility.categoryId" in issue:
                    visibility_category_issues += 1
    
    print("Типы проблем:")
    print(f"  - Неверный mainCategoryId: {main_category_issues}")
    print(f"  - Неполная цепочка категорий: {categories_chain_issues}")
    print(f"  - Неверный categoryId в visibility: {visibility_category_issues}")
    print()
    
    # Показываем примеры проблемных товаров (первые 10)
    problematic = [r for r in results if not r["is_valid"]]
    if problematic:
        print("Примеры проблемных товаров (первые 10):")
        print()
        for result in problematic[:10]:
            print(f"SKU: {result['product_number']}")
            print(f"  Название: {result['product_name']}")
            print(f"  Проблемы:")
            for issue in result["issues"]:
                print(f"    - {issue}")
            print()
    
    # Сохраняем результаты в файл
    output_path = Path(__file__).parent.parent / "diagnostics" / "category_logic_check.json"
    output_path.parent.mkdir(exist_ok=True)
    
    summary = {
        "total_products": total_products,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "main_category_issues": main_category_issues,
        "categories_chain_issues": categories_chain_issues,
        "visibility_category_issues": visibility_category_issues,
        "problematic_products": [
            {
                "product_number": r["product_number"],
                "product_name": r["product_name"],
                "issues": r["issues"],
            }
            for r in problematic[:50]  # Сохраняем первые 50 проблемных
        ],
    }
    
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"[INFO] Результаты сохранены в: {output_path}")
    print()
    print("=" * 80)
    print("ПРОВЕРКА ЗАВЕРШЕНА")
    print("=" * 80)


if __name__ == "__main__":
    main()


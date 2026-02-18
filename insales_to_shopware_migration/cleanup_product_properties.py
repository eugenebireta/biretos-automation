"""
Очистка дублированных свойств у товаров в Shopware 6.

Скрипт находит товары с дублированными свойствами (одинаковые Property Group Options)
и удаляет дубликаты, оставляя только уникальные свойства.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent / "src"))

from clients import ShopwareClient, ShopwareConfig, ShopwareClientError


def get_product_with_properties(client: ShopwareClient, product_id: str) -> Dict[str, Any] | None:
    """Получает товар с его свойствами."""
    try:
        response = client._request(
            "GET",
            f"/api/product/{product_id}",
            params={
                "associations[properties]": "{}"
            }
        )
        
        if isinstance(response, dict):
            return response.get("data", {})
        return response
    except ShopwareClientError:
        return None


def get_all_products(client: ShopwareClient, limit: int | None = None) -> List[Dict[str, Any]]:
    """Получает список всех товаров."""
    products = []
    page_limit = 100
    page = 1
    
    while True:
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "limit": page_limit,
                "page": page,
                "includes": {
                    "product": [
                        "id",
                        "productNumber",
                        "name"
                    ]
                }
            }
        )
        
        if not isinstance(response, dict):
            break
            
        data = response.get("data", [])
        if not data:
            break
            
        products.extend(data)
        
        if limit and len(products) >= limit:
            products = products[:limit]
            break
            
        total = response.get("total", 0)
        if len(products) >= total:
            break
            
        page += 1
    
    return products


def find_unique_properties(properties: List[Dict[str, Any]]) -> List[str]:
    """
    Находит уникальные свойства (удаляет дубликаты).
    
    Возвращает список ID уникальных свойств (без дубликатов).
    """
    seen_keys: Set[str] = set()
    unique_property_ids: List[str] = []
    
    for prop in properties:
        # Используем комбинацию groupId:optionId как уникальный ключ
        group_id = prop.get("groupId") or ""
        option_id = prop.get("id") or ""
        key = f"{group_id}:{option_id}"
        
        if key not in seen_keys:
            # Уникальное свойство - добавляем в список
            unique_property_ids.append(option_id)
            seen_keys.add(key)
    
    return unique_property_ids


def update_product_properties(
    client: ShopwareClient,
    product_id: str,
    unique_property_ids: List[str],
    dry_run: bool = False
) -> bool:
    """
    Обновляет свойства товара, заменяя все свойства на уникальный список.
    
    Использует PATCH /api/product/{productId} с полным списком properties.
    В Shopware 6 для many-to-many связей это должно работать как replace.
    """
    if dry_run:
        return True
    
    try:
        # Формируем payload с уникальными свойствами
        payload = {
            "properties": [{"id": prop_id} for prop_id in unique_property_ids]
        }
        
        client._request(
            "PATCH",
            f"/api/product/{product_id}",
            json=payload
        )
        return True
    except ShopwareClientError as e:
        print(f"      ERROR: Не удалось обновить свойства товара: {e}")
        return False


def cleanup_product_properties(
    client: ShopwareClient,
    product: Dict[str, Any],
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Очищает дублированные свойства у одного товара.
    
    Возвращает словарь с результатами операции.
    """
    product_id = product.get("id")
    product_number = product.get("productNumber", "")
    product_name = product.get("name", {})
    if isinstance(product_name, dict):
        product_name = product_name.get("ru-RU") or str(product_name)
    else:
        product_name = str(product_name)
    
    # Получаем товар с полными данными о свойствах
    product_data = get_product_with_properties(client, product_id)
    if not product_data:
        return {
            "productId": product_id,
            "productNumber": product_number,
            "status": "error",
            "error": "Не удалось получить данные товара",
            "duplicatesRemoved": 0
        }
    
    properties = product_data.get("properties", [])
    if not properties:
        return {
            "productId": product_id,
            "productNumber": product_number,
            "status": "skipped",
            "reason": "Нет свойств",
            "duplicatesRemoved": 0
        }
    
    # Находим уникальные свойства (без дубликатов)
    unique_property_ids = find_unique_properties(properties)
    original_count = len(properties)
    unique_count = len(unique_property_ids)
    duplicates_count = original_count - unique_count
    
    if duplicates_count == 0:
        return {
            "productId": product_id,
            "productNumber": product_number,
            "status": "skipped",
            "reason": "Нет дубликатов",
            "duplicatesRemoved": 0
        }
    
    # Обновляем товар с уникальными свойствами
    success = update_product_properties(
        client,
        product_id,
        unique_property_ids,
        dry_run=dry_run
    )
    
    if success:
        removed_count = duplicates_count
        failed_count = 0
    else:
        removed_count = 0
        failed_count = duplicates_count
    
    return {
        "productId": product_id,
        "productNumber": product_number,
        "productName": product_name,
        "status": "success" if failed_count == 0 else "partial",
        "duplicatesFound": len(duplicate_property_ids),
        "duplicatesRemoved": removed_count,
        "duplicatesFailed": failed_count
    }


def main():
    """Основная функция."""
    parser = argparse.ArgumentParser(
        description="Очистка дублированных свойств у товаров"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Режим проверки без применения изменений"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Ограничить количество обрабатываемых товаров (для тестирования)"
    )
    parser.add_argument(
        "--product-id",
        type=str,
        default=None,
        help="Обработать только один товар по ID"
    )
    
    args = parser.parse_args()
    
    # Загружаем конфигурацию
    config_path = Path(__file__).parent / "config.json"
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)
    
    with config_path.open("r", encoding="utf-8") as f:
        config_data = json.load(f)
    
    shopware_config = config_data.get("shopware", {})
    client = ShopwareClient(
        ShopwareConfig(
            url=shopware_config["url"],
            access_key_id=shopware_config["access_key_id"],
            secret_access_key=shopware_config["secret_access_key"]
        )
    )
    
    print("=" * 80)
    print("ОЧИСТКА ДУБЛИРОВАННЫХ СВОЙСТВ ТОВАРОВ")
    if args.dry_run:
        print("РЕЖИМ: DRY-RUN (изменения не применяются)")
    print("=" * 80)
    print()
    
    # Получаем список товаров для обработки
    if args.product_id:
        print(f"[1/2] Получение товара {args.product_id}...")
        product_data = get_product_with_properties(client, args.product_id)
        if not product_data:
            print(f"ERROR: Товар {args.product_id} не найден")
            sys.exit(1)
        products = [{
            "id": product_data.get("id"),
            "productNumber": product_data.get("productNumber"),
            "name": product_data.get("name")
        }]
    else:
        print("[1/2] Получение списка товаров...")
        products = get_all_products(client, limit=args.limit)
        print(f"   Найдено товаров: {len(products)}")
    
    # Обрабатываем товары
    print(f"\n[2/2] Обработка {len(products)} товаров...")
    if args.dry_run:
        print("   [DRY-RUN] Изменения не применяются")
    
    results = []
    total_duplicates_removed = 0
    total_products_processed = 0
    total_products_with_duplicates = 0
    total_errors = 0
    
    for i, product in enumerate(products, 1):
        product_number = product.get("productNumber", "")
        print(f"   [{i}/{len(products)}] Обработка товара {product_number}...", end=" ")
        
        result = cleanup_product_properties(client, product, dry_run=args.dry_run)
        results.append(result)
        
        if result["status"] == "success":
            duplicates_removed = result.get("duplicatesRemoved", 0)
            if duplicates_removed > 0:
                total_products_with_duplicates += 1
                total_duplicates_removed += duplicates_removed
                print(f"✓ Удалено {duplicates_removed} дубликатов")
            else:
                print("— Нет дубликатов")
        elif result["status"] == "partial":
            duplicates_removed = result.get("duplicatesRemoved", 0)
            duplicates_failed = result.get("duplicatesFailed", 0)
            total_products_with_duplicates += 1
            total_duplicates_removed += duplicates_removed
            total_errors += duplicates_failed
            print(f"⚠ Удалено {duplicates_removed}, ошибок {duplicates_failed}")
        elif result["status"] == "error":
            total_errors += 1
            print(f"✗ Ошибка: {result.get('error', 'Unknown')}")
        else:
            print("— Пропущен")
        
        total_products_processed += 1
    
    # Сохранение лога операций
    log_path = Path(__file__).parent / "cleanup_properties_log.json"
    log_data = {
        "dryRun": args.dry_run,
        "summary": {
            "totalProductsProcessed": total_products_processed,
            "productsWithDuplicates": total_products_with_duplicates,
            "totalDuplicatesRemoved": total_duplicates_removed,
            "totalErrors": total_errors
        },
        "results": results
    }
    
    with log_path.open("w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    
    # Вывод итогов
    print("\n" + "=" * 80)
    print("ИТОГИ")
    print("=" * 80)
    print(f"Обработано товаров: {total_products_processed}")
    print(f"Товаров с дубликатами: {total_products_with_duplicates}")
    print(f"Удалено дубликатов: {total_duplicates_removed}")
    if total_errors > 0:
        print(f"Ошибок: {total_errors}")
    print(f"\nЛог операций сохранён: {log_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()


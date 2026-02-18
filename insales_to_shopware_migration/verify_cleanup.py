"""
Верификация результатов очистки дублированных свойств и фильтров.

Скрипт проверяет:
- Property Groups с filterable=false (фильтры должны быть отключены)
- Товары без дублированных свойств
- Общее состояние системы
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent / "src"))

from clients import ShopwareClient, ShopwareConfig


def normalize_name(name: str) -> str:
    """Нормализует имя для сравнения (lowercase + strip)."""
    return (name or "").lower().strip()


def get_all_property_groups(client: ShopwareClient) -> List[Dict[str, Any]]:
    """Получает все Property Groups из Shopware."""
    all_groups = []
    limit = 100
    page = 1
    
    while True:
        response = client._request(
            "POST",
            "/api/search/property-group",
            json={
                "limit": limit,
                "page": page,
                "includes": {
                    "property_group": [
                        "id",
                        "name",
                        "filterable"
                    ]
                }
            }
        )
        
        if not isinstance(response, dict):
            break
            
        data = response.get("data", [])
        if not data:
            break
            
        all_groups.extend(data)
        
        total = response.get("total", 0)
        if len(all_groups) >= total:
            break
            
        page += 1
    
    return all_groups


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
    except Exception:
        return None


def get_sample_products(client: ShopwareClient, limit: int = 20) -> List[Dict[str, Any]]:
    """Получает выборку товаров для проверки."""
    response = client._request(
        "POST",
        "/api/search/product",
        json={
            "limit": limit,
            "includes": {
                "product": [
                    "id",
                    "productNumber",
                    "name"
                ]
            }
        }
    )
    
    if isinstance(response, dict):
        return response.get("data", [])
    return []


def check_property_group_duplicates(groups: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Проверяет наличие дубликатов Property Groups."""
    groups_by_name: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    
    for group in groups:
        name = group.get("name", "")
        normalized = normalize_name(name)
        if normalized:
            groups_by_name[normalized].append(group)
    
    duplicates = {
        name: group_list
        for name, group_list in groups_by_name.items()
        if len(group_list) > 1
    }
    
    # Проверяем, есть ли дубликаты с filterable=true
    filterable_duplicates = []
    for normalized_name, group_list in duplicates.items():
        filterable_groups = [g for g in group_list if g.get("filterable") is True]
        if len(filterable_groups) > 1:
            filterable_duplicates.append({
                "name": group_list[0].get("name", ""),
                "count": len(filterable_groups)
            })
    
    return {
        "totalDuplicates": len(duplicates),
        "filterableDuplicates": len(filterable_duplicates),
        "details": filterable_duplicates
    }


def check_product_property_duplicates(
    client: ShopwareClient,
    products: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Проверяет наличие дублированных свойств у товаров."""
    products_with_duplicates = []
    
    for product in products:
        product_id = product.get("id")
        product_data = get_product_with_properties(client, product_id)
        if not product_data:
            continue
        
        properties = product_data.get("properties", [])
        if not properties:
            continue
        
        # Проверяем на дубликаты
        seen_keys = set()
        has_duplicates = False
        
        for prop in properties:
            group_id = prop.get("groupId") or ""
            option_id = prop.get("id") or ""
            key = f"{group_id}:{option_id}"
            
            if key in seen_keys:
                has_duplicates = True
                break
            seen_keys.add(key)
        
        if has_duplicates:
            products_with_duplicates.append({
                "productId": product_id,
                "productNumber": product.get("productNumber"),
                "productName": product.get("name", {})
            })
    
    return {
        "totalChecked": len(products),
        "productsWithDuplicates": len(products_with_duplicates),
        "details": products_with_duplicates[:10]  # Первые 10 для примера
    }


def main():
    """Основная функция верификации."""
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
    print("ВЕРИФИКАЦИЯ РЕЗУЛЬТАТОВ ОЧИСТКИ")
    print("=" * 80)
    print()
    
    # 1. Проверка Property Groups
    print("[1/3] Проверка Property Groups...")
    all_groups = get_all_property_groups(client)
    print(f"   Всего Property Groups: {len(all_groups)}")
    
    filterable_groups = [g for g in all_groups if g.get("filterable") is True]
    non_filterable_groups = [g for g in all_groups if g.get("filterable") is False]
    
    print(f"   С filterable=true: {len(filterable_groups)}")
    print(f"   С filterable=false: {len(non_filterable_groups)}")
    
    # Проверка дубликатов
    duplicates_check = check_property_group_duplicates(all_groups)
    print(f"   Дубликатов (по имени): {duplicates_check['totalDuplicates']}")
    print(f"   Дубликатов с filterable=true: {duplicates_check['filterableDuplicates']}")
    
    if duplicates_check['filterableDuplicates'] > 0:
        print("   ⚠ ВНИМАНИЕ: Найдены дубликаты с filterable=true!")
        for detail in duplicates_check['details'][:5]:
            print(f"     - {detail['name']}: {detail['count']} групп")
    else:
        print("   ✓ Дубликатов с filterable=true не найдено")
    
    # 2. Проверка свойств товаров
    print("\n[2/3] Проверка свойств товаров...")
    sample_products = get_sample_products(client, limit=50)
    print(f"   Проверено товаров: {len(sample_products)}")
    
    properties_check = check_product_property_duplicates(client, sample_products)
    print(f"   Товаров с дубликатами: {properties_check['productsWithDuplicates']}")
    
    if properties_check['productsWithDuplicates'] > 0:
        print("   ⚠ ВНИМАНИЕ: Найдены товары с дублированными свойствами!")
        for detail in properties_check['details'][:5]:
            product_name = detail.get("productName", {})
            if isinstance(product_name, dict):
                product_name = product_name.get("ru-RU") or str(product_name)
            else:
                product_name = str(product_name)
            print(f"     - {detail['productNumber']}: {product_name[:50]}")
    else:
        print("   ✓ Дубликатов свойств не найдено")
    
    # 3. Общая статистика
    print("\n[3/3] Общая статистика...")
    
    # Загружаем логи операций, если есть
    disable_filters_log = Path(__file__).parent / "disable_filters_log.json"
    cleanup_properties_log = Path(__file__).parent / "cleanup_properties_log.json"
    
    if disable_filters_log.exists():
        with disable_filters_log.open("r", encoding="utf-8") as f:
            disable_log = json.load(f)
        print(f"   Отключено фильтров: {disable_log.get('successCount', 0)}")
    
    if cleanup_properties_log.exists():
        with cleanup_properties_log.open("r", encoding="utf-8") as f:
            cleanup_log = json.load(f)
        summary = cleanup_log.get("summary", {})
        print(f"   Очищено свойств: {summary.get('totalDuplicatesRemoved', 0)}")
        print(f"   Товаров обработано: {summary.get('totalProductsProcessed', 0)}")
    
    # Итоговый отчёт
    print("\n" + "=" * 80)
    print("ИТОГОВЫЙ ОТЧЁТ")
    print("=" * 80)
    
    issues = []
    
    if duplicates_check['filterableDuplicates'] > 0:
        issues.append(f"⚠ Найдено {duplicates_check['filterableDuplicates']} дубликатов Property Groups с filterable=true")
    
    if properties_check['productsWithDuplicates'] > 0:
        issues.append(f"⚠ Найдено {properties_check['productsWithDuplicates']} товаров с дублированными свойствами")
    
    if not issues:
        print("✓ ВСЁ В ПОРЯДКЕ!")
        print("  - Дубликатов Property Groups с filterable=true не найдено")
        print("  - Дубликатов свойств у товаров не найдено")
    else:
        print("⚠ ОБНАРУЖЕНЫ ПРОБЛЕМЫ:")
        for issue in issues:
            print(f"  {issue}")
    
    print("=" * 80)
    
    # Сохранение отчёта
    report_path = Path(__file__).parent / "verification_report.json"
    report = {
        "propertyGroups": {
            "total": len(all_groups),
            "filterable": len(filterable_groups),
            "nonFilterable": len(non_filterable_groups),
            "duplicates": duplicates_check
        },
        "productProperties": properties_check,
        "status": "ok" if not issues else "issues_found",
        "issues": issues
    }
    
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\nОтчёт сохранён: {report_path}")


if __name__ == "__main__":
    main()





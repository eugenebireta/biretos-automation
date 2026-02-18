"""
Анализ дублированных Property Groups и свойств товаров в Shopware 6.

Скрипт анализирует:
- Property Groups с filterable=true (загрязняют фильтры)
- Дубликаты Property Groups (по нормализованному имени)
- Товары с дублированными свойствами
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set

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
                        "filterable",
                        "displayType",
                        "sortingType"
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


def get_all_products_with_properties(client: ShopwareClient, limit: int | None = None) -> List[Dict[str, Any]]:
    """Получает товары с их свойствами."""
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
                    ],
                    "property_group_option": [
                        "id",
                        "name",
                        "groupId"
                    ]
                },
                "associations": {
                    "properties": {
                        "associations": {
                            "group": {}
                        }
                    }
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


def find_duplicate_property_groups(groups: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Находит дубликаты Property Groups по нормализованному имени."""
    groups_by_name: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    
    for group in groups:
        name = group.get("name", "")
        normalized = normalize_name(name)
        if normalized:
            groups_by_name[normalized].append(group)
    
    # Оставляем только дубликаты (2+ группы с одинаковым именем)
    duplicates = {
        name: group_list
        for name, group_list in groups_by_name.items()
        if len(group_list) > 1
    }
    
    return duplicates


def analyze_product_property_duplicates(products: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Анализирует дублированные свойства у товаров."""
    products_with_duplicates = []
    total_duplicates = 0
    
    for product in products:
        properties = product.get("properties", [])
        if not properties:
            continue
        
        # Группируем свойства по groupId:optionId
        property_keys: Set[str] = set()
        duplicates_in_product: List[Dict[str, Any]] = []
        
        for prop in properties:
            group_id = prop.get("groupId") or ""
            option_id = prop.get("id") or ""
            key = f"{group_id}:{option_id}"
            
            if key in property_keys:
                # Дубликат найден
                duplicates_in_product.append({
                    "groupId": group_id,
                    "optionId": option_id,
                    "optionName": prop.get("name", "")
                })
                total_duplicates += 1
            else:
                property_keys.add(key)
        
        if duplicates_in_product:
            products_with_duplicates.append({
                "productId": product.get("id"),
                "productNumber": product.get("productNumber"),
                "productName": product.get("name", {}).get("ru-RU") or str(product.get("name", "")),
                "duplicates": duplicates_in_product,
                "duplicateCount": len(duplicates_in_product)
            })
    
    return {
        "productsWithDuplicates": products_with_duplicates,
        "totalProductsAffected": len(products_with_duplicates),
        "totalDuplicateProperties": total_duplicates
    }


def main():
    """Основная функция анализа."""
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
    print("АНАЛИЗ ДУБЛИКАТОВ В SHOPWARE 6")
    print("=" * 80)
    print()
    
    # 1. Анализ Property Groups
    print("[1/3] Получение всех Property Groups...")
    all_groups = get_all_property_groups(client)
    print(f"   Найдено Property Groups: {len(all_groups)}")
    
    # Группы с filterable=true
    filterable_groups = [g for g in all_groups if g.get("filterable") is True]
    print(f"   Property Groups с filterable=true: {len(filterable_groups)}")
    
    # 2. Поиск дубликатов Property Groups
    print("\n[2/3] Поиск дубликатов Property Groups...")
    duplicates = find_duplicate_property_groups(all_groups)
    print(f"   Найдено дубликатов (по нормализованному имени): {len(duplicates)}")
    
    # Анализ дубликатов
    duplicate_details = []
    for normalized_name, group_list in duplicates.items():
        filterable_count = sum(1 for g in group_list if g.get("filterable") is True)
        non_filterable_count = len(group_list) - filterable_count
        
        duplicate_details.append({
            "normalizedName": normalized_name,
            "originalName": group_list[0].get("name", ""),
            "totalGroups": len(group_list),
            "filterableCount": filterable_count,
            "nonFilterableCount": non_filterable_count,
            "groups": [
                {
                    "id": g.get("id"),
                    "name": g.get("name"),
                    "filterable": g.get("filterable")
                }
                for g in group_list
            ]
        })
    
    # 3. Анализ дублированных свойств товаров
    print("\n[3/3] Анализ свойств товаров...")
    print("   Получение товаров (это может занять время)...")
    products = get_all_products_with_properties(client, limit=None)
    print(f"   Найдено товаров: {len(products)}")
    
    property_analysis = analyze_product_property_duplicates(products)
    
    # Вывод отчёта
    print("\n" + "=" * 80)
    print("ОТЧЁТ")
    print("=" * 80)
    
    print("\n1. PROPERTY GROUPS:")
    print(f"   Всего групп: {len(all_groups)}")
    print(f"   С filterable=true: {len(filterable_groups)}")
    print(f"   Дубликатов (по имени): {len(duplicates)}")
    
    if duplicate_details:
        print("\n   Детали дубликатов:")
        for detail in duplicate_details[:10]:  # Показываем первые 10
            print(f"     - '{detail['originalName']}': {detail['totalGroups']} групп "
                  f"(filterable: {detail['filterableCount']}, "
                  f"non-filterable: {detail['nonFilterableCount']})")
        if len(duplicate_details) > 10:
            print(f"     ... и ещё {len(duplicate_details) - 10} дубликатов")
    
    print("\n2. СВОЙСТВА ТОВАРОВ:")
    print(f"   Товаров с дублированными свойствами: {property_analysis['totalProductsAffected']}")
    print(f"   Всего дублированных свойств: {property_analysis['totalDuplicateProperties']}")
    
    if property_analysis['productsWithDuplicates']:
        print("\n   Примеры товаров с дубликатами:")
        for product in property_analysis['productsWithDuplicates'][:5]:
            print(f"     - {product['productNumber']} ({product['productName'][:50]}): "
                  f"{product['duplicateCount']} дубликатов")
        if len(property_analysis['productsWithDuplicates']) > 5:
            print(f"     ... и ещё {len(property_analysis['productsWithDuplicates']) - 5} товаров")
    
    # Сохранение детального отчёта
    report_path = Path(__file__).parent / "duplicates_analysis_report.json"
    report = {
        "propertyGroups": {
            "total": len(all_groups),
            "filterable": len(filterable_groups),
            "duplicates": duplicate_details
        },
        "productProperties": property_analysis,
        "summary": {
            "totalPropertyGroups": len(all_groups),
            "filterablePropertyGroups": len(filterable_groups),
            "duplicatePropertyGroups": len(duplicates),
            "productsWithDuplicateProperties": property_analysis['totalProductsAffected'],
            "totalDuplicateProperties": property_analysis['totalDuplicateProperties']
        }
    }
    
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n3. ДЕТАЛЬНЫЙ ОТЧЁТ сохранён: {report_path}")
    print("\n" + "=" * 80)
    print("АНАЛИЗ ЗАВЕРШЁН")
    print("=" * 80)


if __name__ == "__main__":
    main()





#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Восстановление productNumber (SKU) у существующих товаров в Shopware
"""
import json
import sys
import argparse
from pathlib import Path
from typing import Dict, Optional, Any

sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from full_import import parse_ndjson, DEFAULT_SNAPSHOT_NDJSON

def find_product_by_name_and_manufacturer(
    client: ShopwareClient,
    product_name: str,
    manufacturer_name: Optional[str] = None
) -> Optional[str]:
    """
    Ищет товар в Shopware по имени и производителю.
    Возвращает product_id или None.
    """
    try:
        # Строим фильтры
        filters = [
            {"field": "name", "type": "equals", "value": product_name}
        ]
        
        if manufacturer_name:
            # Сначала находим manufacturer_id
            manufacturer_id = client.find_manufacturer_by_name(manufacturer_name)
            if manufacturer_id:
                filters.append({
                    "field": "manufacturerId",
                    "type": "equals",
                    "value": manufacturer_id
                })
        
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": filters,
                "includes": {"product": ["id", "productNumber", "name", "manufacturerId"]},
                "limit": 1,
            },
        )
        
        if isinstance(response, dict):
            data = response.get("data", [])
            if data and len(data) > 0:
                product = data[0]
                if isinstance(product, dict):
                    product_id = product.get("id")
                    if product_id:
                        return product_id
    except Exception as e:
        print(f"[DEBUG] Ошибка поиска товара '{product_name}': {e}")
    
    return None

def load_migration_map() -> Dict[str, str]:
    """
    Загружает migration_map.json если существует.
    Возвращает словарь: insales_product_id -> shopware_product_id
    """
    map_path = Path(__file__).parent.parent / "migration_map.json"
    if not map_path.exists():
        return {}
    
    try:
        with map_path.open(encoding="utf-8") as f:
            data = json.load(f)
            # migration_map.json может иметь структуру с "products" или быть плоским словарем
            if isinstance(data, dict) and "products" in data:
                return data.get("products", {})
            elif isinstance(data, dict):
                # Пробуем найти маппинг товаров
                # Может быть в разных форматах
                return data
    except Exception as e:
        print(f"[WARNING] Ошибка загрузки migration_map.json: {e}")
    
    return {}

def restore_product_numbers(
    client: ShopwareClient,
    products: list[Dict[str, Any]],
    migration_map: Dict[str, str],
    dry_run: bool = False,
    limit: Optional[int] = None
) -> int:
    """
    Восстанавливает productNumber для товаров.
    Возвращает количество обновленных товаров.
    """
    updated_count = 0
    
    # Ограничиваем количество товаров
    if limit:
        products = products[:limit]
    
    print(f"\n{'='*80}")
    print(f"ВОССТАНОВЛЕНИЕ PRODUCT NUMBER")
    print(f"{'='*80}")
    print(f"Режим: {'DRY-RUN' if dry_run else 'REAL'}")
    print(f"Товаров к обработке: {len(products)}")
    print(f"{'='*80}\n")
    
    for idx, product_data in enumerate(products, 1):
        # Получаем SKU из snapshot
        variants = product_data.get("variants", [])
        if not variants:
            print(f"[{idx}] Пропуск: нет вариантов")
            continue
        
        sku = variants[0].get("sku", "").strip()
        if not sku:
            print(f"[{idx}] Пропуск: нет SKU")
            continue
        
        product_name = product_data.get("title", "").strip()
        if not product_name:
            print(f"[{idx}] Пропуск: нет названия товара")
            continue
        
        # Получаем manufacturer из характеристик
        manufacturer_name = None
        characteristics = product_data.get("characteristics", [])
        properties = product_data.get("properties", [])
        
        # Ищем бренд в characteristics
        brand_property_id = None
        for prop in properties:
            if prop.get("permalink", "").strip().lower() == "brand" or prop.get("title", "").strip() == "Бренд":
                brand_property_id = prop.get("id")
                break
        
        if brand_property_id:
            for char in characteristics:
                if char.get("property_id") == brand_property_id:
                    manufacturer_name = char.get("title", "").strip()
                    break
        
        # Пробуем найти товар в Shopware
        product_id = None
        
        # Способ 1: По migration_map (если есть insales_id)
        insales_id = str(product_data.get("id", ""))
        if insales_id and insales_id in migration_map:
            product_id = migration_map[insales_id]
            print(f"[{idx}] Найден через migration_map: {product_id}")
        
        # Способ 2: По name + manufacturer
        if not product_id:
            product_id = find_product_by_name_and_manufacturer(
                client,
                product_name,
                manufacturer_name
            )
            if product_id:
                print(f"[{idx}] Найден по name+manufacturer: {product_id}")
        
        if not product_id:
            print(f"[{idx}] [SKIP] Товар не найден в Shopware: {product_name} (SKU: {sku})")
            continue
        
        # Получаем текущий productNumber
        try:
            response = client._request("GET", f"/api/product/{product_id}")
            if isinstance(response, dict):
                current_data = response.get("data", {})
                # productNumber может быть в data или data.attributes
                current_product_number = current_data.get("productNumber")
                if current_product_number is None and isinstance(current_data.get("attributes"), dict):
                    current_product_number = current_data.get("attributes", {}).get("productNumber")
                
                print(f"[{idx}] Товар найден:")
                print(f"    Product ID: {product_id}")
                print(f"    Название: {product_name}")
                print(f"    Текущий productNumber: {current_product_number}")
                print(f"    Новый productNumber: {sku}")
                
                # Если productNumber уже установлен и совпадает, пропускаем
                if current_product_number == sku:
                    print(f"    [OK] productNumber уже установлен правильно, пропуск")
                    continue
                
                # Обновляем productNumber
                if not dry_run:
                    try:
                        client._request(
                            "PATCH",
                            f"/api/product/{product_id}",
                            json={"productNumber": sku}
                        )
                        print(f"    [OK] productNumber обновлен")
                        updated_count += 1
                    except Exception as e:
                        print(f"    [ERROR] Ошибка обновления: {e}")
                else:
                    print(f"    [DRY-RUN] Будет обновлен productNumber: {sku}")
                    updated_count += 1
        except Exception as e:
            # Если товар не найден, пробуем найти по name+manufacturer
            if "404" in str(e) or "not found" in str(e).lower():
                print(f"[{idx}] Товар из migration_map не найден, пробуем найти по name+manufacturer...")
                product_id_alt = find_product_by_name_and_manufacturer(
                    client,
                    product_name,
                    manufacturer_name
                )
                if product_id_alt:
                    print(f"[{idx}] Товар найден альтернативным способом: {product_id_alt}")
                    # Повторяем попытку с новым ID
                    try:
                        response = client._request("GET", f"/api/product/{product_id_alt}")
                        if isinstance(response, dict):
                            current_data = response.get("data", {})
                            # productNumber может быть в data или data.attributes
                            current_product_number = current_data.get("productNumber")
                            if current_product_number is None and isinstance(current_data.get("attributes"), dict):
                                current_product_number = current_data.get("attributes", {}).get("productNumber")
                            
                            print(f"[{idx}] Товар найден:")
                            print(f"    Product ID: {product_id_alt}")
                            print(f"    Название: {product_name}")
                            print(f"    Текущий productNumber: {current_product_number}")
                            print(f"    Новый productNumber: {sku}")
                            
                            if current_product_number == sku:
                                print(f"    [OK] productNumber уже установлен правильно, пропуск")
                                continue
                            
                            if not dry_run:
                                try:
                                    client._request(
                                        "PATCH",
                                        f"/api/product/{product_id_alt}",
                                        json={"productNumber": sku}
                                    )
                                    print(f"    [OK] productNumber обновлен")
                                    updated_count += 1
                                except Exception as e2:
                                    print(f"    [ERROR] Ошибка обновления: {e2}")
                            else:
                                print(f"    [DRY-RUN] Будет обновлен productNumber: {sku}")
                                updated_count += 1
                    except Exception as e2:
                        print(f"[{idx}] [ERROR] Ошибка получения товара {product_id_alt}: {e2}")
                else:
                    print(f"[{idx}] [ERROR] Товар не найден в Shopware: {product_name} (SKU: {sku})")
            else:
                print(f"[{idx}] [ERROR] Ошибка получения товара {product_id}: {e}")
            continue
        
        print()  # Пустая строка для читаемости
    
    print(f"{'='*80}")
    print(f"ИТОГО: {'Будет обновлено' if dry_run else 'Обновлено'} товаров: {updated_count}")
    print(f"{'='*80}\n")
    
    return updated_count

def main():
    parser = argparse.ArgumentParser(
        description="Восстановление productNumber (SKU) у существующих товаров в Shopware"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Режим проверки без реальных изменений"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Ограничение количества товаров для обработки"
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=DEFAULT_SNAPSHOT_NDJSON,
        help="Путь к snapshot файлу (по умолчанию: insales_snapshot/products.ndjson)"
    )
    
    args = parser.parse_args()
    
    # Загружаем конфигурацию
    config_path = Path(__file__).parent.parent / "config.json"
    with config_path.open(encoding="utf-8") as f:
        config = json.load(f)
    
    sw = config["shopware"]
    client = ShopwareClient(ShopwareConfig(sw["url"], sw["access_key_id"], sw["secret_access_key"]))
    
    # Загружаем snapshot
    print(f"Загрузка snapshot: {args.snapshot}")
    products = parse_ndjson(args.snapshot, limit=args.limit)
    print(f"Загружено товаров: {len(products)}")
    
    # Загружаем migration_map если есть
    migration_map = load_migration_map()
    if migration_map:
        print(f"Загружен migration_map: {len(migration_map)} записей")
    
    # Восстанавливаем productNumber
    updated_count = restore_product_numbers(
        client,
        products,
        migration_map,
        dry_run=args.dry_run,
        limit=args.limit
    )
    
    if args.dry_run:
        print("\n[INFO] Запуск в режиме DRY-RUN. Для реального обновления запустите без --dry-run")
    else:
        print(f"\n[SUCCESS] Обновлено товаров: {updated_count}")

if __name__ == "__main__":
    main()


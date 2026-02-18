#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Массовое заполнение customFields.internal_barcode для товаров Shopware.

Источники данных:
1. NDJSON файл (insales_snapshot/products.ndjson) - приоритет
2. InSales API (если NDJSON недоступен)

Сопоставление:
- productNumber (Shopware) -> SKU (InSales) -> variant.barcode
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, Optional, List, Tuple

sys.path.insert(0, str(Path(__file__).parent))

from clients.shopware_client import ShopwareClient, ShopwareConfig

def load_json(path: Path) -> dict:
    """Загружает JSON файл."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_ndjson(path: Path) -> List[Dict]:
    """Загружает NDJSON файл."""
    products = []
    if not path.exists():
        print(f"[WARNING] NDJSON файл не найден: {path}")
        return products
    
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                product = json.loads(line)
                products.append(product)
            except json.JSONDecodeError as e:
                print(f"[WARNING] Ошибка парсинга строки {line_num}: {e}")
                continue
    
    print(f"[INFO] Загружено {len(products)} товаров из NDJSON")
    return products

def build_barcode_map_from_ndjson(ndjson_path: Path) -> Dict[str, str]:
    """
    Строит маппинг SKU -> barcode из NDJSON файла.
    
    Returns:
        Dict[str, str]: {sku: barcode}
    """
    print("\n[ШАГ 1] Построение маппинга штрих-кодов из NDJSON...")
    
    products = load_ndjson(ndjson_path)
    barcode_map = {}
    
    for product in products:
        variants = product.get("variants", [])
        if not variants:
            continue
        
        # Берем первый вариант (как в full_import.py)
        variant = variants[0]
        sku = variant.get("sku")
        barcode = variant.get("barcode")
        
        if sku and barcode:
            sku_str = str(sku).strip()
            barcode_str = str(barcode).strip()
            if sku_str and barcode_str:
                barcode_map[sku_str] = barcode_str
    
    print(f"[OK] Найдено {len(barcode_map)} товаров с штрих-кодами")
    return barcode_map

def build_barcode_map_from_insales(config_path: Path) -> Dict[str, str]:
    """
    Строит маппинг SKU -> barcode из InSales API.
    
    Returns:
        Dict[str, str]: {sku: barcode}
    """
    print("\n[ШАГ 1] Построение маппинга штрих-кодов из InSales API...")
    
    try:
        from clients.insales_client import InsalesClient, InsalesConfig
    except ImportError:
        print("[ERROR] Не удалось импортировать InsalesClient")
        return {}
    
    config = load_json(config_path)
    insales_config = config.get("insales", {})
    
    if not insales_config:
        print("[ERROR] Конфигурация InSales не найдена")
        return {}
    
    insales_cfg = InsalesConfig(
        host=insales_config.get("host", ""),
        api_key=insales_config.get("api_key", ""),
        api_password=insales_config.get("api_password", "")
    )
    
    try:
        client = InsalesClient(insales_cfg)
    except Exception as e:
        print(f"[ERROR] Не удалось создать InSales клиент: {e}")
        return {}
    
    barcode_map = {}
    
    try:
        print("[INFO] Получение товаров из InSales...")
        products = client.fetch_all("/products", per_page=250)
        
        for product in products:
            variants = product.get("variants", [])
            if not variants:
                continue
            
            variant = variants[0]
            sku = variant.get("sku")
            barcode = variant.get("barcode")
            
            if sku and barcode:
                sku_str = str(sku).strip()
                barcode_str = str(barcode).strip()
                if sku_str and barcode_str:
                    barcode_map[sku_str] = barcode_str
        
        print(f"[OK] Найдено {len(barcode_map)} товаров с штрих-кодами")
    except Exception as e:
        print(f"[ERROR] Ошибка получения данных из InSales: {e}")
    
    return barcode_map

def get_products_without_barcode(client: ShopwareClient, limit: Optional[int] = None) -> List[Dict]:
    """
    Получает товары из Shopware, у которых internal_barcode пустой.
    
    Returns:
        List[Dict]: Список товаров с полями id, productNumber, customFields
    """
    print("\n[ШАГ 2] Получение товаров без internal_barcode из Shopware...")
    
    products = []
    page = 1
    per_page = 100
    
    while True:
        try:
            response = client._request(
                "POST",
                "/api/search/product",
                json={
                    "includes": {
                        "product": ["id", "productNumber", "customFields"]
                    },
                    "limit": per_page,
                    "page": page
                }
            )
            
            if not isinstance(response, dict):
                break
            
            data = response.get("data", [])
            if not data:
                break
            
            for product in data:
                attributes = product.get("attributes", {})
                custom_fields = attributes.get("customFields", {}) or {}
                internal_barcode = custom_fields.get("internal_barcode")
                
                # Проверяем, что поле пустое или отсутствует
                if not internal_barcode or str(internal_barcode).strip() == "":
                    products.append({
                        "id": product.get("id"),
                        "productNumber": attributes.get("productNumber"),
                        "customFields": custom_fields
                    })
            
            if limit and len(products) >= limit:
                products = products[:limit]
                break
            
            if len(data) < per_page:
                break
            
            page += 1
            time.sleep(0.2)  # Небольшая задержка
            
        except Exception as e:
            print(f"[ERROR] Ошибка получения товаров: {e}")
            break
    
    print(f"[OK] Найдено {len(products)} товаров без internal_barcode")
    return products

def update_product_barcode(client: ShopwareClient, product_id: str, barcode: str) -> bool:
    """
    Обновляет internal_barcode для товара.
    
    Returns:
        bool: True при успехе
    """
    try:
        client.update_product_custom_fields(
            product_id=product_id,
            custom_fields={"internal_barcode": str(barcode).strip()}
        )
        return True
    except Exception as e:
        print(f"[ERROR] Ошибка обновления товара {product_id}: {e}")
        return False

def main() -> int:
    """Основная функция."""
    
    print("="*80)
    print("МАССОВОЕ ЗАПОЛНЕНИЕ internal_barcode")
    print("="*80)
    
    # Загружаем конфигурацию
    config_path = Path(__file__).parent.parent / "config.json"
    if not config_path.exists():
        print(f"[ERROR] Конфигурация не найдена: {config_path}")
        return 1
    
    config = load_json(config_path)
    
    # Создаем Shopware клиент
    shop_cfg = ShopwareConfig(
        url=config["shopware"]["url"],
        access_key_id=config["shopware"]["access_key_id"],
        secret_access_key=config["shopware"]["secret_access_key"],
    )
    client = ShopwareClient(shop_cfg, timeout=30)
    
    # ШАГ 1: Строим маппинг штрих-кодов
    # Приоритет: NDJSON файл
    ndjson_path = Path(__file__).parent.parent / "insales_snapshot" / "products.ndjson"
    barcode_map = {}
    
    if ndjson_path.exists():
        barcode_map = build_barcode_map_from_ndjson(ndjson_path)
    else:
        print(f"[INFO] NDJSON файл не найден, пробуем InSales API...")
        barcode_map = build_barcode_map_from_insales(config_path)
    
    if not barcode_map:
        print("[ERROR] Не удалось получить маппинг штрих-кодов")
        return 1
    
    # ШАГ 2: Получаем товары без internal_barcode
    products = get_products_without_barcode(client)
    
    if not products:
        print("\n[INFO] Все товары уже имеют internal_barcode")
        return 0
    
    # ШАГ 3: Сопоставляем и обновляем
    print(f"\n[ШАГ 3] Обновление товаров...")
    
    updated = 0
    not_found = 0
    errors = 0
    examples = []
    
    for idx, product in enumerate(products, 1):
        product_id = product["id"]
        product_number = product["productNumber"]
        
        # Ищем штрих-код по productNumber (который соответствует SKU в InSales)
        barcode = barcode_map.get(product_number)
        
        if not barcode:
            not_found += 1
            if not_found <= 5:  # Показываем первые 5 примеров
                print(f"[SKIP] {product_number}: штрих-код не найден")
            continue
        
        # Обновляем товар
        if update_product_barcode(client, product_id, barcode):
            updated += 1
            if updated <= 10:  # Показываем первые 10 примеров
                examples.append((product_number, barcode))
                print(f"[OK] {idx}/{len(products)}: {product_number} -> {barcode}")
            elif updated == 11:
                print(f"[INFO] ... (продолжаем обновление)")
        else:
            errors += 1
        
        # Небольшая задержка для избежания rate limit
        if idx % 10 == 0:
            time.sleep(0.3)
    
    # ШАГ 4: Отчёт
    print("\n" + "="*80)
    print("ИТОГОВЫЙ ОТЧЁТ")
    print("="*80)
    
    print(f"\n[1] Статистика:")
    print(f"    - Всего товаров без internal_barcode: {len(products)}")
    print(f"    - Обновлено: {updated}")
    print(f"    - Штрих-код не найден: {not_found}")
    print(f"    - Ошибки: {errors}")
    
    print(f"\n[2] Примеры обновлённых товаров:")
    if examples:
        for product_number, barcode in examples[:10]:
            print(f"    - {product_number} -> {barcode}")
    else:
        print(f"    - Нет примеров")
    
    print(f"\n[3] Результат:")
    if updated > 0:
        print(f"    [OK] Успешно обновлено {updated} товаров")
        print(f"    [INFO] Поле internal_barcode заполнено и готово для экспорта")
    else:
        print(f"    [WARNING] Не удалось обновить товары")
        if not_found > 0:
            print(f"    [INFO] Для {not_found} товаров не найден штрих-код в источнике")
    
    print("\n" + "="*80)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())




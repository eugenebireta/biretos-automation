#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматическая проверка наличия internal_barcode в Shopware API.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from clients.shopware_client import ShopwareClient, ShopwareConfig

def load_json(path: Path) -> dict:
    """Загружает JSON файл."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main() -> int:
    """Проверяет наличие internal_barcode в API."""
    # Тестовый productNumber (можно заменить на любой существующий)
    test_product_number = "500944170"
    
    # Загружаем конфигурацию
    config_path = Path(__file__).parent.parent / "config.json"
    if not config_path.exists():
        print(f"[ERROR] Конфигурация не найдена: {config_path}")
        return 1
    
    config = load_json(config_path)
    
    # Создаем клиент
    shop_cfg = ShopwareConfig(
        url=config["shopware"]["url"],
        access_key_id=config["shopware"]["access_key_id"],
        secret_access_key=config["shopware"]["secret_access_key"],
    )
    client = ShopwareClient(shop_cfg, timeout=10)
    
    print("="*70)
    print("[CHECK] Проверка наличия internal_barcode в Shopware API")
    print("="*70)
    
    # ШАГ 1: Найти product_id по productNumber
    print(f"\n[STEP 1] Поиск товара: productNumber = {test_product_number}")
    try:
        search_response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [
                    {"field": "productNumber", "type": "equals", "value": test_product_number}
                ],
                "limit": 1
            }
        )
        
        if not isinstance(search_response, dict):
            print(f"[ERROR] Неожиданный формат ответа Search API")
            return 1
        
        data = search_response.get("data", [])
        if not data or len(data) == 0:
            print(f"[ERROR] Товар с productNumber '{test_product_number}' не найден")
            print(f"[INFO] Попробуйте указать другой productNumber")
            return 1
        
        product_id = data[0].get("id")
        if not product_id:
            print(f"[ERROR] product_id не найден в ответе")
            return 1
        
        print(f"[OK] Товар найден: product_id = {product_id}")
        
    except Exception as e:
        print(f"[ERROR] Ошибка поиска товара: {e}")
        return 1
    
    # ШАГ 2: Получить товар через GET /api/product/{id}
    print(f"\n[STEP 2] Получение товара через GET /api/product/{product_id}")
    try:
        product_response = client._request("GET", f"/api/product/{product_id}")
        
        if not isinstance(product_response, dict):
            print(f"[ERROR] Неожиданный формат ответа GET API")
            return 1
        
        data = product_response.get("data", {})
        if not data:
            print(f"[ERROR] Данные товара не найдены в ответе")
            return 1
        
        attributes = data.get("attributes", {})
        custom_fields = attributes.get("customFields", {})
        internal_barcode = custom_fields.get("internal_barcode")
        
        print(f"[OK] Товар получен")
        print(f"\n[RESULT] Проверка customFields.internal_barcode:")
        print(f"  productNumber: {test_product_number}")
        print(f"  product_id: {product_id}")
        print(f"  internal_barcode: {internal_barcode}")
        
        # ШАГ 3: Проверка значения
        print(f"\n[STEP 3] Валидация значения")
        
        if internal_barcode is None:
            print(f"[FAIL] internal_barcode = None (не установлен)")
            print(f"\n" + "="*70)
            print("[FINAL] STOP - данные не сохраняются, импорт продолжать нельзя")
            print("="*70)
            return 1
        
        if not isinstance(internal_barcode, str):
            print(f"[FAIL] internal_barcode имеет неверный тип: {type(internal_barcode)}")
            print(f"\n" + "="*70)
            print("[FINAL] STOP - данные не сохраняются, импорт продолжать нельзя")
            print("="*70)
            return 1
        
        if internal_barcode.strip() == "":
            print(f"[FAIL] internal_barcode = пустая строка")
            print(f"\n" + "="*70)
            print("[FINAL] STOP - данные не сохраняются, импорт продолжать нельзя")
            print("="*70)
            return 1
        
        print(f"[OK] internal_barcode установлен: '{internal_barcode}'")
        print(f"\n" + "="*70)
        print("[FINAL] OK - данные есть, проблема только в отображении")
        print("="*70)
        return 0
        
    except Exception as e:
        print(f"[ERROR] Ошибка получения товара: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())





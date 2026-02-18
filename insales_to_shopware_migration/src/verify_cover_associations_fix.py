#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка установки cover через associations.cover после UPDATE.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from clients.shopware_client import ShopwareClient, ShopwareConfig
from full_import import load_json, find_product_by_number


def main() -> int:
    """Проверяет установку cover через associations после UPDATE."""
    product_number = "500944170"
    
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
    print("[VERIFY] Проверка установки cover через associations.cover")
    print("="*70)
    
    # Находим товар
    product_id = find_product_by_number(client, product_number)
    if not product_id:
        print(f"[ERROR] Товар не найден: {product_number}")
        return 1
    
    print(f"[OK] Товар найден: {product_id}")
    
    # Проверяем текущее состояние
    print(f"\n[CHECK 1] Состояние ДО проверки...")
    check1 = client._request(
        "POST",
        "/api/search/product",
        json={
            "filter": [{"field": "id", "type": "equals", "value": product_id}],
            "limit": 1
        }
    )
    
    cover_id_before = None
    media_count_before = 0
    
    if isinstance(check1, dict):
        data_list = check1.get("data", [])
        if data_list:
            attrs = data_list[0].get("attributes", {})
            cover_id_before = attrs.get("coverId")
            print(f"  coverId: {cover_id_before}")
            
            # Проверяем media count
            media_search = client._request(
                "POST",
                "/api/search/product-media",
                json={
                    "filter": [{"field": "productId", "type": "equals", "value": product_id}],
                    "limit": 100
                }
            )
            if isinstance(media_search, dict):
                media_list = media_search.get("data", [])
                media_count_before = len(media_list)
                print(f"  media_count: {media_count_before}")
    
    if not cover_id_before:
        print(f"\n[INFO] coverId отсутствует, требуется установка через UPDATE")
        print(f"[INFO] Запустите UPDATE для этого товара через full_import.py")
        return 0
    
    # Проверяем сразу после установки (если coverId есть)
    print(f"\n[CHECK 2] Проверка сразу...")
    time.sleep(0.3)
    check2 = client._request(
        "POST",
        "/api/search/product",
        json={
            "filter": [{"field": "id", "type": "equals", "value": product_id}],
            "limit": 1
        }
    )
    
    cover_id_immediate = None
    if isinstance(check2, dict):
        data_list = check2.get("data", [])
        if data_list:
            attrs = data_list[0].get("attributes", {})
            cover_id_immediate = attrs.get("coverId")
            print(f"  coverId: {cover_id_immediate}")
    
    # Проверяем после задержки
    print(f"\n[CHECK 3] Проверка после задержки (2 сек)...")
    time.sleep(2.0)
    check3 = client._request(
        "POST",
        "/api/search/product",
        json={
            "filter": [{"field": "id", "type": "equals", "value": product_id}],
            "limit": 1
        }
    )
    
    cover_id_after_delay = None
    if isinstance(check3, dict):
        data_list = check3.get("data", [])
        if data_list:
            attrs = data_list[0].get("attributes", {})
            cover_id_after_delay = attrs.get("coverId")
            print(f"  coverId: {cover_id_after_delay}")
    
    # Финальный вывод
    print("\n" + "="*70)
    print("[RESULT]")
    print("="*70)
    
    if cover_id_before:
        if cover_id_immediate == cover_id_before and cover_id_after_delay == cover_id_before:
            print(f"[SUCCESS] coverId стабильно сохраняется!")
            print(f"  До проверки: {cover_id_before}")
            print(f"  Сразу: {cover_id_immediate}")
            print(f"  После задержки: {cover_id_after_delay}")
            print(f"\n[OK] Откат coverId НЕ происходит")
            return 0
        else:
            print(f"[FAIL] coverId не сохраняется стабильно")
            print(f"  До проверки: {cover_id_before}")
            print(f"  Сразу: {cover_id_immediate}")
            print(f"  После задержки: {cover_id_after_delay}")
            return 1
    else:
        print(f"[INFO] coverId отсутствует, требуется UPDATE")
        return 0


if __name__ == "__main__":
    sys.exit(main())





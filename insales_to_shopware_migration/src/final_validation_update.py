#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Финальная валидация UPDATE: проверка media_count, coverId, customFields.internal_barcode.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from clients.shopware_client import ShopwareClient, ShopwareConfig
from full_import import load_json, find_product_by_number


def main() -> int:
    """Финальная валидация UPDATE."""
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
    print("[FINAL VALIDATION] Проверка UPDATE: media_count, coverId, customFields")
    print("="*70)
    
    # Находим товар
    product_id = find_product_by_number(client, product_number)
    if not product_id:
        print(f"[ERROR] Товар не найден: {product_number}")
        return 1
    
    print(f"[OK] Товар найден: {product_id}")
    
    # Проверяем состояние ДО UPDATE
    print(f"\n[CHECK BEFORE] Состояние ДО UPDATE...")
    check_before = client._request(
        "POST",
        "/api/search/product",
        json={
            "filter": [{"field": "id", "type": "equals", "value": product_id}],
            "limit": 1
        }
    )
    
    media_count_before = 0
    cover_id_before = None
    barcode_before = None
    
    if isinstance(check_before, dict):
        data_list = check_before.get("data", [])
        if data_list:
            attrs = data_list[0].get("attributes", {})
            cover_id_before = attrs.get("coverId")
            
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
            
            # Проверяем customFields
            custom_fields = attrs.get("customFields", {})
            barcode_before = custom_fields.get("internal_barcode")
    
    print(f"  media_count: {media_count_before}")
    print(f"  coverId: {cover_id_before}")
    print(f"  internal_barcode: {barcode_before}")
    
    # Запускаем UPDATE через full_import.py
    print(f"\n[UPDATE] Запуск UPDATE через full_import.py...")
    import subprocess
    import os
    
    script_dir = Path(__file__).parent
    result = subprocess.run(
        [sys.executable, str(script_dir / "full_import.py"), "--source", "snapshot", "--limit", "1"],
        cwd=str(script_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    
    if result.returncode != 0:
        print(f"[ERROR] UPDATE завершился с ошибкой:")
        print(result.stderr)
        return 1
    
    print(f"[OK] UPDATE выполнен (exit code: {result.returncode})")
    
    # Ждем применения изменений
    time.sleep(1.0)
    
    # Проверяем состояние ПОСЛЕ UPDATE
    print(f"\n[CHECK AFTER] Состояние ПОСЛЕ UPDATE...")
    check_after = client._request(
        "POST",
        "/api/search/product",
        json={
            "filter": [{"field": "id", "type": "equals", "value": product_id}],
            "limit": 1
        }
    )
    
    media_count_after = 0
    cover_id_after = None
    barcode_after = None
    
    if isinstance(check_after, dict):
        data_list = check_after.get("data", [])
        if data_list:
            attrs = data_list[0].get("attributes", {})
            cover_id_after = attrs.get("coverId")
            
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
                media_count_after = len(media_list)
            
            # Проверяем customFields
            custom_fields = attrs.get("customFields", {})
            barcode_after = custom_fields.get("internal_barcode")
    
    print(f"  media_count: {media_count_after}")
    print(f"  coverId: {cover_id_after}")
    print(f"  internal_barcode: {barcode_after}")
    
    # Финальная проверка
    print("\n" + "="*70)
    print("[RESULT]")
    print("="*70)
    
    checks = {
        "media_count > 0": media_count_after > 0,
        "coverId установлен": cover_id_after is not None and cover_id_after != "",
        "customFields.internal_barcode сохранён": barcode_after is not None
    }
    
    all_ok = True
    for check_name, check_result in checks.items():
        status = "[OK]" if check_result else "[FAIL]"
        print(f"{status} {check_name}: {check_result}")
        if not check_result:
            all_ok = False
    
    if all_ok:
        print("\n[SUCCESS] Все проверки пройдены!")
        print("[OK] Image pipeline считается каноническим и закрытым")
        return 0
    else:
        print("\n[FAIL] Некоторые проверки не пройдены")
        return 1


if __name__ == "__main__":
    sys.exit(main())


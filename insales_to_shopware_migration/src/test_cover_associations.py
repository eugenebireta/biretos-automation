#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест установки cover через associations.cover вместо прямого поля coverId.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from clients.shopware_client import ShopwareClient, ShopwareConfig
from full_import import load_json, find_product_by_number, download_and_upload_image


def main() -> int:
    """Тестирует установку cover через associations."""
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
    print("[TEST] Установка cover через associations.cover")
    print("="*70)
    
    # Находим товар
    product_id = find_product_by_number(client, product_number)
    if not product_id:
        print(f"[ERROR] Товар не найден: {product_number}")
        return 1
    
    print(f"[OK] Товар найден: {product_id}")
    
    # Загружаем изображение
    snapshot_path = Path(__file__).parent.parent / "insales_snapshot" / "products.ndjson"
    import json
    test_media_id = None
    with open(snapshot_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                variant = data.get("variants", [{}])[0] if data.get("variants") else {}
                if variant.get("sku") == product_number:
                    images = data.get("images", [])
                    if images and len(images) > 0:
                        url = images[0].get("original_url")
                        if url:
                            test_media_id = download_and_upload_image(client, url, product_number)
                            break
            except Exception:
                continue
    
    if not test_media_id:
        print(f"[ERROR] Не удалось загрузить изображение")
        return 1
    
    print(f"[OK] Изображение загружено: {test_media_id}")
    
    # Удаляем старые product_media
    try:
        pm_search = client._request(
            "POST",
            "/api/search/product-media",
            json={
                "filter": [{"field": "productId", "type": "equals", "value": product_id}],
                "limit": 100
            }
        )
        if isinstance(pm_search, dict):
            pm_list = pm_search.get("data", [])
            for pm in pm_list:
                pm_id = pm.get("id")
                if pm_id:
                    try:
                        client._request("DELETE", f"/api/product-media/{pm_id}")
                    except Exception:
                        pass
    except Exception:
        pass
    
    time.sleep(0.5)
    
    # Создаем product_media
    print(f"\n[STEP 1] Создание product_media...")
    product_media_id = client.create_product_media(
        product_id=product_id,
        media_id=test_media_id,
        position=0
    )
    
    if not product_media_id:
        print(f"[ERROR] Не удалось создать product_media")
        return 1
    
    print(f"[OK] product_media создан: {product_media_id}")
    
    time.sleep(0.3)
    
    # Устанавливаем cover через associations
    print(f"\n[STEP 2] Установка cover через associations.cover...")
    success = client.set_product_cover(product_id, product_media_id)
    
    if not success:
        print(f"[ERROR] Не удалось установить cover")
        return 1
    
    print(f"[OK] PATCH выполнен")
    
    # Проверка сразу
    print(f"\n[CHECK 1] Проверка сразу после PATCH...")
    time.sleep(0.3)
    check1 = client._request(
        "POST",
        "/api/search/product",
        json={
            "filter": [{"field": "id", "type": "equals", "value": product_id}],
            "limit": 1
        }
    )
    if isinstance(check1, dict):
        data_list = check1.get("data", [])
        if data_list:
            attrs = data_list[0].get("attributes", {})
            cover_id_1 = attrs.get("coverId")
            print(f"  coverId: {cover_id_1}")
    
    # Проверка с задержкой
    print(f"\n[CHECK 2] Проверка после задержки (2 сек)...")
    time.sleep(2.0)
    check2 = client._request(
        "POST",
        "/api/search/product",
        json={
            "filter": [{"field": "id", "type": "equals", "value": product_id}],
            "limit": 1
        }
    )
    if isinstance(check2, dict):
        data_list = check2.get("data", [])
        if data_list:
            attrs = data_list[0].get("attributes", {})
            cover_id_2 = attrs.get("coverId")
            print(f"  coverId: {cover_id_2}")
    
    # Финальный вывод
    print("\n" + "="*70)
    print("[RESULT]")
    print("="*70)
    
    if cover_id_1 == product_media_id and cover_id_2 == product_media_id:
        print(f"[SUCCESS] coverId установлен и сохранен!")
        print(f"  Сразу: {cover_id_1}")
        print(f"  После задержки: {cover_id_2}")
        return 0
    else:
        print(f"[FAIL] coverId не сохраняется")
        print(f"  Сразу: {cover_id_1}")
        print(f"  После задержки: {cover_id_2}")
        return 1


if __name__ == "__main__":
    sys.exit(main())





#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Диагностика результата UPDATE через Search API.
Проверяет coverId, customFields и media через правильные associations.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from clients.shopware_client import ShopwareClient, ShopwareConfig
from full_import import load_json, find_product_by_number


def main() -> int:
    """Проверяет результат UPDATE через Search API с associations."""
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
    print("[DIAGNOSTIC] Проверка результата UPDATE через Search API")
    print("="*70)
    
    # Выполняем поиск через Search API с associations
    print(f"\n[INFO] Поиск товара через Search API: productNumber = {product_number}")
    
    search_payload = {
        "filter": [
            {"field": "productNumber", "type": "equals", "value": product_number}
        ],
        "limit": 1,
        "associations": {
            "media": {},
            "cover": {}
        },
        "includes": {
            "product": ["id", "productNumber", "coverId", "customFields"]
        }
    }
    
    try:
        search_result = client._request(
            "POST",
            "/api/search/product",
            json=search_payload
        )
    except Exception as e:
        print(f"[ERROR] Ошибка Search API: {e}")
        return 1
    
    if not isinstance(search_result, dict):
        print(f"[ERROR] Неожиданный формат ответа Search API")
        return 1
    
    data_list = search_result.get("data", [])
    if not data_list:
        print(f"[ERROR] Товар не найден: {product_number}")
        return 1
    
    product = data_list[0]
    
    print("\n" + "="*70)
    print("[SEARCH API RESULT] Данные товара:")
    print("="*70)
    
    # Основные поля
    product_id = product.get("id")
    product_number_found = product.get("productNumber")
    cover_id = product.get("coverId")
    
    print(f"\nproduct.id: {product_id}")
    print(f"product.productNumber: {product_number_found}")
    print(f"product.coverId: {cover_id}")
    
    # Проверяем cover association
    cover = product.get("cover")
    if cover:
        cover_pm_id = cover.get("id")
        cover_media_id = cover.get("mediaId")
        print(f"\ncover.id: {cover_pm_id}")
        print(f"cover.mediaId: {cover_media_id}")
    else:
        print(f"\ncover: None (association отсутствует)")
        cover_pm_id = None
        cover_media_id = None
    
    # Проверяем customFields
    custom_fields = product.get("customFields")
    if custom_fields:
        internal_barcode = custom_fields.get("internal_barcode")
        print(f"\ncustomFields: {custom_fields}")
        print(f"customFields.internal_barcode: {internal_barcode}")
    else:
        print(f"\ncustomFields: None")
        internal_barcode = None
    
    # Проверяем media association
    media_list = product.get("media")
    if media_list:
        media_count = len(media_list)
        print(f"\nmedia (association): {media_count} элементов")
        for idx, media_item in enumerate(media_list[:3]):  # Показываем первые 3
            print(f"  [{idx}] mediaId: {media_item.get('mediaId')}, position: {media_item.get('position')}")
    else:
        print(f"\nmedia (association): None")
        media_count = 0
    
    # Дополнительная проверка через прямой GET с явными полями
    print("\n" + "="*70)
    print("[DIRECT GET CHECK] Проверка через GET /api/product/{id}:")
    print("="*70)
    
    try:
        direct_get = client._request("GET", f"/api/product/{product_id}")
        if isinstance(direct_get, dict):
            direct_data = direct_get.get("data", direct_get)
            print(f"\nGET /api/product/{product_id}:")
            print(f"  productNumber: {direct_data.get('productNumber')}")
            print(f"  coverId: {direct_data.get('coverId')}")
            print(f"  customFields: {direct_data.get('customFields')}")
            
            # Обновляем значения из GET, если они есть
            if direct_data.get('coverId'):
                cover_id = direct_data.get('coverId')
            if direct_data.get('customFields'):
                custom_fields = direct_data.get('customFields')
                internal_barcode = custom_fields.get('internal_barcode')
    except Exception as e:
        print(f"[WARNING] Ошибка GET запроса: {e}")
    
    # Дополнительная проверка через product_media search
    print("\n" + "="*70)
    print("[ADDITIONAL CHECK] Проверка product_media через Search API:")
    print("="*70)
    
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
            print(f"\nproduct_media count: {len(pm_list)}")
            
            # Ищем product_media с position=0 (должен быть cover)
            cover_pm = None
            for pm in pm_list:
                if pm.get("position") == 0:
                    cover_pm = pm
                    break
            
            if cover_pm:
                print(f"product_media[position=0].id: {cover_pm.get('id')}")
                print(f"product_media[position=0].mediaId: {cover_pm.get('mediaId')}")
                
                # Сравниваем с coverId
                if cover_id and cover_id == cover_pm.get("id"):
                    print(f"[OK] coverId совпадает с product_media[position=0].id")
                elif cover_id:
                    print(f"[WARNING] coverId ({cover_id}) != product_media[position=0].id ({cover_pm.get('id')})")
                else:
                    print(f"[INFO] coverId отсутствует, но product_media[position=0] существует: {cover_pm.get('id')}")
    except Exception as e:
        print(f"[WARNING] Ошибка проверки product_media: {e}")
    
    # Получаем значение штрих-кода из snapshot для сравнения
    print("\n" + "="*70)
    print("[COMPARISON] Сравнение с данными из InSales snapshot:")
    print("="*70)
    
    snapshot_path = Path(__file__).parent.parent / "insales_snapshot" / "products.ndjson"
    if snapshot_path.exists():
        with open(snapshot_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    variant = data.get("variants", [{}])[0] if data.get("variants") else {}
                    if variant.get("sku") == product_number:
                        snapshot_barcode = variant.get("barcode")
                        print(f"\nInSales snapshot barcode: {snapshot_barcode}")
                        
                        if internal_barcode:
                            if str(internal_barcode) == str(snapshot_barcode):
                                print(f"[OK] internal_barcode совпадает с snapshot: {internal_barcode}")
                            else:
                                print(f"[WARNING] internal_barcode ({internal_barcode}) != snapshot ({snapshot_barcode})")
                        else:
                            print(f"[FAIL] internal_barcode отсутствует в Shopware")
                        break
                except Exception:
                    continue
    
    # Финальный вывод
    print("\n" + "="*70)
    print("[FINAL DIAGNOSIS]")
    print("="*70)
    
    has_cover = cover_id is not None and cover_id != ""
    has_barcode = internal_barcode is not None and internal_barcode != ""
    has_media = media_count > 0
    
    print(f"\ncoverId присутствует: {has_cover} ({cover_id})")
    print(f"internal_barcode присутствует: {has_barcode} ({internal_barcode})")
    print(f"media присутствует: {has_media} (count: {media_count})")
    
    if has_cover and cover_pm_id:
        print(f"\ncoverId ссылается на product_media.id: {cover_id == cover_pm_id}")
    
    print("\n" + "="*70)
    if has_cover and has_barcode and has_media:
        print("[CONCLUSION] Данные ПРИСУТСТВУЮТ в Shopware")
        print("Проблема была в GET API, который не возвращал associations")
    elif not has_cover and not has_barcode:
        print("[CONCLUSION] Данные ОТСУТСТВУЮТ в Shopware")
        print("UPDATE не сохранил coverId и customFields")
    else:
        print("[CONCLUSION] Частичное присутствие данных")
        print(f"  - coverId: {'OK' if has_cover else 'MISSING'}")
        print(f"  - barcode: {'OK' if has_barcode else 'MISSING'}")
        print(f"  - media: {'OK' if has_media else 'MISSING'}")
    print("="*70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


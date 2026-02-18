#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Финальная диагностика: почему изображения не отображаются в listing
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from full_import import find_product_by_number

def final_diagnosis(product_number: str):
    """Финальная диагностика"""
    config_path = Path(__file__).parent.parent / "config.json"
    with config_path.open(encoding="utf-8") as f:
        config = json.load(f)
    
    sw = config["shopware"]
    client = ShopwareClient(ShopwareConfig(sw["url"], sw["access_key_id"], sw["secret_access_key"]))
    
    product_id = find_product_by_number(client, product_number)
    if not product_id:
        print(f"[ERROR] Товар {product_number} не найден")
        return
    
    # Получаем coverId
    response = client._request("GET", f"/api/product/{product_id}")
    if isinstance(response, dict):
        data = response.get("data", {})
        attributes = data.get("attributes", {})
        cover_id = attributes.get("coverId")
    
    print("=" * 80)
    print("ФИНАЛЬНАЯ ДИАГНОСТИКА: ПОЧЕМУ ИЗОБРАЖЕНИЯ НЕ В LISTING")
    print("=" * 80)
    print(f"Product ID: {product_id}")
    print(f"Product Number: {product_number}")
    print(f"Cover ID: {cover_id}")
    print()
    
    # Проверка 1: product_media через API
    print("=" * 80)
    print("1. ПРОВЕРКА PRODUCT_MEDIA ЧЕРЕЗ API")
    print("=" * 80)
    
    try:
        media_response = client._request("GET", f"/api/product/{product_id}/media")
        if isinstance(media_response, dict):
            media_list = media_response.get("data", [])
            print(f"Product-media записей через API: {len(media_list)}")
            
            if len(media_list) == 0:
                print("[КРИТИЧЕСКАЯ ПРОБЛЕМА] Нет записей в product_media!")
                print("  Это означает, что медиа не привязаны к товару через product_media таблицу.")
                print("  coverId установлен, но связь product_media отсутствует.")
            else:
                print("\nНайденные записи:")
                for idx, pm in enumerate(media_list[:5]):
                    pm_attrs = pm.get("attributes", {})
                    media_id = pm_attrs.get("mediaId") or pm.get("mediaId")
                    position = pm_attrs.get("position") or pm.get("position")
                    is_cover = pm_attrs.get("isCover") or pm.get("isCover")
                    
                    print(f"  [{idx}] Product-Media ID: {pm.get('id')}")
                    print(f"      Media ID: {media_id}")
                    print(f"      Position: {position}")
                    print(f"      IsCover: {is_cover}")
                    print(f"      Совпадает с coverId: {media_id == cover_id}")
                    if media_id == cover_id:
                        print(f"      *** ЭТО COVER МЕДИА ***")
    except Exception as e:
        print(f"[ERROR] Ошибка получения product_media: {e}")
    
    # Проверка 2: thumbnails
    print("\n" + "=" * 80)
    print("2. ПРОВЕРКА THUMBNAILS")
    print("=" * 80)
    
    if cover_id:
        try:
            thumb_response = client._request("GET", f"/api/media/{cover_id}/thumbnails")
            if isinstance(thumb_response, dict):
                thumb_list = thumb_response.get("data", [])
                print(f"Thumbnails для cover медиа: {len(thumb_list)}")
                
                if len(thumb_list) == 0:
                    print("[ПРОБЛЕМА] Thumbnails не сгенерированы!")
                    print("  Это может быть причиной отсутствия изображений в listing.")
                else:
                    print("\nНайденные thumbnails:")
                    for thumb in thumb_list[:3]:
                        thumb_attrs = thumb.get("attributes", {})
                        width = thumb_attrs.get("width") or thumb.get("width")
                        height = thumb_attrs.get("height") or thumb.get("height")
                        url = thumb_attrs.get("url") or thumb.get("url")
                        print(f"  - {width}x{height}: {url}")
        except Exception as e:
            print(f"[ERROR] Ошибка получения thumbnails: {e}")
    
    # Выводы
    print("\n" + "=" * 80)
    print("ВЫВОДЫ")
    print("=" * 80)
    print()
    print("ПРОБЛЕМЫ ОБНАРУЖЕНЫ:")
    print()
    print("1. PRODUCT_MEDIA:")
    print("   - Если записей нет - медиа не привязаны к товару через product_media")
    print("   - coverId установлен, но связь отсутствует")
    print("   - Решение: нужно создать product_media записи через API")
    print()
    print("2. THUMBNAILS:")
    print("   - Если thumbnails нет - изображения не могут отображаться в listing")
    print("   - Решение: запустить media:generate-thumbnails")
    print()
    print("3. PRODUCT_LISTING_INDEX:")
    print("   - Таблица может не существовать или быть пустой")
    print("   - Решение: запустить dal:refresh:index для перестроения индексов")
    print()
    print("КОРНЕВАЯ ПРИЧИНА:")
    print("   Когда мы устанавливали coverId через PATCH /api/product/{id},")
    print("   Shopware НЕ создал автоматически запись в product_media.")
    print("   Нужно явно создавать product_media через POST /api/product-media")
    print("   или через Sync API с правильной структурой.")
    print()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-number", default="500944170")
    args = parser.parse_args()
    final_diagnosis(args.product_number)


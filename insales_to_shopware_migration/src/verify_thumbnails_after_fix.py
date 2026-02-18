#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка thumbnails после восстановления"""
import json
from pathlib import Path
from clients import ShopwareClient, ShopwareConfig

config_path = Path(__file__).parent.parent / "config.json"
with config_path.open(encoding="utf-8") as f:
    config = json.load(f)

sw = config["shopware"]
client = ShopwareClient(ShopwareConfig(sw["url"], sw["access_key_id"], sw["secret_access_key"]))

product_id = "019b1958a54b726c81a9d01ab4652826"
cover_id = "fc164f4bb8154c5493ee7cbaefa82a69"

print("=" * 80)
print("ПРОВЕРКА THUMBNAILS ПОСЛЕ ВОССТАНОВЛЕНИЯ")
print("=" * 80)
print(f"Product ID: {product_id}")
print(f"Cover ID: {cover_id}")
print()

# Проверяем thumbnails
try:
    thumb_response = client._request("GET", f"/api/media/{cover_id}/thumbnails")
    if isinstance(thumb_response, dict):
        thumb_list = thumb_response.get("data", [])
        print(f"Thumbnails для cover медиа: {len(thumb_list)}")
        
        if len(thumb_list) == 0:
            print("[ПРОБЛЕМА] Thumbnails все еще отсутствуют!")
        else:
            print("\n[SUCCESS] Thumbnails сгенерированы:")
            for idx, thumb in enumerate(thumb_list[:5], 1):
                thumb_attrs = thumb.get("attributes", {})
                width = thumb_attrs.get("width") or thumb.get("width")
                height = thumb_attrs.get("height") or thumb.get("height")
                url = thumb_attrs.get("url") or thumb.get("url")
                print(f"  [{idx}] {width}x{height}")
                if url:
                    print(f"      URL: {url}")
except Exception as e:
    print(f"[ERROR] Ошибка проверки thumbnails: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 80)
print("СТАТУС")
print("=" * 80)
print("Если thumbnails > 0, то listing должен начать отображать изображения.")
print("Проверьте вручную в storefront категории с товаром.")





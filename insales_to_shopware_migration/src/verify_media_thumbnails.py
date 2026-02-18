#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка наличия thumbnails для медиа товара
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from full_import import find_product_by_number

def verify_product_media(product_number: str):
    """Проверяет медиа и thumbnails для товара"""
    config_path = Path(__file__).parent.parent / "config.json"
    with config_path.open() as f:
        config = json.load(f)
    
    sw = config["shopware"]
    client = ShopwareClient(ShopwareConfig(sw["url"], sw["access_key_id"], sw["secret_access_key"]))
    
    product_id = find_product_by_number(client, product_number)
    if not product_id:
        print(f"[ERROR] Товар {product_number} не найден")
        return
    
    print(f"Product ID: {product_id}")
    
    # Получаем товар с медиа
    response = client._request(
        "GET",
        f"/api/product/{product_id}",
        params={"associations[media]": "{}"}
    )
    
    if isinstance(response, dict):
        data = response.get("data", {})
        # Медиа может быть в data.media или в associations
        media = data.get("media", [])
        if not media:
            # Пробуем получить через associations
            associations = data.get("associations", {})
            media_assoc = associations.get("media", {})
            if isinstance(media_assoc, dict):
                media_data = media_assoc.get("data", [])
                if media_data:
                    media = media_data
        
        # coverId может быть в data или data.attributes
        cover_id = data.get("coverId")
        if cover_id is None:
            attributes = data.get("attributes", {})
            if isinstance(attributes, dict):
                cover_id = attributes.get("coverId")
        
        print(f"\nМедиа товара: {len(media)}")
        print(f"Cover ID: {cover_id}")
        
        for idx, media_item in enumerate(media, 1):
            media_id = media_item.get("id")
            print(f"\n[{idx}] Media ID: {media_id}")
            
            # Проверяем thumbnails через API
            try:
                thumb_response = client._request(
                    "GET",
                    f"/api/media/{media_id}",
                    params={"associations[thumbnails]": "{}"}
                )
                if isinstance(thumb_response, dict):
                    thumb_data = thumb_response.get("data", {})
                    thumbnails = thumb_data.get("thumbnails", [])
                    print(f"    Thumbnails: {len(thumbnails)}")
                    for thumb in thumbnails:
                        width = thumb.get("width")
                        height = thumb.get("height")
                        url = thumb.get("url")
                        print(f"      - {width}x{height}: {url}")
            except Exception as e:
                print(f"    Ошибка проверки thumbnails: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-number", required=True)
    args = parser.parse_args()
    verify_product_media(args.product_number)


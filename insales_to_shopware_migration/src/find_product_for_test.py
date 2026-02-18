#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Находит товар для теста пересоздания медиа"""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig

config_path = Path(__file__).parent.parent / "config.json"
with config_path.open() as f:
    config = json.load(f)

sw = config["shopware"]
client = ShopwareClient(ShopwareConfig(sw["url"], sw["access_key_id"], sw["secret_access_key"]))

# Получаем список товаров
response = client._request("GET", "/api/product", params={"limit": 10})
if isinstance(response, dict):
    products = response.get("data", [])
    print("Товары в Shopware:")
    for p in products:
        product_id = p.get("id")
        product_number = p.get("productNumber")
        name = p.get("name")
        print(f"  {product_number} - {name} (ID: {product_id})")
        
        # Проверяем наличие медиа
        try:
            prod_response = client._request(
                "GET",
                f"/api/product/{product_id}",
                params={"associations[media]": "{}"}
            )
            if isinstance(prod_response, dict):
                prod_data = prod_response.get("data", {})
                media = prod_data.get("media", [])
                if media:
                    print(f"    ✓ Имеет {len(media)} медиа")
                    print(f"    → Используйте: python recreate_product_media.py --product-number {product_number}")
                    break
        except:
            pass





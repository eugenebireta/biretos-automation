#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка структуры медиа в ответе API"""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig

config_path = Path(__file__).parent.parent / "config.json"
with config_path.open(encoding="utf-8") as f:
    config = json.load(f)

sw = config["shopware"]
client = ShopwareClient(ShopwareConfig(sw["url"], sw["access_key_id"], sw["secret_access_key"]))

product_id = "019b1958a54b726c81a9d01ab4652826"

# Пробуем разные способы получения медиа
print("Способ 1: GET с associations[media]")
response1 = client._request(
    "GET",
    f"/api/product/{product_id}",
    params={"associations[media]": "{}"}
)
print(f"Keys in data: {list(response1.get('data', {}).keys())[:10]}")
print(f"Media in data: {response1.get('data', {}).get('media')}")
print(f"Associations: {list(response1.get('data', {}).get('associations', {}).keys())}")

print("\nСпособ 2: POST search с associations")
response2 = client._request(
    "POST",
    "/api/search/product",
    json={
        "filter": [{"field": "id", "type": "equals", "value": product_id}],
        "associations": {"product": ["id", "media", "coverId"]},
        "limit": 1
    }
)
print(f"Response keys: {list(response2.keys())}")
if isinstance(response2, dict):
    data = response2.get("data", [])
    if data:
        product = data[0]
        print(f"Product keys: {list(product.keys())[:10]}")
        print(f"Media: {product.get('media')}")





#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка структуры ответа API для товара"""
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
response = client._request("GET", f"/api/product/{product_id}")

print("Полная структура ответа:")
print(json.dumps(response, indent=2, ensure_ascii=False))

print("\n" + "="*80)
print("Поиск productNumber:")
if isinstance(response, dict):
    data = response.get("data", {})
    if isinstance(data, dict):
        # Проверяем разные места
        print(f"data.productNumber: {data.get('productNumber')}")
        print(f"data.attributes.productNumber: {data.get('attributes', {}).get('productNumber')}")
        print(f"data.get('productNumber'): {data.get('productNumber')}")
        
        # Пробуем найти все ключи с "number" или "sku"
        for key in data.keys():
            if 'number' in key.lower() or 'sku' in key.lower():
                print(f"  Найден ключ: {key} = {data.get(key)}")


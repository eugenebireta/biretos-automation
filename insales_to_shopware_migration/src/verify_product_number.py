#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка productNumber после восстановления"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from full_import import find_product_by_number

def verify_product_number(product_id: str):
    """Проверяет productNumber для товара"""
    config_path = Path(__file__).parent.parent / "config.json"
    with config_path.open(encoding="utf-8") as f:
        config = json.load(f)
    
    sw = config["shopware"]
    client = ShopwareClient(ShopwareConfig(sw["url"], sw["access_key_id"], sw["secret_access_key"]))
    
    try:
        response = client._request("GET", f"/api/product/{product_id}")
        if isinstance(response, dict):
            data = response.get("data", {})
            # productNumber может быть в data или data.attributes
            product_number = data.get("productNumber")
            if product_number is None and isinstance(data.get("attributes"), dict):
                product_number = data.get("attributes", {}).get("productNumber")
            name = data.get("name")
            if name is None and isinstance(data.get("attributes"), dict):
                name = data.get("attributes", {}).get("name")
            
            print(f"Product ID: {product_id}")
            print(f"Название: {name}")
            print(f"Product Number: {product_number}")
            
            if product_number:
                print(f"[OK] productNumber установлен: {product_number}")
                
                # Проверяем, что можно найти по productNumber
                found_id = find_product_by_number(client, product_number)
                if found_id == product_id:
                    print(f"[OK] Товар найден по productNumber: {product_number}")
                else:
                    print(f"[WARNING] Товар не найден по productNumber (найден другой ID: {found_id})")
            else:
                print(f"[ERROR] productNumber не установлен (None)")
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-id", required=True)
    args = parser.parse_args()
    verify_product_number(args.product_id)


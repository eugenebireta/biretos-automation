#!/usr/bin/env python3
"""Проверка корректности установки coverId после исправления."""

import sys
import os
import json
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))

from clients.shopware_client import ShopwareClient

def main():
    # Загружаем конфигурацию
    config_path = Path(__file__).parent.parent / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config_data = json.load(f)
        shopware_config = config_data.get("shopware", {})
        if "url" in shopware_config and "api_base" not in shopware_config:
            shopware_config["api_base"] = shopware_config["url"]
        config = type('Config', (), shopware_config)()
    
    client = ShopwareClient(config=config, timeout=10)
    
    sku = "500944170"
    print(f"[VERIFY] Проверка товара по SKU: {sku}")
    
    try:
        # Находим товар
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [{"field": "productNumber", "type": "equals", "value": sku}],
                "limit": 1,
                "includes": {"product": ["id", "productNumber", "coverId"]}
            }
        )
        
        if isinstance(response, dict):
            data = response.get("data", [])
            if not data:
                print(f"[ERROR] Товар с SKU {sku} не найден")
                return 1
            
            product = data[0]
            product_id = product.get("id")
            # coverId может быть в attributes или напрямую
            cover_id = product.get("coverId") or product.get("attributes", {}).get("coverId")
            
            print(f"\n[FACT] product_id: {product_id}")
            print(f"[FACT] coverId: {cover_id}")
            
            # Проверка 1: coverId IS NOT NULL
            if not cover_id:
                print("[FAIL] coverId IS NULL")
                return 1
            else:
                print("[OK] coverId IS NOT NULL")
            
            # Проверка 2: coverId EXISTS in product_media
            pm_response = client._request("GET", f"/api/product-media/{cover_id}")
            if isinstance(pm_response, dict) and "data" in pm_response:
                pm_data = pm_response.get("data", {})
                # product_media использует attributes для полей
                pm_attributes = pm_data.get("attributes", {})
                pm_product_id = pm_attributes.get("productId") or pm_data.get("productId")
                pm_media_id = pm_attributes.get("mediaId") or pm_data.get("mediaId")
                
                print(f"[OK] coverId EXISTS in product_media")
                print(f"[FACT] product_media.productId: {pm_product_id}")
                print(f"[FACT] product_media.mediaId: {pm_media_id}")
                
                # Проверка 3: product_media.mediaId EXISTS in media
                if pm_media_id:
                    media_response = client._request("GET", f"/api/media/{pm_media_id}")
                    if isinstance(media_response, dict) and "data" in media_response:
                        print(f"[OK] product_media.mediaId EXISTS in media")
                    else:
                        print(f"[FAIL] product_media.mediaId DOES NOT EXIST in media")
                        return 1
                else:
                    print(f"[FAIL] product_media.mediaId IS NULL")
                    return 1
                
                # Проверка соответствия product_id
                if pm_product_id != product_id:
                    print(f"[FAIL] product_media.productId ({pm_product_id}) != product.id ({product_id})")
                    return 1
                else:
                    print(f"[OK] product_media.productId matches product.id")
            else:
                print(f"[FAIL] coverId DOES NOT EXIST in product_media")
                return 1
            
            # Проверка количества media
            media_list_response = client._request("GET", f"/api/product/{product_id}/media")
            if isinstance(media_list_response, dict):
                media_list = media_list_response.get("data", [])
                media_count = len(media_list) if isinstance(media_list, list) else 0
                print(f"\n[FACT] media count: {media_count}")
            
            print(f"\n{'='*60}")
            print(f"РЕЗУЛЬТАТ: ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
            print(f"{'='*60}")
            
            return 0
        else:
            print("[ERROR] Неожиданный формат ответа API")
            return 1
            
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())


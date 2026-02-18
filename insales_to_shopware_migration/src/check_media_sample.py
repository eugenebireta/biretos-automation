"""Проверка нескольких media для диагностики"""
import json
from pathlib import Path
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

with CONFIG_PATH.open() as f:
    config = json.load(f)

client = ShopwareClient(
    ShopwareConfig(
        config["shopware"]["url"],
        config["shopware"]["access_key_id"],
        config["shopware"]["secret_access_key"]
    )
)

# Получаем первые 5 media
response = client._request(
    "POST",
    "/api/search/media",
    json={
        "limit": 5,
        "includes": {"media": ["id", "fileName", "mimeType"]}
    }
)

print("Проверка первых 5 media:")
print("=" * 80)

for media in response.get("data", []):
    media_id = media.get("id")
    file_name = media.get("fileName", "N/A")
    
    print(f"\nMedia: {file_name} (ID: {media_id})")
    
    # Проверяем product-media
    try:
        pm_response = client._request(
            "POST",
            "/api/search/product-media",
            json={
                "filter": [{"field": "mediaId", "type": "equals", "value": media_id}],
                "limit": 1
            }
        )
        pm_count = pm_response.get("total", 0)
        print(f"  product-media: {pm_count}")
    except Exception as e:
        print(f"  product-media: ERROR - {e}")
    
    # Проверяем через GET API
    try:
        full_response = client._request("GET", f"/api/media/{media_id}")
        data = full_response.get("data", {})
        relationships = data.get("relationships", {})
        print(f"  relationships keys: {list(relationships.keys())}")
        print(f"  productMedia: {bool(relationships.get('productMedia'))}")
        print(f"  categories: {bool(relationships.get('categories'))}")
        print(f"  productManufacturers: {bool(relationships.get('productManufacturers'))}")
    except Exception as e:
        print(f"  GET API: ERROR - {e}")


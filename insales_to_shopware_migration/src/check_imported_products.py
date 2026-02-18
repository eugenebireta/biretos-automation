"""Проверка последних импортированных товаров"""
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

# Получаем последние 10 товаров
resp = client._request(
    "POST",
    "/api/search/product",
    json={
        "limit": 10,
        "sort": [{"field": "createdAt", "order": "DESC"}],
        "includes": {"product": ["id", "productNumber", "name"]},
    },
)

print("Последние 10 созданных товаров:")
print("=" * 80)

for idx, p in enumerate(resp.get("data", [])[:10], 1):
    pid = p.get("id")
    # Получаем полные данные
    full_data = client._request("GET", f"/api/product/{pid}")
    attrs = full_data.get("data", {}).get("attributes", {})
    pn = attrs.get("productNumber")
    name = attrs.get("name", "")[:50]
    base_price = attrs.get("price", [])
    base_price_val = base_price[0].get("gross") if base_price and len(base_price) > 0 else None
    prices = attrs.get("prices", [])
    has_marketplace = len(prices) > 0 if prices else False
    marketplace_price = None
    if prices:
        for price_entry in prices:
            price_list = price_entry.get("price", [])
            if price_list and len(price_list) > 0:
                marketplace_price = price_list[0].get("gross")
                break
    
    print(f"{idx}. ID: {pid}")
    print(f"   productNumber: {pn}")
    print(f"   name: {name}")
    print(f"   base_price: {base_price_val}")
    print(f"   marketplace_price: {marketplace_price} ({'есть' if has_marketplace else 'нет'})")
    print()

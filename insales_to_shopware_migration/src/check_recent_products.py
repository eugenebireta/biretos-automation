"""Проверка последних созданных товаров"""
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

resp = client._request(
    "POST",
    "/api/search/product",
    json={
        "limit": 20,
        "sort": [{"field": "createdAt", "order": "DESC"}],
        "includes": {"product": ["id", "productNumber", "name"]},
    },
)

print(f"Total: {resp.get('total')}")
print("\nПоследние 10 товаров:")
for p in resp.get("data", [])[:10]:
    pid = p.get('id')
    # Получаем полные данные через GET API
    full_data = client._request("GET", f"/api/product/{pid}")
    attrs = full_data.get("data", {}).get("attributes", {})
    pn = attrs.get("productNumber")
    name = attrs.get("name", "")[:50]
    price2_exists = attrs.get("prices") is not None and len(attrs.get("prices", [])) > 0
    print(f"ID: {pid}, productNumber: {pn}, name: {name}, has price2: {price2_exists}")


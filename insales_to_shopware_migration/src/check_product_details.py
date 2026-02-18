"""Проверка деталей товара"""
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

# Ищем товар 500944170
from clients import ShopwareClient, ShopwareConfig
import json
from pathlib import Path

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

# Ищем товар по productNumber
product_id = client.find_product_by_number("500944170")
if not product_id:
    print("Товар 500944170 не найден")
    exit(1)

print(f"Найден товар с ID: {product_id}\n")
resp = client._request("GET", f"/api/product/{product_id}")
data = resp.get("data", {})
attrs = data.get("attributes", {})

print(f"productNumber (root): {data.get('productNumber')}")
print(f"productNumber (attributes): {attrs.get('productNumber')}")
print(f"name (root): {data.get('name')}")
print(f"name (attributes): {attrs.get('name')}")
print(f"\nprice (root): {data.get('price')}")
print(f"price (attributes): {attrs.get('price')}")
print(f"prices (root): {data.get('prices')}")
print(f"prices (attributes): {attrs.get('prices')}")


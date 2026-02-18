"""Проверка конкретного товара"""
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

product_id = client.find_product_by_number("500944170")
if not product_id:
    print("Товар 500944170 не найден")
    exit(1)

print(f"Товар найден: ID={product_id}\n")

response = client._request("GET", f"/api/product/{product_id}")
data = response.get("data", {})
attrs = data.get("attributes", {})

print(f"productNumber: {attrs.get('productNumber')}")
print(f"name: {attrs.get('name')}")

base_price = attrs.get("price", [])
if base_price and len(base_price) > 0:
    print(f"base_price: {base_price[0].get('gross')}")

prices = attrs.get("prices", [])
print(f"\nprices (advanced): {len(prices)} записей")
for idx, price_entry in enumerate(prices, 1):
    print(f"  [{idx}] ruleId: {price_entry.get('ruleId')}")
    price_list = price_entry.get("price", [])
    if price_list and len(price_list) > 0:
        print(f"      gross: {price_list[0].get('gross')}")
    print(f"      quantityStart: {price_entry.get('quantityStart')}")


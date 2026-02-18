"""Проверка тестового товара 500944170"""
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
product_id = client.find_product_by_number("500944170")
if not product_id:
    print("Товар 500944170 не найден")
    exit(1)

print(f"Найден товар с ID: {product_id}\n")
resp = client._request("GET", f"/api/product/{product_id}")
data = resp.get("data", {})
attrs = data.get("attributes", {})

print("=" * 80)
print("ПРОВЕРКА ТОВАРА 500944170")
print("=" * 80)
print(f"ID: {product_id}")
print(f"productNumber: {attrs.get('productNumber')}")
print(f"name: {attrs.get('name', '')[:50]}")

print("\nBASE PRICE:")
base_price = attrs.get("price")
if base_price and len(base_price) > 0:
    print(f"  gross: {base_price[0].get('gross')}")
    print(f"  net: {base_price[0].get('net')}")
    print(f"  currencyId: {base_price[0].get('currencyId')}")
else:
    print("  НЕТ")

print("\nADVANCED PRICES (product.prices):")
advanced_prices = attrs.get("prices")
if advanced_prices:
    print(f"  Всего записей: {len(advanced_prices)}")
    for idx, price_entry in enumerate(advanced_prices):
        print(f"\n  Запись {idx + 1}:")
        print(f"    ruleId: {price_entry.get('ruleId')}")
        print(f"    quantityStart: {price_entry.get('quantityStart')}")
        price_list = price_entry.get("price", [])
        if price_list:
            for p in price_list:
                print(f"      gross: {p.get('gross')}")
                print(f"      net: {p.get('net')}")
                print(f"      currencyId: {p.get('currencyId')}")
else:
    print("  НЕТ")

# Проверяем Price Rule
print("\nPRICE RULE 'Marketplace Price':")
marketplace_rule_id = client.find_price_rule_by_name("Marketplace Price")
if marketplace_rule_id:
    print(f"  Найден: {marketplace_rule_id}")
    # Проверяем, есть ли цена с этим ruleId
    if advanced_prices:
        for price_entry in advanced_prices:
            if price_entry.get("ruleId") == marketplace_rule_id:
                print(f"  ✓ Marketplace цена найдена в product.prices")
                break
        else:
            print(f"  ✗ Marketplace цена НЕ найдена в product.prices")
else:
    print("  НЕ НАЙДЕН")

# Проверяем ожидаемое значение из snapshot
print("\nОЖИДАЕМОЕ ЗНАЧЕНИЕ (из snapshot):")
snapshot = ROOT / "insales_snapshot" / "products.ndjson"
with snapshot.open("r", encoding="utf-8") as f:
    for line in f:
        try:
            product = json.loads(line)
            variants = product.get("variants", [])
            if variants and str(variants[0].get("sku")) == "500944170":
                price2 = variants[0].get("price2")
                print(f"  price2: {price2}")
                break
        except:
            pass

print("\n" + "=" * 80)


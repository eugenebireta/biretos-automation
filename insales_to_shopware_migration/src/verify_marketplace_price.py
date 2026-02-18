"""Проверка Marketplace цены у товара"""
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

# Проверяем товар 500944170 (первый из тестовых)
product_id = client.find_product_by_number("500944170")
if not product_id:
    # Если не найден, берем последний созданный
    import subprocess
    result = subprocess.run(["python", "check_recent_products.py"], capture_output=True, text=True, cwd=Path(__file__).parent)
    # Парсим первый ID из вывода
    for line in result.stdout.split("\n"):
        if "ID:" in line:
            product_id = line.split("ID:")[1].split(",")[0].strip()
            break
    if not product_id:
        product_id = "019b1a03c73b715186093a1af826cea7"  # Fallback
resp = client._request("GET", f"/api/product/{product_id}")
data = resp.get("data", {})
attrs = data.get("attributes", {})

print("=" * 80)
print("ПРОВЕРКА ТОВАРА")
print("=" * 80)
print(f"ID: {product_id}")
print(f"productNumber: {attrs.get('productNumber')}")
print(f"name: {attrs.get('name')}")

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
else:
    print("  НЕ НАЙДЕН")

print("\n" + "=" * 80)


"""Проверка товара сразу после обновления"""
import json
import time
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

# Получаем последний обновленный товар
resp_search = client._request(
    "POST",
    "/api/search/product",
    json={
        "limit": 1,
        "sort": [{"field": "updatedAt", "order": "DESC"}],
        "includes": {"product": ["id", "productNumber"]},
    },
)
products = resp_search.get("data", [])
if not products:
    print("Товары не найдены")
    exit(1)

product_id = products[0].get("id")
pn = products[0].get("productNumber")
print(f"Проверяем последний обновленный товар: ID={product_id}, productNumber={pn}")

print(f"Найден товар с ID: {product_id}")
print("Ожидание 3 секунды для применения изменений...")
time.sleep(3)

resp = client._request("GET", f"/api/product/{product_id}")
data = resp.get("data", {})
attrs = data.get("attributes", {})

print("\n" + "=" * 80)
print("ПРОВЕРКА ТОВАРА ПОСЛЕ ОБНОВЛЕНИЯ")
print("=" * 80)
print(f"productNumber: {attrs.get('productNumber')}")

print("\nBASE PRICE:")
base_price = attrs.get("price", [])
if base_price:
    print(f"  gross: {base_price[0].get('gross')}")
else:
    print("  НЕТ")

print("\nADVANCED PRICES:")
advanced_prices = attrs.get("prices", [])
if advanced_prices:
    print(f"  Всего записей: {len(advanced_prices)}")
    for idx, price_entry in enumerate(advanced_prices):
        print(f"\n  Запись {idx + 1}:")
        print(f"    ruleId: {price_entry.get('ruleId')}")
        print(f"    quantityStart: {price_entry.get('quantityStart')}")
        price_list = price_entry.get("price", [])
        if price_list:
            print(f"      gross: {price_list[0].get('gross')}")
else:
    print("  НЕТ")

# Проверяем Price Rule
marketplace_rule_id = client.find_price_rule_by_name("Marketplace Price")
print(f"\nPrice Rule 'Marketplace Price': {marketplace_rule_id}")

if advanced_prices and marketplace_rule_id:
    for price_entry in advanced_prices:
        if price_entry.get("ruleId") == marketplace_rule_id:
            print("\nРАБОТАЕТ: Marketplace цена найдена!")
            exit(0)

print("\nНЕ РАБОТАЕТ: Marketplace цена не найдена")
exit(1)


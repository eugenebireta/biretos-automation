"""Финальный тест Marketplace цены"""
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

print("=" * 80)
print("ФИНАЛЬНЫЙ ТЕСТ MARKETPLACE ЦЕНЫ")
print("=" * 80)
print()

# 1. Проверяем/создаем Price Rule
print("1. Проверка Price Rule 'Marketplace Price'...")
marketplace_rule_id = client.find_price_rule_by_name("Marketplace Price")
if not marketplace_rule_id:
    print("   Price Rule не найден, создаем...")
    marketplace_rule_id = client.create_price_rule(
        name="Marketplace Price",
        description="Price rule for Marketplace channel (from InSales price2)",
        priority=100
    )
    print(f"   Создан Price Rule: {marketplace_rule_id}")
else:
    print(f"   Найден Price Rule: {marketplace_rule_id}")

# 2. Запускаем импорт 1 товара
print("\n2. Запуск импорта 1 товара...")
import subprocess
result = subprocess.run(
    ["python", "full_import.py", "--source", "snapshot", "--limit", "1"],
    cwd=Path(__file__).parent,
    capture_output=True,
    text=True
)

if "Marketplace Rule ready" in result.stdout:
    print("   Price Rule создан/найден при импорте")
if "Marketplace цена добавлена" in result.stdout or "DEBUG UPDATE" in result.stdout:
    print("   Marketplace цена добавлена в payload")

# 3. Ждем и проверяем товар
print("\n3. Ожидание применения изменений (5 сек)...")
time.sleep(5)

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
    print("   Товары не найдены")
    exit(1)

product_id = products[0].get("id")
pn = products[0].get("productNumber")
print(f"   Проверяем товар: ID={product_id}, productNumber={pn}")

# Получаем полные данные
resp = client._request("GET", f"/api/product/{product_id}")
data = resp.get("data", {})
attrs = data.get("attributes", {})

base_price = attrs.get("price", [])
advanced_prices = attrs.get("prices", [])

print("\n4. Результаты проверки:")
print(f"   Base price: {'OK' if base_price else 'NO'}")
if base_price:
    print(f"     gross: {base_price[0].get('gross')}")

print(f"   Advanced prices: {'OK' if advanced_prices else 'NO'}")
if advanced_prices:
    print(f"     Всего записей: {len(advanced_prices)}")
    for idx, price_entry in enumerate(advanced_prices):
        rule_id = price_entry.get("ruleId")
        price_list = price_entry.get("price", [])
        if price_list:
            gross = price_list[0].get("gross")
            print(f"     Запись {idx + 1}: ruleId={rule_id}, gross={gross}")

# Проверяем Marketplace цену
has_marketplace = False
if advanced_prices and marketplace_rule_id:
    for price_entry in advanced_prices:
        if price_entry.get("ruleId") == marketplace_rule_id:
            has_marketplace = True
            marketplace_gross = price_entry.get("price", [{}])[0].get("gross")
            print(f"\n   Marketplace цена: OK (gross={marketplace_gross})")
            break

if not has_marketplace:
    print(f"\n   Marketplace цена: NO")

print("\n" + "=" * 80)
if base_price and has_marketplace:
    print("РАБОТАЕТ")
    print("Схема импорта готова для 5000 товаров.")
    exit(0)
else:
    print("НЕ РАБОТАЕТ")
    print("Требуется дополнительная диагностика.")
    exit(1)


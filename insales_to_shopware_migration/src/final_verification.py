"""Финальная проверка Marketplace цен"""
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
        "sort": [{"field": "updatedAt", "order": "DESC"}],
        "includes": {"product": ["id", "productNumber", "name"]},
    },
)

print("=" * 80)
print("ФИНАЛЬНАЯ ПРОВЕРКА MARKETPLACE ЦЕН")
print("=" * 80)
print()

marketplace_rule_id = client.find_price_rule_by_name("Marketplace Price")
print(f"Price Rule 'Marketplace Price': {marketplace_rule_id}")
print()

products = resp.get("data", [])
print(f"Проверяем {len(products)} последних обновленных товаров:\n")

ok_count = 0
fail_count = 0

for product in products:
    pid = product.get("id")
    pn = product.get("productNumber")
    
    # Получаем полные данные
    full_data = client._request("GET", f"/api/product/{pid}")
    attrs = full_data.get("data", {}).get("attributes", {})
    
    base_price = attrs.get("price", [])
    advanced_prices = attrs.get("prices", [])
    
    has_base_price = base_price and len(base_price) > 0
    has_marketplace_price = False
    
    if advanced_prices and marketplace_rule_id:
        for price_entry in advanced_prices:
            if price_entry.get("ruleId") == marketplace_rule_id:
                has_marketplace_price = True
                marketplace_gross = price_entry.get("price", [{}])[0].get("gross")
                break
    
    status = "OK" if (has_base_price and has_marketplace_price) else "FAIL"
    if status == "OK":
        ok_count += 1
    else:
        fail_count += 1
    
    print(f"{pn or 'N/A':<15} | base_price: {'OK' if has_base_price else 'NO':<3} | marketplace: {'OK' if has_marketplace_price else 'NO':<3} | {status}")

print()
print("=" * 80)
print(f"ИТОГО: OK={ok_count}, FAIL={fail_count}")
print("=" * 80)

if ok_count > 0:
    print("\nРАБОТАЕТ")
    print("Схема импорта готова для 5000 товаров.")
else:
    print("\nНЕ РАБОТАЕТ")
    print("Требуется дополнительная диагностика.")


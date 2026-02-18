"""
Финальная проверка Marketplace цен после импорта
"""
import json
from pathlib import Path
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

# Тестовые SKU
TEST_SKUS = ["500944170", "500944171", "500944177", "500944178", "500944203", 
             "500944207", "500944219", "500944220", "500944221", "500944222"]

with CONFIG_PATH.open() as f:
    config = json.load(f)

client = ShopwareClient(
    ShopwareConfig(
        config["shopware"]["url"],
        config["shopware"]["access_key_id"],
        config["shopware"]["secret_access_key"]
    )
)

# Получаем Price Rule ID
marketplace_rule_id = client.find_price_rule_by_name("Marketplace Price")
print(f"Marketplace Price Rule ID: {marketplace_rule_id}\n")

# Получаем последние 20 товаров
resp = client._request(
    "POST",
    "/api/search/product",
    json={
        "limit": 20,
        "sort": [{"field": "createdAt", "order": "DESC"}],
        "includes": {"product": ["id", "productNumber", "name"]},
    },
)

print("=" * 80)
print("ПРОВЕРКА ПОСЛЕДНИХ СОЗДАННЫХ ТОВАРОВ")
print("=" * 80)
print()

found_count = 0
marketplace_count = 0

for p in resp.get("data", [])[:20]:
    pid = p.get("id")
    # Получаем полные данные
    full_data = client._request("GET", f"/api/product/{pid}")
    attrs = full_data.get("data", {}).get("attributes", {})
    pn = attrs.get("productNumber")
    name = attrs.get("name", "")[:50]
    
    # Проверяем, является ли это тестовым товаром
    if pn and pn in TEST_SKUS:
        found_count += 1
        base_price = attrs.get("price", [])
        base_price_val = base_price[0].get("gross") if base_price and len(base_price) > 0 else None
        
        # Проверяем Marketplace цену
        advanced_prices = attrs.get("prices", [])
        marketplace_price_val = None
        has_marketplace = False
        
        if advanced_prices:
            for price_entry in advanced_prices:
                rule_id = price_entry.get("ruleId")
                if rule_id == marketplace_rule_id:
                    price_list = price_entry.get("price", [])
                    if price_list and len(price_list) > 0:
                        marketplace_price_val = price_list[0].get("gross")
                        has_marketplace = True
                        marketplace_count += 1
                        break
        
        status = "OK" if (base_price_val and has_marketplace) else "FAIL"
        print(f"{status}: SKU={pn}, base_price={base_price_val}, marketplace_price={marketplace_price_val}, has_rule={has_marketplace}")

print()
print("=" * 80)
print(f"Найдено тестовых товаров: {found_count}/10")
print(f"С Marketplace ценой: {marketplace_count}/{found_count}")
print("=" * 80)




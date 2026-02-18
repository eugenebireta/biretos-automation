"""
Проверка конкретных товаров по SKU
"""
import json
from pathlib import Path
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

TEST_SKUS = ["500944170", "500944171"]

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

for sku in TEST_SKUS:
    print(f"Проверка товара {sku}...")
    product_id = client.find_product_by_number(sku)
    if not product_id:
        print(f"  Товар не найден")
        continue
    
    # Получаем полные данные
    full_data = client._request("GET", f"/api/product/{product_id}")
    attrs = full_data.get("data", {}).get("attributes", {})
    
    base_price = attrs.get("price", [])
    base_price_val = base_price[0].get("gross") if base_price and len(base_price) > 0 else None
    
    # Проверяем Marketplace цену
    advanced_prices = attrs.get("prices", [])
    marketplace_price_val = None
    has_marketplace = False
    
    print(f"  Base price: {base_price_val}")
    print(f"  Advanced prices count: {len(advanced_prices)}")
    
    if advanced_prices:
        for price_entry in advanced_prices:
            rule_id = price_entry.get("ruleId")
            print(f"    Price entry ruleId: {rule_id}, expected: {marketplace_rule_id}")
            if rule_id == marketplace_rule_id:
                price_list = price_entry.get("price", [])
                if price_list and len(price_list) > 0:
                    marketplace_price_val = price_list[0].get("gross")
                    has_marketplace = True
                    break
    
    print(f"  Marketplace price: {marketplace_price_val}")
    print(f"  Has marketplace: {has_marketplace}")
    print()




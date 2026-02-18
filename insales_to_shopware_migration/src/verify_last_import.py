"""
Проверка последнего импорта - получаем товары напрямую через Search API
"""
import json
from pathlib import Path
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

TEST_SKUS = ["500944170", "500944171", "500944177"]

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

print("=" * 80)
print("ПРОВЕРКА ТОВАРОВ ПО SKU")
print("=" * 80)
print()

all_ok = True

for sku in TEST_SKUS:
    print(f"Проверка товара {sku}...")
    
    # Ищем товар через Search API
    try:
        search_response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [{"field": "productNumber", "type": "equals", "value": sku}],
                "limit": 1,
                "includes": {"product": ["id", "productNumber"]},
            },
        )
        
        if search_response.get("total") and search_response.get("data"):
            product = search_response["data"][0]
            product_id = product.get("id")
            found_pn = product.get("productNumber")
            
            if found_pn == sku and product_id:
                print(f"  Найден товар: ID={product_id}, productNumber={found_pn}")
                
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
                        if rule_id == marketplace_rule_id:
                            price_list = price_entry.get("price", [])
                            if price_list and len(price_list) > 0:
                                marketplace_price_val = price_list[0].get("gross")
                                has_marketplace = True
                                break
                
                print(f"  Marketplace price: {marketplace_price_val}")
                print(f"  Has marketplace: {has_marketplace}")
                
                if base_price_val and has_marketplace:
                    print(f"  STATUS: OK")
                else:
                    print(f"  STATUS: FAIL (base_price={base_price_val is not None}, marketplace={has_marketplace})")
                    all_ok = False
            else:
                print(f"  STATUS: FAIL - productNumber не совпадает (found: {found_pn}, expected: {sku})")
                all_ok = False
        else:
            print(f"  STATUS: FAIL - товар не найден через Search API")
            all_ok = False
    except Exception as e:
        print(f"  STATUS: ERROR - {e}")
        all_ok = False
    
    print()

print("=" * 80)
if all_ok:
    print("РАБОТАЕТ - Все проверки пройдены успешно")
else:
    print("НЕ РАБОТАЕТ - Обнаружены проблемы")
print("=" * 80)




"""
Проверка валюты существующих товаров
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json

ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
config = load_json(ROOT / "config.json")

shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

print("=" * 60)
print("ПРОВЕРКА ВАЛЮТЫ СУЩЕСТВУЮЩИХ ТОВАРОВ")
print("=" * 60)

# Проверяем валюту RUB
rub_currency_id = "b7d2554b0ce847cd82f3ac9bd1c0dfca"
print(f"\nВалюта RUB ID: {rub_currency_id}")

# Проверяем несколько товаров
test_numbers = ["498271735", "498271898", "498271938", "498272057", "498272105"]

print(f"\nПроверка товаров:")
print("-" * 60)

for product_number in test_numbers:
    try:
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [{"field": "productNumber", "type": "equals", "value": product_number}],
                "includes": {"product": ["id", "productNumber", "name", "price"]},
                "limit": 1,
            },
        )
        
        if response.get("total") and response.get("data"):
            product = response["data"][0]
            product_id = product.get("id")
            
            # Получаем детали
            detail = client._request("GET", f"/api/product/{product_id}")
            detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
            attrs = detail_data.get("attributes", {})
            
            prices = attrs.get("price", [])
            if prices:
                price_entry = prices[0] if isinstance(prices, list) else prices
                if isinstance(price_entry, dict):
                    currency_id = price_entry.get("currencyId")
                    gross = price_entry.get("gross")
                    
                    # Проверяем валюту
                    if currency_id:
                        curr = client._request("GET", f"/api/currency/{currency_id}")
                        curr_data = curr.get("data", {}) if isinstance(curr, dict) else {}
                        curr_attrs = curr_data.get("attributes", {})
                        iso_code = curr_attrs.get("isoCode", "N/A")
                        
                        print(f"\n{product_number}:")
                        print(f"  Цена: {gross} {iso_code}")
                        print(f"  Currency ID: {currency_id}")
                        
                        if currency_id == rub_currency_id:
                            print(f"  OK: Использует RUB")
                        else:
                            print(f"  PROBLEM: Использует {iso_code} (ID: {currency_id}) вместо RUB")
                            print(f"  Нужно обновить на RUB (ID: {rub_currency_id})")
        else:
            print(f"{product_number}: не найден")
    except Exception as e:
        print(f"{product_number}: ошибка - {e}")

print("\n" + "=" * 60)









"""
Тест создания нового товара для проверки валюты RUB
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json
import json

ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
config = load_json(ROOT / "config.json")

shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

print("=" * 60)
print("ТЕСТ СОЗДАНИЯ НОВОГО ТОВАРА С ВАЛЮТОЙ RUB")
print("=" * 60)

# Получаем валюту RUB
rub_currency_id = client.get_sales_channel_currency_id()
print(f"\nВалюта RUB ID: {rub_currency_id}")

# Получаем tax ID
tax_id = client.get_default_tax_id()
print(f"Tax ID: {tax_id}")

# Создаём тестовый товар
test_product = {
    "productNumber": f"TEST-{int(__import__('time').time())}",
    "name": "Тестовый товар для проверки RUB",
    "description": "Это тестовый товар для проверки, что цены сохраняются в RUB",
    "stock": 10,
    "active": True,
    "taxId": tax_id,
    "price": [
        {
            "currencyId": rub_currency_id,
            "gross": 1000.0,
            "net": 1000.0,
            "linked": False,
        }
    ],
}

print(f"\nСоздаю товар: {test_product['productNumber']}")
print(f"Цена: {test_product['price'][0]['gross']} RUB")

try:
    response = client._request("POST", "/api/product", json=test_product)
    product_id = response.get("data", {}).get("id") if isinstance(response, dict) else None
    
    if product_id:
        print(f"✓ Товар создан! ID: {product_id}")
        
        # Проверяем созданный товар
        print(f"\nПроверяю созданный товар...")
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
                    
                    print(f"\nРезультат:")
                    print(f"  Цена: {gross} {iso_code}")
                    print(f"  Currency ID: {currency_id}")
                    
                    if currency_id == rub_currency_id and iso_code.upper() == "RUB":
                        print(f"  ✓✓✓ УСПЕХ! Цена сохранена в RUB!")
                    else:
                        print(f"  ✗ ПРОБЛЕМА: Цена в {iso_code} вместо RUB")
        
        print(f"\nТовар можно удалить через админ-панель или API:")
        print(f"  DELETE /api/product/{product_id}")
    else:
        print("✗ Ошибка: товар не создан")
        print(f"Response: {json.dumps(response, indent=2, ensure_ascii=False)}")
        
except Exception as e:
    print(f"✗ Ошибка создания товара: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)









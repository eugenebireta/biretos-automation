"""
Прямая проверка товаров в Shopware через GET запрос
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
print("ПРЯМАЯ ПРОВЕРКА ТОВАРОВ В SHOPWARE")
print("=" * 60)

# Проверяем общее количество товаров
print("\n1. Общее количество товаров:")
print("-" * 60)
try:
    response = client._request("GET", "/api/product", params={"limit": 1})
    total = response.get("total", 0) if isinstance(response, dict) else 0
    print(f"Всего товаров в Shopware: {total}")
except Exception as e:
    print(f"Ошибка: {e}")

# Получаем список товаров
print("\n2. Список товаров (первые 15):")
print("-" * 60)
try:
    response = client._request("GET", "/api/product", params={"limit": 15})
    products = response.get("data", []) if isinstance(response, dict) else []
    print(f"Найдено товаров: {len(products)}")
    
    for idx, product in enumerate(products, 1):
        product_id = product.get("id")
        try:
            detail = client._request("GET", f"/api/product/{product_id}")
            detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
            attrs = detail_data.get("attributes", {})
            
            product_number = attrs.get("productNumber", "N/A")
            name = attrs.get("name", "N/A")
            stock = attrs.get("stock", "N/A")
            active = attrs.get("active", "N/A")
            
            # Проверяем цену
            prices = attrs.get("price", [])
            price_info = "N/A"
            if prices:
                price_entry = prices[0] if isinstance(prices, list) else prices
                if isinstance(price_entry, dict):
                    gross = price_entry.get("gross")
                    currency_id = price_entry.get("currencyId")
                    if currency_id:
                        try:
                            curr = client._request("GET", f"/api/currency/{currency_id}")
                            curr_data = curr.get("data", {}) if isinstance(curr, dict) else {}
                            curr_attrs = curr_data.get("attributes", {})
                            iso_code = curr_attrs.get("isoCode", "N/A")
                            price_info = f"{gross} {iso_code}"
                        except:
                            price_info = f"{gross} (currency ID: {currency_id})"
            
            print(f"\n{idx}. {product_number}")
            print(f"   Название: {name[:60]}...")
            print(f"   Остаток: {stock}, Активен: {active}")
            print(f"   Цена: {price_info}")
        except Exception as e:
            print(f"{idx}. Ошибка получения деталей товара {product_id}: {e}")
except Exception as e:
    print(f"Ошибка получения списка товаров: {e}")
    import traceback
    traceback.print_exc()

# Проверяем конкретные товары из импорта
print("\n3. Проверка конкретных товаров из импорта:")
print("-" * 60)
test_numbers = ["498272057", "498272105", "498272156", "498272205", "498272207", "498272211"]

for product_number in test_numbers:
    try:
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [{"field": "productNumber", "type": "equals", "value": product_number}],
                "includes": {"product": ["id", "productNumber", "name"]},
                "limit": 1,
            },
        )
        
        if response.get("total") and response.get("data"):
            product = response["data"][0]
            print(f"✓ {product_number}: найден (ID: {product.get('id')})")
        else:
            print(f"✗ {product_number}: не найден")
    except Exception as e:
        print(f"✗ {product_number}: ошибка поиска - {e}")









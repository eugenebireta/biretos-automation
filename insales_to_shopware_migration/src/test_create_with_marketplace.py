"""Тест создания нового товара с Marketplace ценой"""
import json
import time
from pathlib import Path
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
SNAPSHOT_PATH = ROOT / "insales_snapshot" / "products.ndjson"

with CONFIG_PATH.open() as f:
    config = json.load(f)

client = ShopwareClient(
    ShopwareConfig(
        config["shopware"]["url"],
        config["shopware"]["access_key_id"],
        config["shopware"]["secret_access_key"]
    )
)

# 1. Создаем/находим Price Rule
print("1. Создание Price Rule...")
marketplace_rule_id = client.find_price_rule_by_name("Marketplace Price")
if not marketplace_rule_id:
    marketplace_rule_id = client.create_price_rule(
        name="Marketplace Price",
        description="Price rule for Marketplace channel",
        priority=100
    )
print(f"   Price Rule ID: {marketplace_rule_id}")

# 2. Загружаем тестовый товар из snapshot (берем первый с price2)
print("\n2. Загрузка тестового товара...")
test_sku = "TEST_MARKETPLACE_001"  # Используем тестовый SKU для нового товара
with SNAPSHOT_PATH.open("r", encoding="utf-8") as f:
    for line in f:
        try:
            product = json.loads(line)
            variants = product.get("variants", [])
            if variants:
                variant = variants[0]
                price2 = variant.get("price2")
                if price2 and float(price2) > 0:
                    price = float(variant.get("price", 0))
                    price2 = float(price2)
                    product_name = product.get("title", "Test Product")
                    
                    print(f"   SKU: {test_sku} (тестовый)")
                    print(f"   price: {price}")
                    print(f"   price2: {price2}")
                    break
        except:
            continue

# 3. Удаляем товар, если существует
print("\n3. Удаление существующего товара...")
existing_id = client.find_product_by_number(test_sku)
if existing_id:
    try:
        client._request("DELETE", f"/api/product/{existing_id}")
        print(f"   Товар удален: {existing_id}")
        time.sleep(2)
        # Проверяем, что товар действительно удален
        check_id = client.find_product_by_number(test_sku)
        if check_id:
            print(f"   WARNING: Товар все еще существует после удаления, пробуем еще раз...")
            client._request("DELETE", f"/api/product/{check_id}")
            time.sleep(2)
    except Exception as e:
        print(f"   Ошибка удаления: {e}")
else:
    print("   Товар не найден, можно создавать новый")

# 4. Создаем новый товар с Marketplace ценой
print("\n4. Создание нового товара с Marketplace ценой...")
sales_channel_currency = client.get_sales_channel_currency_id()
payload = {
    "productNumber": test_sku,
    "name": product_name,
    "active": True,
    "taxId": client.get_default_tax_id(),
    "price": [{
        "currencyId": sales_channel_currency,
        "gross": price,
        "net": price / 1.19,
        "linked": True
    }],
    "prices": [{
        "ruleId": marketplace_rule_id,
        "quantityStart": 1,
        "price": [{
            "currencyId": sales_channel_currency,
            "gross": price2,
            "net": price2,
            "linked": False
        }]
    }],
    "stock": 0
}

print(f"   Payload prices: {payload.get('prices')}")

try:
    response = client._request("POST", "/api/product", json=payload)
    product_id = None
    
    # Пробуем разные форматы ответа Shopware
    if isinstance(response, dict):
        # Формат JSON:API
        if "data" in response:
            data = response["data"]
            if isinstance(data, dict):
                product_id = data.get("id")
            elif isinstance(data, list) and len(data) > 0:
                product_id = data[0].get("id")
        # Прямой формат
        elif "id" in response:
            product_id = response["id"]
    elif isinstance(response, list) and len(response) > 0:
        product_id = response[0].get("id")
    
    if product_id:
        print(f"   Товар создан: {product_id}")
    else:
        print(f"   WARNING: не удалось получить product_id из ответа")
        print(f"   Response type: {type(response)}")
        print(f"   Response keys: {response.keys() if isinstance(response, dict) else 'N/A'}")
        # Пробуем найти товар по SKU
        product_id = client.find_product_by_number(test_sku)
        if product_id:
            print(f"   Товар найден по SKU: {product_id}")
        else:
            print(f"   Ошибка: товар не создан и не найден")
            exit(1)
except Exception as e:
    print(f"   Ошибка создания товара: {e}")
    # Пробуем найти товар по SKU на случай, если он все-таки создался
    product_id = client.find_product_by_number(test_sku)
    if product_id:
        print(f"   Товар найден по SKU после ошибки: {product_id}")
    else:
        exit(1)

# 5. Проверяем товар
print("\n5. Ожидание применения изменений (3 сек)...")
time.sleep(3)

resp = client._request("GET", f"/api/product/{product_id}")
data = resp.get("data", {})
attrs = data.get("attributes", {})

print(f"\n6. Результаты проверки:")
print(f"   productNumber: {attrs.get('productNumber')}")
print(f"   Base price: {attrs.get('price', [{}])[0].get('gross') if attrs.get('price') else 'N/A'}")
print(f"   Advanced prices: {len(attrs.get('prices', []))} записей")

advanced_prices = attrs.get("prices", [])
has_marketplace = False
if advanced_prices:
    for price_entry in advanced_prices:
        if price_entry.get("ruleId") == marketplace_rule_id:
            has_marketplace = True
            marketplace_gross = price_entry.get("price", [{}])[0].get("gross")
            print(f"   Marketplace цена: OK (gross={marketplace_gross})")
            break

if not has_marketplace:
    print(f"   Marketplace цена: NO")

print("\n" + "=" * 80)
if has_marketplace:
    print("РАБОТАЕТ: Marketplace цена установлена при создании товара")
    exit(0)
else:
    print("НЕ РАБОТАЕТ: Marketplace цена не установлена")
    exit(1)


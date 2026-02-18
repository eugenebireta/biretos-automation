"""
Проверка тестового импорта товаров в Shopware
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json
import json
import csv

ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
config = load_json(ROOT / "config.json")

shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

print("=" * 60)
print("ПРОВЕРКА ТЕСТОВОГО ИМПОРТА")
print("=" * 60)

# Читаем результаты импорта
result_path = ROOT.parent / "_scratchpad" / "full_import_result.json"
if not result_path.exists():
    print("❌ Файл результатов не найден. Запустите импорт сначала.")
    sys.exit(1)

result = load_json(result_path)
print(f"\n📊 Статистика импорта:")
print(f"  Всего обработано: {result.get('total', 0)}")
print(f"  Создано: {result.get('created', 0)}")
print(f"  Обновлено: {result.get('updated', 0)}")
print(f"  Пропущено: {result.get('skipped', 0)}")
print(f"  Ошибок: {result.get('errors_count', 0)}")

# Читаем CSV для проверки
csv_path = ROOT / "output" / "products_import.csv"
if not csv_path.exists():
    print("❌ CSV файл не найден.")
    sys.exit(1)

print(f"\n📋 Проверка товаров из CSV (первые 10):")
print("-" * 60)

csv_products = []
with csv_path.open("r", encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    for idx, row in enumerate(reader):
        if idx >= 10:
            break
        csv_products.append({
            "productNumber": row.get("productNumber"),
            "name": row.get("name"),
            "price": row.get("price"),
            "stock": row.get("stock"),
        })

print(f"Загружено {len(csv_products)} товаров из CSV для проверки\n")

# Проверяем каждый товар в Shopware
checked = 0
errors = []

for csv_product in csv_products:
    product_number = csv_product["productNumber"]
    print(f"Проверка товара: {product_number}")
    
    try:
        # Ищем товар в Shopware
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [{"field": "productNumber", "type": "equals", "value": product_number}],
                "includes": {
                    "product": [
                        "id",
                        "productNumber",
                        "name",
                        "stock",
                        "active",
                        "price",
                        "taxId",
                    ]
                },
                "limit": 1,
            },
        )
        
        if response.get("total") and response.get("data"):
            product = response["data"][0]
            product_id = product.get("id")
            
            # Получаем детали товара
            detail_response = client._request("GET", f"/api/product/{product_id}")
            detail_data = detail_response.get("data", {}) if isinstance(detail_response, dict) else {}
            detail_attrs = detail_data.get("attributes", {})
            
            print(f"  ✓ Найден в Shopware")
            print(f"    ID: {product_id}")
            print(f"    Название: {detail_attrs.get('name', 'N/A')[:50]}...")
            print(f"    Артикул: {detail_attrs.get('productNumber', 'N/A')}")
            print(f"    Остаток: {detail_attrs.get('stock', 'N/A')}")
            print(f"    Активен: {detail_attrs.get('active', 'N/A')}")
            
            # Проверяем цену
            prices = detail_attrs.get("price", [])
            if prices:
                price_entry = prices[0] if isinstance(prices, list) else prices
                gross = price_entry.get("gross") if isinstance(price_entry, dict) else None
                currency_id = price_entry.get("currencyId") if isinstance(price_entry, dict) else None
                
                # Проверяем валюту
                if currency_id:
                    curr_detail = client._request("GET", f"/api/currency/{currency_id}")
                    curr_data = curr_detail.get("data", {}) if isinstance(curr_detail, dict) else {}
                    curr_attrs = curr_data.get("attributes", {})
                    iso_code = curr_attrs.get("isoCode")
                    
                    print(f"    Цена: {gross} {iso_code}")
                    
                    if iso_code and iso_code.upper() == "RUB":
                        print(f"    ✓ Валюта правильная (RUB)")
                    else:
                        print(f"    ⚠ Валюта: {iso_code} (ожидалось RUB)")
                        errors.append(f"Товар {product_number}: неверная валюта {iso_code}")
                else:
                    print(f"    ⚠ Цена без валюты")
                    errors.append(f"Товар {product_number}: цена без валюты")
            else:
                print(f"    ⚠ Цена не найдена")
                errors.append(f"Товар {product_number}: цена не найдена")
            
            checked += 1
        else:
            print(f"  ❌ НЕ найден в Shopware")
            errors.append(f"Товар {product_number}: не найден в Shopware")
    
    except Exception as e:
        print(f"  ❌ Ошибка проверки: {e}")
        errors.append(f"Товар {product_number}: ошибка проверки - {e}")
    
    print()

print("=" * 60)
print("РЕЗУЛЬТАТЫ ПРОВЕРКИ")
print("=" * 60)
print(f"Проверено товаров: {checked}/{len(csv_products)}")
print(f"Ошибок: {len(errors)}")

if errors:
    print(f"\n⚠ Найдены проблемы:")
    for error in errors:
        print(f"  - {error}")
else:
    print(f"\n✓ Все товары проверены успешно!")

# Проверяем общее количество товаров в Shopware
print(f"\n📊 Общая статистика Shopware:")
try:
    response = client._request(
        "POST",
        "/api/search/product",
        json={
            "limit": 1,
            "total-count-mode": 1,  # Exact count
        },
    )
    total_products = response.get("total", 0)
    print(f"  Всего товаров в Shopware: {total_products}")
except Exception as e:
    print(f"  ⚠ Не удалось получить общее количество: {e}")









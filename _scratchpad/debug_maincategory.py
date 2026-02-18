"""Отладка mainCategoryId"""
import sys
from pathlib import Path
import csv

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

# Проверяем товар 498271735
product_number = "498271735"

print("=" * 60)
print("ОТЛАДКА mainCategoryId")
print("=" * 60)

# 1. Проверяем CSV
print(f"\n1. Проверка CSV для товара {product_number}...")
csv_path = ROOT / "output" / "products_import.csv"
with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row.get("productNumber") == product_number:
            print(f"   categoryIds: {row.get('categoryIds', 'N/A')}")
            print(f"   mainCategoryId: {row.get('mainCategoryId', 'N/A')}")
            csv_main = row.get('mainCategoryId')
            break
    else:
        print(f"   ❌ Товар не найден в CSV!")
        sys.exit(1)

# 2. Проверяем текущее состояние в Shopware
print(f"\n2. Текущее состояние в Shopware...")
response = client._request("GET", "/api/product", params={"filter[productNumber]": product_number})
products = response.get("data", []) if isinstance(response, dict) else []
if not products:
    print(f"   ❌ Товар не найден в Shopware!")
    sys.exit(1)

product_id = products[0].get("id")
detail = client._request("GET", f"/api/product/{product_id}")
detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
attrs = detail_data.get("attributes", {})

print(f"   Текущий mainCategoryId: {attrs.get('mainCategoryId', 'НЕТ')}")

# 3. Пробуем обновить только mainCategoryId
print(f"\n3. Попытка обновления mainCategoryId...")
if csv_main:
    update_payload = {
        "id": product_id,
        "mainCategoryId": csv_main
    }
    print(f"   Payload: {update_payload}")
    try:
        client._request("PATCH", f"/api/product/{product_id}", json=update_payload)
        print(f"   ✅ Обновление отправлено")
        
        # Проверяем результат
        detail2 = client._request("GET", f"/api/product/{product_id}")
        detail_data2 = detail2.get("data", {}) if isinstance(detail2, dict) else {}
        attrs2 = detail_data2.get("attributes", {})
        print(f"   Новый mainCategoryId: {attrs2.get('mainCategoryId', 'НЕТ')}")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
else:
    print(f"   ❌ mainCategoryId отсутствует в CSV!")

print("=" * 60)









"""Отладка mainCategoryId - проверка категории"""
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

product_number = "498271735"
main_category_id = "67c46b54a5944429ab54e64707dd6418"

print("=" * 60)
print("ОТЛАДКА mainCategoryId - ПРОВЕРКА КАТЕГОРИИ")
print("=" * 60)

# 1. Проверяем, существует ли категория
print(f"\n1. Проверка существования категории {main_category_id}...")
try:
    cat_detail = client._request("GET", f"/api/category/{main_category_id}")
    cat_data = cat_detail.get("data", {}) if isinstance(cat_detail, dict) else {}
    cat_attrs = cat_data.get("attributes", {})
    cat_name = cat_attrs.get("name", "N/A")
    print(f"   ✅ Категория существует: {cat_name}")
except Exception as e:
    print(f"   ❌ Категория не найдена: {e}")
    sys.exit(1)

# 2. Получаем товар с категориями
print(f"\n2. Получение товара {product_number}...")
response = client._request("GET", "/api/product", params={"filter[productNumber]": product_number})
products = response.get("data", []) if isinstance(response, dict) else []
if not products:
    print(f"   ❌ Товар не найден!")
    sys.exit(1)

product_id = products[0].get("id")
detail = client._request("GET", f"/api/product/{product_id}", params={
    "associations[categories][]": "categories"
})
detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
attrs = detail_data.get("attributes", {})

# 3. Проверяем, есть ли mainCategoryId в списке категорий
relationships = detail_data.get("relationships", {})
categories_rel = relationships.get("categories", {})
categories_data = categories_rel.get("data", []) if isinstance(categories_rel, dict) else []
category_ids = [cat.get("id") for cat in categories_data]

print(f"   Категории товара: {len(category_ids)}")
print(f"   mainCategoryId в списке: {'✅ ДА' if main_category_id in category_ids else '❌ НЕТ'}")

# 4. Пробуем обновить с категориями и mainCategoryId вместе
print(f"\n3. Попытка обновления с категориями и mainCategoryId...")
if main_category_id in category_ids:
    # Убеждаемся, что mainCategoryId точно в списке
    update_payload = {
        "id": product_id,
        "categories": [{"id": cid} for cid in category_ids],
        "mainCategoryId": main_category_id
    }
    print(f"   Payload: categories={len(update_payload['categories'])}, mainCategoryId={main_category_id}")
    try:
        client._request("PATCH", f"/api/product/{product_id}", json=update_payload)
        print(f"   ✅ Обновление отправлено")
        
        # Проверяем результат
        detail2 = client._request("GET", f"/api/product/{product_id}")
        detail_data2 = detail2.get("data", {}) if isinstance(detail2, dict) else {}
        attrs2 = detail_data2.get("attributes", {})
        new_main = attrs2.get("mainCategoryId")
        print(f"   Новый mainCategoryId: {new_main if new_main else '❌ НЕТ'}")
        
        if new_main == main_category_id:
            print(f"   ✅ mainCategoryId успешно установлен!")
        else:
            print(f"   ❌ mainCategoryId не установлен (ожидалось: {main_category_id})")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
else:
    print(f"   ❌ mainCategoryId не в списке категорий, добавляем...")
    # Добавляем mainCategoryId в список категорий
    all_category_ids = category_ids + [main_category_id]
    update_payload = {
        "id": product_id,
        "categories": [{"id": cid} for cid in all_category_ids],
        "mainCategoryId": main_category_id
    }
    print(f"   Payload: categories={len(update_payload['categories'])}, mainCategoryId={main_category_id}")
    try:
        client._request("PATCH", f"/api/product/{product_id}", json=update_payload)
        print(f"   ✅ Обновление отправлено")
        
        # Проверяем результат
        detail2 = client._request("GET", f"/api/product/{product_id}")
        detail_data2 = detail2.get("data", {}) if isinstance(detail2, dict) else {}
        attrs2 = detail_data2.get("attributes", {})
        new_main = attrs2.get("mainCategoryId")
        print(f"   Новый mainCategoryId: {new_main if new_main else '❌ НЕТ'}")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")

print("=" * 60)









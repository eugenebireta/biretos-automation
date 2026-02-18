"""Проверка обновления категорий и mainCategoryId"""
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
print("ПРОВЕРКА ОБНОВЛЕНИЯ КАТЕГОРИЙ")
print("=" * 60)

# Получаем несколько товаров
print("\n1. Получение товаров из Shopware...")
response = client._request("GET", "/api/product", params={"limit": 5})
products = response.get("data", []) if isinstance(response, dict) else []

if not products:
    print("  ❌ Товары не найдены!")
    sys.exit(1)

print(f"  Найдено товаров: {len(products)}")

# Проверяем первый товар с категориями
for product in products:
    product_id = product.get("id")
    
    # Получаем детали товара
    detail = client._request("GET", f"/api/product/{product_id}", params={
        "associations[categories][]": "categories"
    })
    detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
    attrs = detail_data.get("attributes", {})
    
    product_number = attrs.get("productNumber", "N/A")
    name = attrs.get("name", "N/A")
    
    # Проверяем mainCategoryId
    main_category_id = attrs.get("mainCategoryId")
    
    # Проверяем категории
    relationships = detail_data.get("relationships", {})
    categories_rel = relationships.get("categories", {})
    categories_data = categories_rel.get("data", []) if isinstance(categories_rel, dict) else []
    
    print(f"\n2. Товар: {product_number}")
    print(f"   Название: {name[:60]}...")
    print(f"   mainCategoryId: {main_category_id if main_category_id else '❌ НЕ УСТАНОВЛЕН'}")
    print(f"   Количество категорий: {len(categories_data)}")
    
    if categories_data:
        print(f"   Категории (ID):")
        for idx, cat in enumerate(categories_data[:10], 1):  # Показываем первые 10
            cat_id = cat.get("id", "N/A")
            is_main = "⭐ MAIN" if cat_id == main_category_id else ""
            print(f"     {idx}. {cat_id} {is_main}")
    
    # Если есть mainCategoryId, проверяем, что он в списке категорий
    if main_category_id:
        category_ids = [cat.get("id") for cat in categories_data]
        if main_category_id in category_ids:
            print(f"   ✅ mainCategoryId присутствует в списке категорий")
        else:
            print(f"   ❌ mainCategoryId НЕ присутствует в списке категорий!")
    
    # Получаем детали категорий для построения пути
    if categories_data:
        print(f"\n3. Детали категорий:")
        for cat in categories_data[:5]:  # Показываем первые 5
            cat_id = cat.get("id")
            try:
                cat_detail = client._request("GET", f"/api/category/{cat_id}")
                cat_data = cat_detail.get("data", {}) if isinstance(cat_detail, dict) else {}
                cat_attrs = cat_data.get("attributes", {})
                cat_name = cat_attrs.get("name", "N/A")
                cat_level = cat_attrs.get("level", 0)
                print(f"   - {cat_name} (ID: {cat_id[:16]}..., level: {cat_level})")
            except Exception as e:
                print(f"   - ID: {cat_id[:16]}... (ошибка получения: {str(e)[:50]})")
    
    # Проверяем только первый товар
    break

print("\n" + "=" * 60)
print("ПРОВЕРКА ЗАВЕРШЕНА")
print("=" * 60)









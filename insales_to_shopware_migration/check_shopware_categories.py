"""
Проверяет, какие категории Авиазапчасти есть в Shopware
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from clients import ShopwareClient, ShopwareConfig
from category_utils import find_category_by_path, is_leaf_category

# Загружаем конфигурацию
config = json.load(open(Path(__file__).parent / "config.json", encoding="utf-8"))
shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

# Проверяем различные пути
test_paths = [
    "Каталог > Авиазапчасти",
    "Каталог > Авиазапчасти > Авиазапчасти boeing 737",
    "Каталог > Авиазапчасти > Авиазапчасти boeing 737 > реле",
    "Каталог > Электрика",
    "Каталог > Электрика > Электроустановочные изделия",
    "Каталог > Электрика > Электроустановочные изделия > выключатели",
    "Каталог > Электрика > Электроустановочные изделия > выключатели > Выключатель-разъединитель нагрузки",
]

root_category_id = config.get("shopware", {}).get("root_category_id")

# Проверяем категорию по UUID из migration_map.json
print("Проверка категории по UUID из migration_map.json...")
migration_map = json.load(open(Path(__file__).parent / "migration_map.json", encoding="utf-8"))
aviacat_uuid = migration_map.get("categories", {}).get("20769913")  # Авиазапчасти
if aviacat_uuid:
    try:
        response = client._request("GET", f"/api/category/{aviacat_uuid}")
        if response:
            print(f"✓ Категория найдена по UUID: {aviacat_uuid}")
            print(f"  Данные: {json.dumps(response, ensure_ascii=False, indent=2)[:200]}...")
            is_leaf = is_leaf_category(client, aviacat_uuid)
            print(f"  Leaf: {is_leaf}")
        else:
            print(f"✗ Категория не найдена по UUID: {aviacat_uuid}")
    except Exception as e:
        print(f"Ошибка при проверке категории: {e}")

print("\n" + "=" * 60)
print("Проверка категорий в Shopware:")
print("=" * 60)
for path in test_paths:
    cat_id = find_category_by_path(client, path, root_category_id)
    if cat_id:
        is_leaf = is_leaf_category(client, cat_id)
        print(f"✓ {path}")
        print(f"  UUID: {cat_id}")
        print(f"  Leaf: {is_leaf}")
    else:
        print(f"✗ {path} - не найдена")
    print()


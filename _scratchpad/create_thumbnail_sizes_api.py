"""
Создание thumbnail sizes через Shopware API
"""
import sys
from pathlib import Path
import json

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
print("СОЗДАНИЕ THUMBNAIL SIZES ЧЕРЕЗ API")
print("=" * 60)

# Проверяем существующие thumbnail sizes
print("\n1. Проверка существующих thumbnail sizes...")
try:
    response = client._request("GET", "/api/media-thumbnail-size")
    existing_sizes = response.get("data", []) if isinstance(response, dict) else []
    print(f"   Найдено существующих sizes: {len(existing_sizes)}")
    
    if existing_sizes:
        print("   Существующие размеры:")
        for size in existing_sizes[:5]:
            attrs = size.get("attributes", {})
            width = attrs.get("width", "N/A")
            height = attrs.get("height", "N/A")
            print(f"     - {width}x{height}")
except Exception as e:
    print(f"   Ошибка получения sizes: {str(e)[:100]}")
    existing_sizes = []

# Стандартные размеры для создания
thumbnail_sizes = [
    {"width": 200, "height": 200},
    {"width": 400, "height": 400},
    {"width": 800, "height": 800},
    {"width": 1920, "height": 1920},
]

# Проверяем, какие размеры уже есть
existing_widths = set()
for size in existing_sizes:
    attrs = size.get("attributes", {})
    width = attrs.get("width")
    height = attrs.get("height")
    if width and height:
        existing_widths.add((width, height))

# Создаём недостающие размеры
print("\n2. Создание недостающих thumbnail sizes...")
created = 0
for size in thumbnail_sizes:
    width = size["width"]
    height = size["height"]
    
    if (width, height) in existing_widths:
        print(f"   [SKIP] {width}x{height} уже существует")
        continue
    
    try:
        payload = {
            "width": width,
            "height": height
        }
        result = client._request("POST", "/api/media-thumbnail-size", json=payload)
        print(f"   [OK] {width}x{height} создан")
        created += 1
    except Exception as e:
        error_str = str(e)
        print(f"   [ERROR] {width}x{height}: {error_str[:150]}...")

print(f"\n   Создано новых sizes: {created}")

# Проверяем итоговый список
print("\n3. Итоговый список thumbnail sizes...")
try:
    response = client._request("GET", "/api/media-thumbnail-size")
    all_sizes = response.get("data", []) if isinstance(response, dict) else []
    print(f"   Всего sizes: {len(all_sizes)}")
    
    for size in all_sizes:
        attrs = size.get("attributes", {})
        width = attrs.get("width", "N/A")
        height = attrs.get("height", "N/A")
        print(f"     - {width}x{height}")
except Exception as e:
    print(f"   Ошибка: {str(e)[:100]}")

print("\n" + "=" * 60)
print("СОЗДАНИЕ ЗАВЕРШЕНО")
print("=" * 60)









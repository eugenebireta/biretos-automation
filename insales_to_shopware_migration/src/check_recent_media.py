"""Проверка последних загруженных медиа с деталями"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from clients import ShopwareClient, ShopwareConfig

config_path = Path(__file__).parent.parent / "config.json"
with config_path.open() as f:
    config = json.load(f)

sw = config["shopware"]
client = ShopwareClient(ShopwareConfig(sw["url"], sw["access_key_id"], sw["secret_access_key"]))

print("=" * 80)
print("ДЕТАЛЬНАЯ ПРОВЕРКА ПОСЛЕДНИХ МЕДИА")
print("=" * 80)
print()

# Получаем последние 10 медиа с полными данными
response = client._request(
    "POST",
    "/api/search/media",
    json={
        "limit": 10,
        "sort": [{"field": "createdAt", "order": "DESC"}],
        "associations": {"mediaFolder": {}},
    },
)
media_list = response.get("data", [])

print(f"Найдено медиа: {len(media_list)}\n")

for i, media in enumerate(media_list, 1):
    media_id = media.get("id")
    created_at = media.get("createdAt", "N/A")
    folder = media.get("mediaFolder", {})
    folder_id = folder.get("id") if folder else None
    folder_name = folder.get("name", {}) if folder else {}
    if isinstance(folder_name, dict):
        folder_name = folder_name.get("ru-RU") or folder_name.get("en-GB") or folder_name.get("de-DE") or str(folder_name)
    else:
        folder_name = str(folder_name) if folder_name else "None"
    
    print(f"[{i}] Media ID: {media_id}")
    print(f"    Created: {created_at}")
    print(f"    Folder ID: {folder_id or 'None (Default)'}")
    print(f"    Folder Name: {folder_name}")
    print()

# Проверяем папку "Product Media" через API
print("=" * 80)
print("ПРОВЕРКА ПАПКИ 'Product Media'")
print("=" * 80)
print()

folder_id = client.get_product_media_folder_id()
if folder_id:
    print(f"✓ Папка 'Product Media' найдена/создана: {folder_id}")
    # Получаем детали папки
    try:
        folder_response = client._request("GET", f"/api/media-folder/{folder_id}")
        folder_data = folder_response.get("data", {}) if isinstance(folder_response, dict) else folder_response
        config_id = folder_data.get("configurationId")
        print(f"  Configuration ID: {config_id}")
        if config_id:
            config_response = client._request("GET", f"/api/media-folder-configuration/{config_id}")
            config_data = config_response.get("data", {}) if isinstance(config_response, dict) else config_response
            sizes = config_data.get("thumbnailSizes", [])
            print(f"  Thumbnail sizes: {len(sizes)}")
            for size in sizes:
                print(f"    - {size.get('width')}x{size.get('height')}")
    except Exception as e:
        print(f"  Ошибка получения деталей: {e}")
else:
    print("✗ Папка 'Product Media' НЕ найдена и НЕ создана")

print()
print("=" * 80)





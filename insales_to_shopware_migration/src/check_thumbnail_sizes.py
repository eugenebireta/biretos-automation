"""Проверка thumbnail sizes в папках медиа"""
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
print("ПРОВЕРКА THUMBNAIL SIZES В ПАПКАХ МЕДИА")
print("=" * 80)
print()

# Получаем все папки
response = client._request(
    "POST",
    "/api/search/media-folder",
    json={"limit": 100},
)
folders = response.get("data", [])

print(f"Найдено папок: {len(folders)}\n")

for folder in folders:
    folder_id = folder.get("id")
    try:
        # Получаем полные данные папки
        folder_response = client._request("GET", f"/api/media-folder/{folder_id}")
        folder_data = folder_response.get("data", {}) if isinstance(folder_response, dict) else folder_response
        
        name = folder_data.get("name", {})
        if isinstance(name, dict):
            name = name.get("ru-RU") or name.get("en-GB") or name.get("de-DE") or str(name)
        else:
            name = str(name) if name else "Empty"
        
        # Получаем конфигурацию папки
        config_id = folder_data.get("configurationId")
        if config_id:
            try:
                config_response = client._request("GET", f"/api/media-folder-configuration/{config_id}")
                config_data = config_response.get("data", {}) if isinstance(config_response, dict) else config_response
                thumbnail_sizes = config_data.get("thumbnailSizes", [])
                print(f"Папка: '{name}' (ID: {folder_id})")
                print(f"  Конфигурация ID: {config_id}")
                print(f"  Thumbnail sizes: {len(thumbnail_sizes)}")
                if thumbnail_sizes:
                    for size in thumbnail_sizes:
                        width = size.get("width")
                        height = size.get("height")
                        print(f"    - {width}x{height}")
                else:
                    print("    - НЕТ РАЗМЕРОВ")
                print()
            except Exception as e:
                print(f"Папка: '{name}' (ID: {folder_id})")
                print(f"  Ошибка получения конфигурации: {e}\n")
        else:
            print(f"Папка: '{name}' (ID: {folder_id})")
            print(f"  Конфигурация: НЕТ\n")
    except Exception as e:
        print(f"Папка ID: {folder_id}, Ошибка: {e}\n")

print("=" * 80)





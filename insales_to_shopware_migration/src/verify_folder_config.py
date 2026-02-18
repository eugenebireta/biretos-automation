"""Проверка конфигурации папки Product Media"""
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
print("ПРОВЕРКА КОНФИГУРАЦИИ ПАПКИ 'Product Media'")
print("=" * 80)
print()

folder_id = client.get_product_media_folder_id()
if folder_id:
    print(f"Папка ID: {folder_id}")
    
    # Получаем детали папки
    folder_response = client._request("GET", f"/api/media-folder/{folder_id}")
    folder_data = folder_response.get("data", {}) if isinstance(folder_response, dict) else folder_response
    config_id = folder_data.get("configurationId")
    
    print(f"Configuration ID в папке: {config_id}")
    
    if config_id:
        # Получаем детали конфигурации
        config_response = client._request("GET", f"/api/media-folder-configuration/{config_id}")
        config_data = config_response.get("data", {}) if isinstance(config_response, dict) else config_response
        sizes = config_data.get("thumbnailSizes", [])
        print(f"Thumbnail sizes в конфигурации: {len(sizes)}")
        for size in sizes:
            print(f"  - {size.get('width')}x{size.get('height')}")
    else:
        print("⚠ Конфигурация НЕ связана с папкой!")
else:
    print("✗ Папка не найдена")

print()
print("=" * 80)





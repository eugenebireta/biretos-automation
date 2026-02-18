"""Тестовый скрипт для проверки загрузки медиа в папку"""
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
print("ТЕСТ ЗАГРУЗКИ МЕДИА В ПАПКУ")
print("=" * 80)
print()

# Получаем папку
folder_id = client.get_product_media_folder_id()
print(f"1. Папка Product Media ID: {folder_id}")

# Создаем тестовое медиа
print(f"\n2. Создание медиа с folder_id={folder_id}...")
media_id = client.create_media(media_folder_id=folder_id)
print(f"   Media ID: {media_id}")

# Проверяем, в какую папку попало медиа
print(f"\n3. Проверка папки медиа...")
media_response = client._request("GET", f"/api/media/{media_id}")
media_data = media_response.get("data", {}) if isinstance(media_response, dict) else media_response
actual_folder_id = media_data.get("mediaFolderId")
print(f"   Folder ID в медиа: {actual_folder_id}")
print(f"   Ожидалось: {folder_id}")
print(f"   Совпадает: {actual_folder_id == folder_id}")

print()
print("=" * 80)





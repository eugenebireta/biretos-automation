"""Скрипт для проверки медиа-папок и конфигураций в Shopware"""
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
print("ПРОВЕРКА МЕДИА-ПАПОК В SHOPWARE")
print("=" * 80)
print()

# 1. Список всех папок медиа (через GET для полных данных)
print("[1] Все папки медиа:")
try:
    response = client._request(
        "POST",
        "/api/search/media-folder",
        json={
            "limit": 100,
        },
    )
    folders = response.get("data", [])
    print(f"   Найдено папок: {len(folders)}")
    for folder in folders:
        folder_id = folder.get("id")
        # Получаем полные данные папки через GET
        try:
            folder_response = client._request("GET", f"/api/media-folder/{folder_id}")
            folder_data = folder_response.get("data", {}) if isinstance(folder_response, dict) else folder_response
            name = folder_data.get("name", {})
            if isinstance(name, dict):
                name = name.get("ru-RU") or name.get("en-GB") or name.get("de-DE") or str(name)
            else:
                name = str(name) if name else "Empty"
            print(f"   - ID: {folder_id}, Name: '{name}'")
        except Exception as e2:
            print(f"   - ID: {folder_id}, Name: <error getting name: {e2}>")
except Exception as e:
    print(f"   ОШИБКА: {e}")

print()

# 2. Поиск папки "Product Media"
print("[2] Поиск папки 'Product Media':")
try:
    response = client._request(
        "POST",
        "/api/search/media-folder",
        json={
            "filter": [{"field": "name", "type": "equals", "value": "Product Media"}],
            "limit": 1,
            "includes": {"media_folder": ["id", "name"]},
        },
    )
    print(f"   Total: {response.get('total', 0)}")
    if response.get("total") and response.get("data"):
        folder = response["data"][0]
        print(f"   Найдена: ID={folder.get('id')}, Name={folder.get('name')}")
    else:
        print("   НЕ НАЙДЕНА")
except Exception as e:
    print(f"   ОШИБКА: {e}")

print()

# 3. Конфигурации папок для entity "product"
print("[3] Конфигурации папок для entity 'product':")
try:
    response = client._request(
        "POST",
        "/api/search/media-folder-configuration",
        json={
            "filter": [{"field": "entity", "type": "equals", "value": "product"}],
            "limit": 10,
        },
    )
    configs = response.get("data", [])
    print(f"   Найдено конфигураций: {len(configs)}")
    for cfg in configs:
        entity = cfg.get("entity")
        folder_id = cfg.get("mediaFolderId")
        if folder_id:
            # Получаем папку через GET
            try:
                folder_response = client._request("GET", f"/api/media-folder/{folder_id}")
                folder_data = folder_response.get("data", {}) if isinstance(folder_response, dict) else folder_response
                folder_name = folder_data.get("name", {})
                if isinstance(folder_name, dict):
                    folder_name = folder_name.get("ru-RU") or folder_name.get("en-GB") or folder_name.get("de-DE") or str(folder_name)
                else:
                    folder_name = str(folder_name) if folder_name else "Empty"
                print(f"   - Entity: {entity}, Folder ID: {folder_id}, Folder Name: '{folder_name}'")
            except Exception as e2:
                print(f"   - Entity: {entity}, Folder ID: {folder_id}, Folder Name: <error: {e2}>")
        else:
            print(f"   - Entity: {entity}, Folder ID: None")
except Exception as e:
    print(f"   ОШИБКА: {e}")

print()

# 4. Проверка последних загруженных медиа
print("[4] Последние 5 медиа-файлов:")
try:
    response = client._request(
        "POST",
        "/api/search/media",
        json={
            "limit": 5,
            "sort": [{"field": "createdAt", "order": "DESC"}],
            "associations": {"mediaFolder": {}},
        },
    )
    media_list = response.get("data", [])
    print(f"   Найдено медиа: {len(media_list)}")
    for media in media_list:
        media_id = media.get("id")
        folder = media.get("mediaFolder", {})
        folder_id = folder.get("id") if folder else None
        folder_name = folder.get("name", {}) if folder else {}
        if isinstance(folder_name, dict):
            folder_name = folder_name.get("ru-RU") or folder_name.get("en-GB") or str(folder_name)
        print(f"   - Media ID: {media_id}, Folder ID: {folder_id}, Folder Name: {folder_name or 'None'}")
except Exception as e:
    print(f"   ОШИБКА: {e}")

print()
print("=" * 80)


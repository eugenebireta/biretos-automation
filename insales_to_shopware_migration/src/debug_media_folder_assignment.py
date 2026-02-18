"""Диагностика проблемы с сохранением mediaFolderId и configurationId"""
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
print("ДИАГНОСТИКА: СОХРАНЕНИЕ mediaFolderId И configurationId")
print("=" * 80)
print()

# Шаг 1: Получаем папку Product Media
folder_id = client.get_product_media_folder_id()
print(f"[1] Папка Product Media ID: {folder_id}")
print()

# Шаг 2: Тест создания медиа с mediaFolderId
print("[2] ТЕСТ: Создание медиа с mediaFolderId")
print("-" * 80)
import uuid
test_media_id = str(uuid.uuid4().hex)
payload = {
    "id": test_media_id,
    "mediaFolderId": folder_id,
}
print(f"Payload отправлен:")
print(json.dumps(payload, indent=2, ensure_ascii=False))
print()

try:
    response = client._request("POST", "/api/media", json=payload)
    print(f"Response:")
    print(json.dumps(response, indent=2, ensure_ascii=False)[:500])
    print()
    
    # Проверяем, сохранилось ли
    check_response = client._request("GET", f"/api/media/{test_media_id}")
    check_data = check_response.get("data", {}) if isinstance(check_response, dict) else check_response
    saved_folder_id = check_data.get("attributes", {}).get("mediaFolderId")
    print(f"Результат GET /api/media/{test_media_id}:")
    print(f"  mediaFolderId в attributes: {saved_folder_id}")
    print(f"  Ожидалось: {folder_id}")
    print(f"  Сохранилось: {saved_folder_id == folder_id}")
    print()
    
    # Проверяем association
    media_folder_assoc = check_data.get("relationships", {}).get("mediaFolder", {})
    print(f"  mediaFolder association: {media_folder_assoc.get('data')}")
    print()
except Exception as e:
    print(f"ОШИБКА: {e}")
    print()

# Шаг 3: Тест обновления папки с configurationId
print("[3] ТЕСТ: Обновление папки с configurationId через PATCH")
print("-" * 80)

# Сначала создаем конфигурацию
config_id = str(uuid.uuid4().hex)
config_payload = {
    "id": config_id,
    "thumbnailSizes": [
        {"width": 400, "height": 400},
        {"width": 800, "height": 800},
    ],
}
print(f"Создание конфигурации:")
print(json.dumps(config_payload, indent=2, ensure_ascii=False))
print()

try:
    client._request("POST", "/api/media-folder-configuration", json=config_payload)
    print(f"Конфигурация создана: {config_id}")
    print()
    
    # Пробуем PATCH
    patch_payload = {
        "id": folder_id,
        "configurationId": config_id,
    }
    print(f"PATCH payload:")
    print(json.dumps(patch_payload, indent=2, ensure_ascii=False))
    print()
    
    client._request("PATCH", f"/api/media-folder/{folder_id}", json=patch_payload)
    print("PATCH выполнен")
    print()
    
    # Проверяем результат
    verify_response = client._request("GET", f"/api/media-folder/{folder_id}")
    verify_data = verify_response.get("data", {}) if isinstance(verify_response, dict) else verify_response
    saved_config_id = verify_data.get("configurationId")
    print(f"Результат GET /api/media-folder/{folder_id}:")
    print(f"  configurationId: {saved_config_id}")
    print(f"  Ожидалось: {config_id}")
    print(f"  Сохранилось: {saved_config_id == config_id}")
    print()
except Exception as e:
    print(f"ОШИБКА: {e}")
    import traceback
    traceback.print_exc()
    print()

# Шаг 4: Тест через Sync API
print("[4] ТЕСТ: Обновление через Sync API")
print("-" * 80)

try:
    # Создаем новую конфигурацию для теста
    sync_config_id = str(uuid.uuid4().hex)
    sync_config_payload = {
        "id": sync_config_id,
        "thumbnailSizes": [
            {"width": 192, "height": 192},
            {"width": 400, "height": 400},
        ],
    }
    
    # Получаем текущие данные папки
    folder_get = client._request("GET", f"/api/media-folder/{folder_id}")
    folder_data = folder_get.get("data", {}) if isinstance(folder_get, dict) else folder_get
    folder_name = folder_data.get("name", {"ru-RU": "Product Media", "en-GB": "Product Media", "de-DE": "Product Media"})
    
    sync_payload = [
        {
            "entity": "media_folder_configuration",
            "action": "upsert",
            "payload": [sync_config_payload]
        },
        {
            "entity": "media_folder",
            "action": "upsert",
            "payload": [{
                "id": folder_id,
                "name": folder_name,
                "configurationId": sync_config_id,
            }]
        }
    ]
    
    print(f"Sync payload:")
    print(json.dumps(sync_payload, indent=2, ensure_ascii=False))
    print()
    
    sync_response = client._request("POST", "/api/_action/sync", json=sync_payload)
    print(f"Sync response:")
    print(json.dumps(sync_response, indent=2, ensure_ascii=False)[:500])
    print()
    
    # Проверяем результат
    sync_verify = client._request("GET", f"/api/media-folder/{folder_id}")
    sync_verify_data = sync_verify.get("data", {}) if isinstance(sync_verify, dict) else sync_verify
    sync_saved_config_id = sync_verify_data.get("configurationId")
    print(f"Результат GET /api/media-folder/{folder_id} после Sync:")
    print(f"  configurationId: {sync_saved_config_id}")
    print(f"  Ожидалось: {sync_config_id}")
    print(f"  Сохранилось: {sync_saved_config_id == sync_config_id}")
    print()
except Exception as e:
    print(f"ОШИБКА: {e}")
    import traceback
    traceback.print_exc()
    print()

print("=" * 80)
print("ДИАГНОСТИКА ЗАВЕРШЕНА")
print("=" * 80)


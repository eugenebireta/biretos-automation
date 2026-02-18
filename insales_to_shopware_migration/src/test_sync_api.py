"""Тест Sync API для связи папки с конфигурацией"""
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

folder_id = "01994d23ada87207aa7d8cb9994f5198"

# Получаем текущие данные папки
folder_get = client._request("GET", f"/api/media-folder/{folder_id}")
folder_data = folder_get.get("data", {}) if isinstance(folder_get, dict) else folder_get
print(f"Текущий configurationId: {folder_data.get('configurationId')}")
print(f"Текущее name: {folder_data.get('name')}")
print()

# Создаем новую конфигурацию
import uuid
config_id = str(uuid.uuid4().hex)
config_payload = {
    "id": config_id,
    "thumbnailSizes": [
        {"width": 400, "height": 400},
        {"width": 800, "height": 800},
    ],
}
client._request("POST", "/api/media-folder-configuration", json=config_payload)
print(f"Создана конфигурация: {config_id}")
print()

# Пробуем Sync API с разными форматами
print("ТЕСТ 1: Sync API с name как строка")
sync_payload1 = [
    {
        "entity": "media_folder",
        "action": "upsert",
        "payload": [{
            "id": folder_id,
            "name": "Product Media",
            "configurationId": config_id,
        }]
    }
]
print(f"Payload: {json.dumps(sync_payload1, indent=2)}")
try:
    response1 = client._request("POST", "/api/_action/sync", json=sync_payload1)
    print(f"Response: {json.dumps(response1, indent=2)[:500]}")
except Exception as e:
    print(f"Ошибка: {e}")
print()

# Проверяем результат
verify1 = client._request("GET", f"/api/media-folder/{folder_id}")
verify1_data = verify1.get("data", {}) if isinstance(verify1, dict) else verify1
print(f"configurationId после Sync: {verify1_data.get('configurationId')}")
print()





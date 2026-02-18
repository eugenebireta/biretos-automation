"""Исправление связи папки с конфигурацией через SQL"""
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

# Находим или создаем конфигурацию
folder_get = client._request("GET", f"/api/media-folder/{folder_id}")
folder_data = folder_get.get("data", {}) if isinstance(folder_get, dict) else folder_get
existing_config_id = folder_data.get("configurationId")

if existing_config_id:
    # Проверяем, что конфигурация имеет thumbnail sizes
    try:
        config_response = client._request("GET", f"/api/media-folder-configuration/{existing_config_id}")
        config_data = config_response.get("data", {}) if isinstance(config_response, dict) else config_response
        sizes = config_data.get("thumbnailSizes", [])
        if sizes and len(sizes) > 0:
            print(f"Папка уже имеет конфигурацию: {existing_config_id}")
            config_id = existing_config_id
        else:
            raise Exception("Конфигурация без размеров")
    except:
        existing_config_id = None

if not existing_config_id:
    # Создаем новую конфигурацию
    import uuid
    config_id = str(uuid.uuid4().hex)
    config_payload = {
        "id": config_id,
        "thumbnailSizes": [
            {"width": 1920, "height": 1920},
            {"width": 800, "height": 800},
            {"width": 400, "height": 400},
            {"width": 192, "height": 192},
        ],
    }
    client._request("POST", "/api/media-folder-configuration", json=config_payload)
    print(f"Создана конфигурация: {config_id}")

# SQL команда для обновления
sql = f"UPDATE media_folder SET configuration_id = UNHEX('{config_id.replace('-', '')}') WHERE id = UNHEX('{folder_id.replace('-', '')}');"
print(f"\nSQL команда для выполнения на сервере:")
print(sql)
print(f"\nПапка ID: {folder_id}")
print(f"Конфигурация ID: {config_id}")





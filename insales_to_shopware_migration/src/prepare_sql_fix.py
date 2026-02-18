"""Подготовка SQL фикса для связи папки с конфигурацией"""
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

print("=" * 80)
print("ПОДГОТОВКА SQL ФИКСА")
print("=" * 80)
print()

# Проверяем текущее состояние папки
folder_get = client._request("GET", f"/api/media-folder/{folder_id}")
folder_data = folder_get.get("data", {}) if isinstance(folder_get, dict) else folder_get
existing_config_id = folder_data.get("configurationId")

print(f"Папка Product Media ID: {folder_id}")
print(f"Текущий configurationId: {existing_config_id}")
print()

# Создаем или используем существующую конфигурацию
if existing_config_id:
    # Проверяем, что конфигурация имеет thumbnail sizes
    try:
        config_response = client._request("GET", f"/api/media-folder-configuration/{existing_config_id}")
        config_data = config_response.get("data", {}) if isinstance(config_response, dict) else config_response
        sizes = config_data.get("thumbnailSizes", [])
        if sizes and len(sizes) > 0:
            print(f"✓ Найдена существующая конфигурация: {existing_config_id}")
            print(f"  Thumbnail sizes: {len(sizes)}")
            config_id = existing_config_id
        else:
            existing_config_id = None
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
    print(f"✓ Создана новая конфигурация: {config_id}")
    print(f"  Thumbnail sizes: {len(config_payload['thumbnailSizes'])}")
    print()

# Генерируем SQL команду
folder_id_hex = folder_id.replace('-', '')
config_id_hex = config_id.replace('-', '')

sql = f"UPDATE media_folder SET configuration_id = UNHEX('{config_id_hex}') WHERE id = UNHEX('{folder_id_hex}');"

print("=" * 80)
print("SQL КОМАНДА ДЛЯ ВЫПОЛНЕНИЯ:")
print("=" * 80)
print(sql)
print()
print(f"Папка ID (HEX): {folder_id_hex}")
print(f"Конфигурация ID (HEX): {config_id_hex}")
print()
print("=" * 80)

# Сохраняем в файл для использования
with open(Path(__file__).parent / "sql_fix.txt", "w") as f:
    f.write(f"FOLDER_ID={folder_id}\n")
    f.write(f"CONFIG_ID={config_id}\n")
    f.write(f"FOLDER_ID_HEX={folder_id_hex}\n")
    f.write(f"CONFIG_ID_HEX={config_id_hex}\n")
    f.write(f"SQL={sql}\n")

print("✓ Данные сохранены в sql_fix.txt")





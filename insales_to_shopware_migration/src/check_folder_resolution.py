"""Проверка разрешения папки в реальном импорте"""
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

print("Проверка разрешения папки:")
folder_id = client.get_product_media_folder_id()
print(f"get_product_media_folder_id() возвращает: {folder_id}")
print(f"Тип: {type(folder_id)}")
print(f"None? {folder_id is None}")





"""Проверка конфигурации thumbnail sizes"""
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

config_id = "019A0C73E2A9739DAE82E8A78764D4EA"

print("Проверка конфигурации:")
try:
    response = client._request("GET", f"/api/media-folder-configuration/{config_id}")
    config_data = response.get("data", {}) if isinstance(response, dict) else response
    print(f"Config ID: {config_id}")
    print(f"create_thumbnails: {config_data.get('createThumbnails')}")
    print(f"thumbnail_quality: {config_data.get('thumbnailQuality')}")
    print(f"media_thumbnail_sizes_ro: {config_data.get('mediaThumbnailSizesRo')}")
    print(f"keep_aspect_ratio: {config_data.get('keepAspectRatio')}")
except Exception as e:
    print(f"Ошибка: {e}")





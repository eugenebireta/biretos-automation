"""Проверка структуры медиа для определения правильного поля"""
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

# Получаем существующее медиа
response = client._request(
    "POST",
    "/api/search/media",
    json={
        "limit": 1,
        "associations": {"mediaFolder": {}},
    },
)
media_list = response.get("data", [])

if media_list:
    media = media_list[0]
    print("Структура медиа:")
    print(json.dumps(media, indent=2, ensure_ascii=False))
    
    print("\n" + "=" * 80)
    print("Поля медиа:")
    for key in media.keys():
        print(f"  - {key}: {type(media[key]).__name__}")





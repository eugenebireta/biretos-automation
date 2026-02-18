"""
Детальная проверка медиа для понимания, почему они пропускаются
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json

ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
config = load_json(ROOT / "config.json")

shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

print("=" * 60)
print("ДЕТАЛЬНАЯ ПРОВЕРКА МЕДИА")
print("=" * 60)

# Получаем несколько медиа
print("\n1. Получение медиа...")
media_response = client._request("GET", "/api/media", params={"limit": 5})
media_list = media_response.get("data", []) if isinstance(media_response, dict) else []

print(f"Найдено медиа: {len(media_list)}")

for idx, media in enumerate(media_list, 1):
    media_id = media.get("id")
    attrs = media.get("attributes", {})
    
    print(f"\n{idx}. Медиа ID: {media_id[:16]}...")
    print(f"   File name: {attrs.get('fileName', 'N/A')}")
    print(f"   File extension: {attrs.get('fileExtension', 'N/A')}")
    print(f"   MIME type: {attrs.get('mimeType', 'N/A')}")
    print(f"   File size: {attrs.get('fileSize', 'N/A')} bytes")
    print(f"   URL: {attrs.get('url', 'N/A')[:80]}...")
    print(f"   Thumbnails: {len(attrs.get('thumbnails', []))}")
    
    # Проверяем, есть ли файл физически
    print(f"   Проверка файла...")
    url = attrs.get("url", "")
    if url:
        try:
            import requests
            response = requests.head(url, verify=False, timeout=5)
            print(f"     HTTP Status: {response.status_code}")
            if response.status_code == 200:
                print(f"     [OK] Файл доступен")
            else:
                print(f"     [WARNING] Файл недоступен (код {response.status_code})")
        except Exception as e:
            print(f"     [ERROR] Ошибка проверки: {str(e)[:100]}")

print("\n" + "=" * 60)









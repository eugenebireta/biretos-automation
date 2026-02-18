"""
Проверка состояния media (не thumbnail sizes)
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
print("ПРОВЕРКА СОСТОЯНИЯ MEDIA")
print("=" * 60)

# Получаем несколько медиа
print("\n1. Получение медиа...")
response = client._request("GET", "/api/media", params={"limit": 5})
media_list = response.get("data", []) if isinstance(response, dict) else []

print(f"   Найдено медиа: {len(media_list)}")

for idx, media in enumerate(media_list, 1):
    media_id = media.get("id")
    attrs = media.get("attributes", {})
    
    print(f"\n{idx}. Медиа ID: {media_id[:16]}...")
    print(f"   File name: {attrs.get('fileName', 'N/A')}")
    print(f"   File extension: {attrs.get('fileExtension', 'N/A')}")
    print(f"   MIME type: {attrs.get('mimeType', 'N/A')}")
    print(f"   File size: {attrs.get('fileSize', 'N/A')} bytes")
    
    # Проверяем mediaType
    media_type_id = attrs.get("mediaTypeId")
    if media_type_id:
        try:
            type_response = client._request("GET", f"/api/media-type/{media_type_id}")
            type_data = type_response.get("data", {}) if isinstance(type_response, dict) else {}
            type_attrs = type_data.get("attributes", {})
            print(f"   Media type: {type_attrs.get('name', 'N/A')}")
        except:
            print(f"   Media type ID: {media_type_id}")
    
    # Проверяем processedAt
    processed_at = attrs.get("uploadedAt") or attrs.get("createdAt")
    print(f"   Uploaded at: {processed_at}")
    
    # Проверяем thumbnails
    thumbnails = attrs.get("thumbnails", [])
    print(f"   Thumbnails count: {len(thumbnails)}")
    
    # Проверяем relationships для thumbnailsRo
    relationships = media.get("relationships", {})
    thumbnails_ro = relationships.get("thumbnailsRo", {})
    if thumbnails_ro:
        thumbnails_data = thumbnails_ro.get("data", [])
        print(f"   ThumbnailsRo count: {len(thumbnails_data)}")
    
    # Проверяем, является ли это изображением
    mime_type = attrs.get("mimeType", "")
    is_image = mime_type.startswith("image/")
    print(f"   Is image: {is_image}")
    
    if is_image and len(thumbnails) == 0:
        print(f"   [WARNING] Изображение без thumbnails!")

print("\n" + "=" * 60)
print("АНАЛИЗ")
print("=" * 60)

# Проверяем, почему Shopware считает медиа "не требующими обработки"
print("\nПочему Shopware пропускает медиа:")
print("1. Проверяем наличие processedAt/uploadedAt")
print("2. Проверяем mediaType (должен быть 'image')")
print("3. Проверяем наличие thumbnails в базе")









"""
Детальная проверка изображений товаров и их отображения.
"""
import sys
from pathlib import Path
import json

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
print("ДЕТАЛЬНАЯ ПРОВЕРКА ИЗОБРАЖЕНИЙ ТОВАРОВ")
print("=" * 60)

# Получаем товары с associations для медиа
print("\n1. Получение товаров с медиа...")
response = client._request("GET", "/api/product", params={
    "limit": 10,
    "associations[media][]": "media"
})
products = response.get("data", []) if isinstance(response, dict) else []
included = response.get("included", []) if isinstance(response, dict) else []

print(f"   Найдено товаров: {len(products)}")
print(f"   Included items: {len(included)}")

# Проверяем каждый товар
print("\n2. Проверка товаров:")
for product in products:
    product_id = product.get("id")
    attrs = product.get("attributes", {})
    product_number = attrs.get("productNumber", "N/A")
    name = attrs.get("name", "N/A")[:50]
    
    print(f"\n   Товар: {product_number} - {name}")
    
    # Проверяем cover
    cover_id = attrs.get("coverId")
    print(f"   Cover ID: {cover_id or 'НЕТ'}")
    
    # Проверяем relationships
    relationships = product.get("relationships", {})
    media_rel = relationships.get("media")
    if media_rel:
        media_data = media_rel.get("data", [])
        print(f"   Relationships.media: {len(media_data)} шт.")
        for m in media_data[:3]:
            media_id = m.get("id")
            print(f"     - Media ID: {media_id}")
    
    # Ищем медиа в included
    if cover_id:
        for item in included:
            if item.get("id") == cover_id and item.get("type") == "media":
                media_attrs = item.get("attributes", {})
                url = media_attrs.get("url")
                thumbnails = media_attrs.get("thumbnails", [])
                print(f"   Cover URL: {url or 'N/A'}")
                print(f"   Thumbnails: {len(thumbnails)} шт.")
                if thumbnails:
                    for thumb in thumbnails[:3]:
                        thumb_url = thumb.get("url")
                        print(f"     - {thumb_url}")

# Проверяем медиа напрямую
print("\n3. Проверка медиа напрямую...")
media_response = client._request("GET", "/api/media", params={"limit": 10})
media_items = media_response.get("data", []) if isinstance(media_response, dict) else []

print(f"   Найдено медиа: {len(media_items)}")
for media in media_items[:5]:
    media_id = media.get("id")
    attrs = media.get("attributes", {})
    url = attrs.get("url")
    mime_type = attrs.get("mimeType", "")
    print(f"   - {media_id[:16]}... - {mime_type} - {url or 'N/A'}")

# Проверяем product_media через БД
print("\n4. Проверка product_media через БД...")
import paramiko

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=ssh_username, password=ssh_password, timeout=10)
    
    command = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT pm.product_id, pm.media_id, m.url, m.mime_type FROM product_media pm JOIN media m ON pm.media_id = m.id WHERE m.mime_type LIKE 'image/%' LIMIT 10;\" 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    output = stdout.read().decode().strip()
    
    if output:
        print("   Product-media связи:")
        lines = [l for l in output.split('\n') if l.strip() and 'product_id' not in l.lower()]
        for line in lines[:10]:
            print(f"   - {line.strip()}")
    else:
        print("   ⚠️  Не удалось получить данные")
    
    ssh.close()
except Exception as e:
    print(f"   ⚠️  Ошибка подключения: {e}")

print("\n" + "=" * 60)
print("ПРОВЕРКА ЗАВЕРШЕНА")
print("=" * 60)








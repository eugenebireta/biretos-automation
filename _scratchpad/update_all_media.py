"""
Обновление всех медиа для триггера генерации thumbnails
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
print("ОБНОВЛЕНИЕ ВСЕХ МЕДИА ДЛЯ ГЕНЕРАЦИИ THUMBNAILS")
print("=" * 60)

# Получаем все медиа
print("\n1. Получение всех медиа...")
all_media = []
page = 1
while True:
    response = client._request("GET", "/api/media", params={"limit": 100, "page": page})
    media_list = response.get("data", []) if isinstance(response, dict) else []
    
    if not media_list:
        break
    
    all_media.extend(media_list)
    print(f"   Страница {page}: {len(media_list)} медиа")
    
    # Проверяем, есть ли ещё страницы
    links = response.get("links", {})
    if not links.get("next"):
        break
    
    page += 1

print(f"\n   Всего медиа: {len(all_media)}")

# Обновляем каждое медиа
print("\n2. Обновление медиа...")
updated = 0
errors = 0

for idx, media in enumerate(all_media, 1):
    media_id = media.get("id")
    attrs = media.get("attributes", {})
    file_name = attrs.get("fileName", "N/A")
    
    try:
        # Обновляем медиа (минимальное изменение для триггера)
        update_payload = {
            "id": media_id,
            "alt": attrs.get("alt") or file_name
        }
        client._request("PATCH", f"/api/media/{media_id}", json=update_payload)
        updated += 1
        
        if idx % 10 == 0:
            print(f"   Обновлено: {updated}/{len(all_media)}")
            
    except Exception as e:
        errors += 1
        if errors <= 5:
            print(f"   [ERROR] Медиа {media_id[:16]}...: {str(e)[:80]}")

print(f"\n   Итого: обновлено {updated}, ошибок {errors}")

# Запускаем генерацию thumbnails
print("\n3. Генерация thumbnails после обновления...")
import paramiko

host = "77.233.222.214"
username = "root"
password = "HuPtNj39"

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    
    command = "docker exec shopware php bin/console media:generate-thumbnails"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=300)
    
    for line in stdout:
        line = line.strip()
        if line:
            print(f"     {line}")
    
    ssh.close()
    
except Exception as e:
    print(f"   [ERROR] Ошибка генерации: {e}")

print("\n" + "=" * 60)
print("ОБНОВЛЕНИЕ ЗАВЕРШЕНО")
print("=" * 60)









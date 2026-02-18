"""
Финальное исправление: установка mediaType и генерация thumbnails
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
print("УСТАНОВКА MEDIATYPE И ГЕНЕРАЦИЯ THUMBNAILS")
print("=" * 60)

# Получаем mediaType для изображений
print("\n1. Поиск mediaType для изображений...")
try:
    type_response = client._request("GET", "/api/media-type")
    types = type_response.get("data", []) if isinstance(type_response, dict) else []
    
    image_type_id = None
    for mt in types:
        attrs = mt.get("attributes", {})
        name = attrs.get("name", "").lower()
        if "image" in name:
            image_type_id = mt.get("id")
            print(f"   [FOUND] MediaType: {attrs.get('name')} (ID: {image_type_id})")
            break
    
    if not image_type_id:
        print("   [ERROR] MediaType для изображений не найден!")
        print("   Запустите: docker exec shopware php bin/console media:generate-media-types")
        exit(1)
except Exception as e:
    print(f"   [ERROR] Ошибка получения mediaType: {e}")
    exit(1)

# Получаем все изображения
print("\n2. Получение всех изображений...")
all_media = []
page = 1
while True:
    response = client._request("GET", "/api/media", params={"limit": 100, "page": page})
    media_list = response.get("data", []) if isinstance(response, dict) else []
    
    if not media_list:
        break
    
    for media in media_list:
        attrs = media.get("attributes", {})
        mime_type = attrs.get("mimeType") or ""
        if mime_type and mime_type.startswith("image/"):
            all_media.append(media)
    
    page += 1
    if page > 10:
        break

print(f"   Найдено изображений: {len(all_media)}")

# Устанавливаем mediaType
print(f"\n3. Установка mediaType для {len(all_media)} изображений...")
updated = 0
errors = 0

for idx, media in enumerate(all_media, 1):
    media_id = media.get("id")
    attrs = media.get("attributes", {})
    current_type_id = attrs.get("mediaTypeId")
    
    # Пропускаем, если уже установлен
    if current_type_id == image_type_id:
        continue
    
    try:
        update_payload = {
            "id": media_id,
            "mediaTypeId": image_type_id
        }
        client._request("PATCH", f"/api/media/{media_id}", json=update_payload)
        updated += 1
        
        if idx % 10 == 0:
            print(f"   Обновлено: {updated}/{len(all_media)}")
    except Exception as e:
        errors += 1
        if errors <= 5:
            print(f"   [ERROR] {media_id[:16]}...: {str(e)[:50]}")

print(f"\n   [OK] Обновлено: {updated}, ошибок: {errors}")

# Генерируем thumbnails через SSH
print("\n4. Генерация thumbnails...")
import paramiko

host = "77.233.222.214"
username = "root"
password = "HuPtNj39"

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    
    command = "docker exec shopware php bin/console media:generate-thumbnails 2>&1"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=600)
    
    generated = 0
    for line in stdout:
        try:
            line_str = line.decode('utf-8', errors='ignore').strip()
            if line_str and ("Generated" in line_str or "Skipped" in line_str):
                print(f"     {line_str}")
                if "Generated" in line_str:
                    try:
                        parts = line_str.split()
                        for i, part in enumerate(parts):
                            if part == "Generated" and i + 1 < len(parts):
                                generated = int(parts[i + 1])
                    except:
                        pass
        except:
            pass
    
    print(f"\n   [RESULT] Generated: {generated}")
    
    # Очищаем кеш
    print("\n5. Очистка кеша...")
    command = "docker exec shopware php bin/console cache:clear"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
    stdout.read()
    print("   [OK] Кеш очищен")
    
    ssh.close()
    
except Exception as e:
    print(f"   [ERROR] Ошибка SSH: {e}")

print("\n" + "=" * 60)
print("ИСПРАВЛЕНИЕ ЗАВЕРШЕНО")
print("=" * 60)









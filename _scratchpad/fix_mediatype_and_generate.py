"""
ИСПРАВЛЕНИЕ: Установка mediaType и генерация thumbnails
"""
import paramiko
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json

host = "77.233.222.214"
username = "root"
password = "HuPtNj39"

ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
config = load_json(ROOT / "config.json")

shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

print("=" * 60)
print("ИСПРАВЛЕНИЕ: УСТАНОВКА MEDIATYPE")
print("=" * 60)

# Получаем все изображения
print("\n1. Получение всех изображений...")
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

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    
    # Находим правильный mediaType для изображений
    print("\n2. Поиск mediaType для изображений...")
    # Пробуем разные варианты названий таблиц
    tables_to_check = [
        "media_type",
        "media_type_translation", 
    ]
    
    image_type_id = None
    
    # Ищем через API
    try:
        type_response = client._request("GET", "/api/media-type")
        types = type_response.get("data", []) if isinstance(type_response, dict) else []
        
        for mt in types:
            attrs = mt.get("attributes", {})
            name = attrs.get("name", "").lower()
            if "image" in name:
                image_type_id = mt.get("id")
                print(f"   [FOUND] MediaType для изображений: {attrs.get('name')} (ID: {image_type_id})")
                break
    except:
        pass
    
    # Если не нашли через API, ищем в БД
    if not image_type_id:
        print("   Поиск в БД...")
        command = "docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SHOW TABLES LIKE '%media%type%';\" 2>&1 | grep -v Warning"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        tables = stdout.read().decode()
        
        if tables.strip():
            print(f"   Найденные таблицы: {tables.strip()}")
    
    # Если всё ещё не нашли, используем media:generate-media-types
    if not image_type_id:
        print("\n3. Генерация media types...")
        command = "docker exec shopware php bin/console media:generate-media-types 2>&1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
        gen_output = stdout.read().decode()
        
        if gen_output.strip():
            print("   Результат:")
            for line in gen_output.split('\n')[:10]:
                if line.strip():
                    print(f"     {line}")
        
        # Пробуем найти снова
        try:
            type_response = client._request("GET", "/api/media-type")
            types = type_response.get("data", []) if isinstance(type_response, dict) else []
            
            for mt in types:
                attrs = mt.get("attributes", {})
                name = attrs.get("name", "").lower()
                if "image" in name:
                    image_type_id = mt.get("id")
                    print(f"   [FOUND] MediaType: {attrs.get('name')} (ID: {image_type_id})")
                    break
        except:
            pass
    
    # Устанавливаем mediaType для всех изображений
    if image_type_id:
        print(f"\n4. Установка mediaType для {len(all_media)} изображений...")
        updated = 0
        for media in all_media:
            media_id = media.get("id")
            try:
                update_payload = {
                    "id": media_id,
                    "mediaTypeId": image_type_id
                }
                client._request("PATCH", f"/api/media/{media_id}", json=update_payload)
                updated += 1
                
                if updated % 10 == 0:
                    print(f"   Обновлено: {updated}/{len(all_media)}")
            except Exception as e:
                print(f"   [ERROR] Ошибка обновления {media_id[:16]}...: {str(e)[:50]}")
        
        print(f"   [OK] Обновлено медиа: {updated}")
        
        # Генерируем thumbnails
        print("\n5. Генерация thumbnails после установки mediaType...")
        command = "docker exec shopware php bin/console media:generate-thumbnails -vv 2>&1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=600)
        
        generated = 0
        for line in stdout:
            try:
                line_str = line.decode('utf-8', errors='ignore').strip()
                if line_str and ("Generated" in line_str or "Skipped" in line_str or "Processing" in line_str):
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
        
        # Проверяем результат
        if all_media:
            test_media_id = all_media[0].get("id")
            command = f"docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(*) as count FROM media_thumbnail WHERE media_id = '{test_media_id}';\" 2>&1 | grep -v Warning | tail -1"
            stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
            count = stdout.read().decode().strip()
            print(f"   Thumbnails в БД для тестового медиа: {count}")
            
            command = f"docker exec shopware find /var/www/html/public/media/thumbnail -name '*{test_media_id}*' 2>/dev/null | wc -l"
            stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
            disk_count = stdout.read().decode().strip()
            print(f"   Thumbnails на диске для тестового медиа: {disk_count}")
    else:
        print("\n   [ERROR] Не удалось найти mediaType для изображений!")
    
    ssh.close()
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)









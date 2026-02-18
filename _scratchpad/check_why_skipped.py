"""
Проверка, почему Shopware пропускает наши медиа
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
print("АНАЛИЗ: ПОЧЕМУ SHOPWARE ПРОПУСКАЕТ МЕДИА")
print("=" * 60)

# Получаем наши медиа (загруженные через API)
print("\n1. Получение наших медиа...")
response = client._request("GET", "/api/media", params={"limit": 5})
media_list = response.get("data", []) if isinstance(response, dict) else []

print(f"   Найдено медиа: {len(media_list)}")

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    
    for idx, media in enumerate(media_list, 1):
        media_id = media.get("id")
        attrs = media.get("attributes", {})
        file_name = attrs.get("fileName", "N/A")
        mime_type = attrs.get("mimeType", "")
        
        print(f"\n{idx}. Медиа: {file_name}")
        print(f"   ID: {media_id}")
        print(f"   MIME: {mime_type}")
        
        # Проверяем в БД
        command = f"docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT id, file_name, mime_type, media_type_id, thumbnails_ro FROM media WHERE id = '{media_id}';\" 2>&1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        db_info = stdout.read().decode()
        
        if db_info.strip() and "id" in db_info.lower():
            print(f"   Данные из БД:")
            for line in db_info.split('\n'):
                if line.strip() and "id" not in line.lower() and "file_name" not in line.lower():
                    print(f"     {line}")
        
        # Проверяем media_type_id
        media_type_id = attrs.get("mediaTypeId")
        if media_type_id:
            print(f"   Media Type ID: {media_type_id}")
            
            # Проверяем, что это за тип
            command = f"docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT id, name FROM media_type WHERE id = '{media_type_id}';\" 2>&1"
            stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
            type_info = stdout.read().decode()
            
            if type_info.strip():
                print(f"   Media Type:")
                for line in type_info.split('\n'):
                    if line.strip() and "id" not in line.lower() and "name" not in line.lower():
                        print(f"     {line}")
        
        # Проверяем thumbnails_ro
        command = f"docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(*) as count FROM media_thumbnail WHERE media_id = '{media_id}';\" 2>&1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        thumb_count = stdout.read().decode()
        
        if thumb_count.strip() and "count" in thumb_count.lower():
            for line in thumb_count.split('\n'):
                if line.strip() and "count" not in line.lower() and line.strip().isdigit():
                    count = int(line.strip())
                    if count == 0:
                        print(f"   [WARNING] Нет thumbnails в БД (count={count})")
                    else:
                        print(f"   [OK] Есть thumbnails в БД (count={count})")
        
        # Проверяем, есть ли физический файл
        print(f"   Проверка физического файла...")
        url = attrs.get("url", "")
        if url:
            # Извлекаем путь из URL
            if "/media/" in url:
                path_part = url.split("/media/")[1].split("?")[0]
                # Shopware хранит файлы в public/media/
                print(f"     URL путь: {path_part}")
    
    # Сравниваем с медиа, у которых ЕСТЬ thumbnails
    print("\n2. Сравнение с медиа, у которых ЕСТЬ thumbnails...")
    command = "docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT m.id, m.file_name, m.mime_type, COUNT(mt.id) as thumb_count FROM media m LEFT JOIN media_thumbnail mt ON m.id = mt.media_id WHERE mt.id IS NOT NULL GROUP BY m.id LIMIT 3;\" 2>&1"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    working_media = stdout.read().decode()
    
    if working_media.strip():
        print("   Медиа с thumbnails:")
        for line in working_media.split('\n'):
            if line.strip() and "id" not in line.lower() and "file_name" not in line.lower():
                print(f"     {line}")
    
    ssh.close()
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)









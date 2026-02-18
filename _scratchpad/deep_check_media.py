"""
Глубокая проверка медиа - почему Shopware пропускает
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
print("ГЛУБОКАЯ ПРОВЕРКА: ПОЧЕМУ SHOPWARE ПРОПУСКАЕТ")
print("=" * 60)

# Получаем одно медиа для детального анализа
print("\n1. Получение тестового медиа...")
response = client._request("GET", "/api/media", params={"limit": 1})
media_list = response.get("data", []) if isinstance(response, dict) else []

if not media_list:
    print("   [ERROR] Нет медиа!")
    exit(1)

test_media = media_list[0]
media_id = test_media.get("id")
attrs = test_media.get("attributes", {})
file_name = attrs.get("fileName", "N/A")
mime_type = attrs.get("mimeType", "N/A")

print(f"   Медиа ID: {media_id}")
print(f"   File name: {file_name}")
print(f"   MIME type: {mime_type}")

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    
    # Проверяем ВСЕ поля медиа в БД
    print("\n2. Полная информация о медиа из БД...")
    command = f"docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT * FROM media WHERE id = '{media_id}'\\G\" 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    full_info = stdout.read().decode()
    
    if full_info.strip():
        print("   Все поля медиа:")
        for line in full_info.split('\n'):
            if line.strip():
                print(f"     {line}")
    
    # Проверяем media_type
    print("\n3. Проверка media_type...")
    media_type_id = attrs.get("mediaTypeId")
    if media_type_id:
        command = f"docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT * FROM media_type WHERE id = '{media_type_id}'\\G\" 2>&1 | grep -v Warning"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        type_info = stdout.read().decode()
        
        if type_info.strip():
            print("   Media type:")
            for line in type_info.split('\n'):
                if line.strip():
                    print(f"     {line}")
    
    # Проверяем физический файл
    print("\n4. Проверка физического файла...")
    url = attrs.get("url", "")
    if url and "/media/" in url:
        # Извлекаем путь
        path_part = url.split("/media/")[1].split("?")[0]
        file_path = f"/var/www/html/public/media/{path_part}"
        
        command = f"docker exec shopware ls -lh '{file_path}' 2>&1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        file_info = stdout.read().decode()
        
        if file_info.strip() and "No such file" not in file_info:
            print(f"   [OK] Файл существует:")
            print(f"     {file_info.strip()}")
        else:
            print(f"   [ERROR] Файл не найден: {file_path}")
            print(f"     {file_info.strip()}")
    
    # Сравниваем с медиа, у которого ЕСТЬ thumbnails
    print("\n5. Сравнение с рабочим медиа...")
    command = "docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT m.id, m.file_name, m.mime_type, m.media_type_id, COUNT(mt.id) as thumb_count FROM media m LEFT JOIN media_thumbnail mt ON m.id = mt.media_id WHERE mt.id IS NOT NULL GROUP BY m.id LIMIT 1\\G\" 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    working = stdout.read().decode()
    
    if working.strip():
        print("   Рабочее медиа (с thumbnails):")
        for line in working.split('\n'):
            if line.strip():
                print(f"     {line}")
    
    # Проверяем, может быть проблема в том, что нужно обновить uploadedAt
    print("\n6. Попытка обновления uploadedAt...")
    command = f"docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"UPDATE media SET uploaded_at = NOW() WHERE id = '{media_id}';\" 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    update_result = stdout.read().decode()
    
    if "ERROR" not in update_result:
        print("   [OK] uploadedAt обновлён")
        
        # Пробуем сгенерировать заново
        print("\n7. Генерация после обновления...")
        command = "docker exec shopware php bin/console media:generate-thumbnails 2>&1 | tail -10"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=300)
        gen_output = stdout.read().decode()
        
        if gen_output.strip():
            print("   Результат:")
            for line in gen_output.split('\n'):
                if line.strip():
                    print(f"     {line}")
    
    ssh.close()
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)









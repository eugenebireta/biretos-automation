"""
Исправление mediaType (хранится как JSON в longblob)
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
print("ИСПРАВЛЕНИЕ MEDIATYPE (JSON BLOB)")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    
    # Проверяем mediaType у рабочего медиа
    print("\n1. Проверка mediaType у рабочего медиа...")
    command = "docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT id, HEX(media_type) as media_type_hex FROM media WHERE media_type IS NOT NULL LIMIT 1;\" 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    working_media = stdout.read().decode()
    
    if working_media.strip():
        print("   Рабочее медиа (с mediaType):")
        for line in working_media.split('\n'):
            if line.strip() and "id" not in line.lower():
                print(f"     {line}")
    
    # Проверяем наше медиа
    print("\n2. Проверка нашего медиа...")
    response = client._request("GET", "/api/media", params={"limit": 1})
    media_list = response.get("data", []) if isinstance(response, dict) else []
    
    if media_list:
        test_media_id = media_list[0].get("id")
        command = f"docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT id, HEX(media_type) as media_type_hex FROM media WHERE id = '{test_media_id}';\" 2>&1 | grep -v Warning"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        our_media = stdout.read().decode()
        
        if our_media.strip():
            print("   Наше медиа:")
            for line in our_media.split('\n'):
                if line.strip() and "id" not in line.lower():
                    print(f"     {line}")
                    if "NULL" in line or len(line.strip()) < 20:
                        print("       [WARNING] media_type = NULL или пустой!")
    
    # Генерируем media types через команду
    print("\n3. Генерация media types...")
    command = "docker exec shopware php bin/console media:generate-media-types 2>&1"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=120)
    
    gen_output = stdout.read().decode()
    if "Finished" in gen_output or "completed" in gen_output.lower():
        print("   [OK] Media types сгенерированы")
    else:
        print("   Вывод:")
        for line in gen_output.split('\n')[-10:]:
            if line.strip():
                print(f"     {line}")
    
    # Проверяем результат
    print("\n4. Проверка mediaType после генерации...")
    if media_list:
        test_media_id = media_list[0].get("id")
        command = f"docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT id, HEX(media_type) as media_type_hex FROM media WHERE id = '{test_media_id}';\" 2>&1 | grep -v Warning"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        after_gen = stdout.read().decode()
        
        if after_gen.strip():
            print("   После генерации:")
            for line in after_gen.split('\n'):
                if line.strip() and "id" not in line.lower():
                    print(f"     {line}")
                    if "NULL" not in line and len(line.strip()) > 20:
                        print("       [OK] media_type установлен!")
    
    # Генерируем thumbnails
    print("\n5. Генерация thumbnails...")
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
    
    # Проверяем thumbnails
    if media_list:
        test_media_id = media_list[0].get("id")
        command = f"docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(*) as count FROM media_thumbnail WHERE media_id = '{test_media_id}';\" 2>&1 | grep -v Warning | tail -1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        count = stdout.read().decode().strip()
        print(f"   Thumbnails в БД: {count}")
        
        command = f"docker exec shopware find /var/www/html/public/media/thumbnail -name '*{test_media_id}*' 2>/dev/null | wc -l"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        disk_count = stdout.read().decode().strip()
        print(f"   Thumbnails на диске: {disk_count}")
    
    ssh.close()
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)









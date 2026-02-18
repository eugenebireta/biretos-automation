"""
Исправление mediaType через БД напрямую
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
print("ИСПРАВЛЕНИЕ MEDIATYPE ЧЕРЕЗ БД")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    
    # Находим mediaType для изображений через БД
    print("\n1. Поиск mediaType для изображений в БД...")
    command = "docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT id FROM media_type WHERE name LIKE '%image%' OR name LIKE '%Image%' LIMIT 1;\" 2>&1 | grep -v Warning | tail -1"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    image_type_id = stdout.read().decode().strip()
    
    if not image_type_id or "ERROR" in image_type_id:
        # Пробуем найти через другую таблицу или создать
        print("   MediaType не найден, генерируем...")
        command = "docker exec shopware php bin/console media:generate-media-types 2>&1 | tail -5"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
        gen_output = stdout.read().decode()
        
        # Пробуем найти снова
        command = "docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT id FROM media_type WHERE name LIKE '%image%' LIMIT 1;\" 2>&1 | grep -v Warning | tail -1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        image_type_id = stdout.read().decode().strip()
    
    if image_type_id and image_type_id and len(image_type_id) > 10:
        print(f"   [FOUND] MediaType ID: {image_type_id}")
    else:
        print("   [ERROR] MediaType не найден!")
        ssh.close()
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
                all_media.append(media.get("id"))
        
        page += 1
        if page > 10:
            break
    
    print(f"   Найдено изображений: {len(all_media)}")
    
    # Устанавливаем mediaType через БД
    print(f"\n3. Установка mediaType для {len(all_media)} изображений через БД...")
    updated = 0
    for media_id in all_media:
        command = f"docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"UPDATE media SET media_type_id = '{image_type_id}' WHERE id = '{media_id}';\" 2>&1 | grep -v Warning"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        result = stdout.read().decode()
        
        if "ERROR" not in result:
            updated += 1
            if updated % 10 == 0:
                print(f"   Обновлено: {updated}/{len(all_media)}")
    
    print(f"   [OK] Обновлено: {updated}")
    
    # Генерируем thumbnails
    print("\n4. Генерация thumbnails...")
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
    
    # Проверяем результат
    if all_media:
        test_media_id = all_media[0]
        command = f"docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(*) as count FROM media_thumbnail WHERE media_id = '{test_media_id}';\" 2>&1 | grep -v Warning | tail -1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        count = stdout.read().decode().strip()
        print(f"   Thumbnails в БД для тестового медиа: {count}")
        
        command = f"docker exec shopware find /var/www/html/public/media/thumbnail -name '*{test_media_id}*' 2>/dev/null | wc -l"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        disk_count = stdout.read().decode().strip()
        print(f"   Thumbnails на диске: {disk_count}")
    
    # Очищаем кеш
    print("\n5. Очистка кеша...")
    command = "docker exec shopware php bin/console cache:clear"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
    stdout.read()
    print("   [OK] Кеш очищен")
    
    ssh.close()
    
    print("\n" + "=" * 60)
    print("ИСПРАВЛЕНИЕ ЗАВЕРШЕНО")
    print("=" * 60)
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()









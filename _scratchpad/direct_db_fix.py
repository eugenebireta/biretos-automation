"""
Прямое исправление через БД - сброс состояния медиа
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
print("ПРЯМОЕ ИСПРАВЛЕНИЕ ЧЕРЕЗ БД")
print("=" * 60)

# Получаем изображения
print("\n1. Получение изображений...")
response = client._request("GET", "/api/media", params={"limit": 10})
media_list = response.get("data", []) if isinstance(response, dict) else []

image_media = []
for media in media_list:
    attrs = media.get("attributes", {})
    mime_type = attrs.get("mimeType") or ""
    if mime_type and mime_type.startswith("image/"):
        image_media.append(media)

print(f"   Найдено изображений: {len(image_media)}")

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    
    # Удаляем все thumbnails для наших медиа из БД
    print("\n2. Удаление thumbnails из БД...")
    for media in image_media:
        media_id = media.get("id")
        command = f"docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"DELETE FROM media_thumbnail WHERE media_id = '{media_id}';\" 2>&1 | grep -v Warning"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        stdout.read()  # Ждём завершения
    
    print("   [OK] Thumbnails удалены из БД")
    
    # Генерируем thumbnails заново
    print("\n3. Генерация thumbnails...")
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
    
    print(f"\n   Generated: {generated}")
    
    # Проверяем результат
    print("\n4. Проверка результата...")
    if image_media:
        test_media_id = image_media[0].get("id")
        command = f"docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(*) as count FROM media_thumbnail WHERE media_id = '{test_media_id}';\" 2>&1 | grep -v Warning | tail -1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        count = stdout.read().decode().strip()
        print(f"   Thumbnails для тестового медиа в БД: {count}")
        
        # Проверяем на диске
        command = f"docker exec shopware find /var/www/html/public/media/thumbnail -name '*{test_media_id}*' 2>/dev/null | wc -l"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        disk_count = stdout.read().decode().strip()
        print(f"   Thumbnails для тестового медиа на диске: {disk_count}")
    
    ssh.close()
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)









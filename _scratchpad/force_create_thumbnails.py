"""
Принудительное создание thumbnails через прямое обновление медиа
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
print("ПРИНУДИТЕЛЬНОЕ СОЗДАНИЕ THUMBNAILS")
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
    
    # Фильтруем только изображения
    for media in media_list:
        attrs = media.get("attributes", {})
        mime_type = attrs.get("mimeType") or ""
        if mime_type and mime_type.startswith("image/"):
            all_media.append(media)
    
    page += 1
    if page > 10:  # Ограничение
        break

print(f"   Найдено изображений: {len(all_media)}")

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    
    # Шаг 1: Удаляем записи thumbnails из БД для наших медиа (если есть)
    print("\n2. Очистка старых thumbnails из БД...")
    for media in all_media[:5]:  # Ограничиваем для теста
        media_id = media.get("id")
        command = f"docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"DELETE FROM media_thumbnail WHERE media_id = '{media_id}';\" 2>&1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        # Не выводим, чтобы не засорять вывод
    
    print("   [OK] Очистка завершена")
    
    # Шаг 2: Обновляем медиа через API, чтобы триггернуть обработку
    print("\n3. Обновление медиа через API...")
    updated = 0
    for media in all_media[:10]:  # Ограничиваем для теста
        media_id = media.get("id")
        attrs = media.get("attributes", {})
        
        try:
            # Обновляем медиа с небольшим изменением
            update_payload = {
                "id": media_id,
                "alt": attrs.get("alt") or attrs.get("fileName", "")
            }
            client._request("PATCH", f"/api/media/{media_id}", json=update_payload)
            updated += 1
        except Exception as e:
            print(f"   [ERROR] Ошибка обновления {media_id[:16]}...: {str(e)[:50]}")
    
    print(f"   Обновлено медиа: {updated}")
    
    # Шаг 3: Генерируем thumbnails
    print("\n4. Генерация thumbnails...")
    command = "docker exec shopware php bin/console media:generate-thumbnails -vv 2>&1"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=600)
    
    generated = 0
    skipped = 0
    
    print("   Прогресс:")
    for line in stdout:
        line_str = line.decode('utf-8', errors='ignore').strip()
        if line_str:
            print(f"     {line_str}")
            if "Generated" in line_str:
                try:
                    parts = line_str.split()
                    for i, part in enumerate(parts):
                        if part == "Generated" and i + 1 < len(parts):
                            generated = int(parts[i + 1])
                except:
                    pass
            if "Skipped" in line_str:
                try:
                    parts = line_str.split()
                    for i, part in enumerate(parts):
                        if part == "Skipped" and i + 1 < len(parts):
                            skipped = int(parts[i + 1])
                except:
                    pass
    
    print(f"\n   Результат: Generated={generated}, Skipped={skipped}")
    
    # Шаг 4: Проверяем результат на диске
    print("\n5. Проверка thumbnails на диске...")
    command = "docker exec shopware find /var/www/html/public/media/thumbnail -type f 2>/dev/null | wc -l"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    thumb_files = stdout.read().decode().strip()
    print(f"   Файлов thumbnails на диске: {thumb_files}")
    
    # Проверяем для конкретного медиа
    if all_media:
        test_media_id = all_media[0].get("id")
        command = f"docker exec shopware find /var/www/html/public/media/thumbnail -name '*{test_media_id}*' 2>/dev/null | head -5"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        test_thumbs = stdout.read().decode().strip()
        
        if test_thumbs:
            print(f"   Thumbnails для тестового медиа:")
            for line in test_thumbs.split('\n'):
                if line.strip():
                    print(f"     {line}")
        else:
            print(f"   [WARNING] Thumbnails для тестового медиа не найдены на диске")
    
    ssh.close()
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)


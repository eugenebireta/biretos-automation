"""
Принудительное исправление thumbnails - все возможные варианты.
"""
import sys
import paramiko
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
config = load_json(ROOT / "config.json")

shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

print("=" * 60)
print("ПРИНУДИТЕЛЬНОЕ ИСПРАВЛЕНИЕ THUMBNAILS")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=ssh_username, password=ssh_password, timeout=10)
    print(f"  [OK] Подключено к {host}")
    
    # Шаг 1: Получаем все медиа товаров
    print("\n1. Получение медиа товаров...")
    products_response = client._request("GET", "/api/product", params={"limit": 100})
    products = products_response.get("data", []) if isinstance(products_response, dict) else []
    
    media_ids = []
    for product in products:
        attrs = product.get("attributes", {})
        media = attrs.get("media", [])
        for m in media:
            media_id = m.get("mediaId") or m.get("id")
            if media_id:
                media_ids.append(media_id)
    
    media_ids = list(set(media_ids))  # Убираем дубликаты
    print(f"   Найдено уникальных медиа: {len(media_ids)}")
    
    # Шаг 2: Пробуем принудительно обновить каждое медиа через API
    print("\n2. Принудительное обновление медиа через API...")
    updated = 0
    for idx, media_id in enumerate(media_ids[:20]):  # Ограничиваем первыми 20 для теста
        try:
            # Получаем текущее медиа
            media_response = client._request("GET", f"/api/media/{media_id}")
            media_data = media_response.get("data", {}) if isinstance(media_response, dict) else {}
            media_attrs = media_data.get("attributes", {})
            
            # Обновляем медиа (даже без изменений, чтобы заставить Shopware пересоздать thumbnails)
            client._request("PATCH", f"/api/media/{media_id}", json={
                "id": media_id,
                "title": media_attrs.get("title", ""),  # Сохраняем текущее значение
            })
            updated += 1
            if (idx + 1) % 5 == 0:
                print(f"   Обновлено: {updated}/{idx + 1}")
            time.sleep(0.1)  # Небольшая задержка
        except Exception as e:
            error_msg = str(e)[:100]
            print(f"   [SKIP] {media_id[:16]}... - {error_msg}")
    
    print(f"\n   Итого обновлено медиа: {updated}")
    
    # Шаг 3: Запускаем генерацию thumbnails с принудительным флагом
    print("\n3. Запуск media:generate-thumbnails (принудительно)...")
    
    # Пробуем разные варианты команды
    commands_to_try = [
        "media:generate-thumbnails --all",
        "media:generate-thumbnails -vvv",
    ]
    
    for cmd in commands_to_try:
        print(f"\n   Пробуем: {cmd}")
        command = f"docker exec {container_name} php bin/console {cmd} 2>&1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=600)
        
        output_lines = []
        for line in stdout:
            try:
                line_str = line.decode('utf-8', errors='ignore').strip()
                if line_str:
                    output_lines.append(line_str)
                    if "Generated" in line_str or "Skipped" in line_str or "Error" in line_str or "generated" in line_str.lower():
                        print(f"      {line_str}")
            except:
                pass
        
        if output_lines:
            print(f"   ✅ Команда вывела результат ({len(output_lines)} строк)")
            # Показываем последние 10 строк
            for line in output_lines[-10:]:
                if line.strip():
                    print(f"      {line}")
            break
        else:
            print(f"   ⚠️  Команда не вывела результат")
    
    # Шаг 4: Проверяем thumbnails на диске
    print("\n4. Проверка thumbnails на диске...")
    command_check = f"docker exec {container_name} find /var/www/html/public/media -type d -name thumbnail -exec find {{}} -type f \\; 2>/dev/null | wc -l"
    stdin, stdout, stderr = ssh.exec_command(command_check, timeout=30)
    thumb_count = stdout.read().decode().strip()
    if thumb_count.isdigit():
        thumb_count_int = int(thumb_count)
        if thumb_count_int > 0:
            print(f"   ✅ Найдено {thumb_count_int} файлов thumbnails")
        else:
            print(f"   ⚠️  Thumbnails не найдены")
    
    # Шаг 5: Очищаем кеш и обновляем индексы
    print("\n5. Очистка кеша и обновление индексов...")
    commands = [
        ("cache:clear", "Очистка кеша"),
        ("dal:refresh:index", "Обновление индексов"),
    ]
    
    for cmd, desc in commands:
        command = f"docker exec {container_name} php bin/console {cmd}"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=120)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status == 0:
            print(f"   ✅ {desc} выполнена")
        else:
            print(f"   ⚠️  {desc} завершилась с ошибкой")
    
    ssh.close()
    
    print("\n" + "=" * 60)
    print("ИСПРАВЛЕНИЕ ЗАВЕРШЕНО")
    print("=" * 60)
    print("\n💡 Если thumbnails всё ещё не появились:")
    print("   1. Shopware может использовать оригинальные изображения для превьюшек")
    print("   2. Проверьте настройки темы в админке")
    print("   3. Возможно, нужно обновить шаблон каталога")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)








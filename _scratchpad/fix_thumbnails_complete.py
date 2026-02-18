"""
Полное исправление thumbnails: media types + генерация.
"""
import sys
import paramiko

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

print("=" * 60)
print("ПОЛНОЕ ИСПРАВЛЕНИЕ THUMBNAILS")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=ssh_username, password=ssh_password, timeout=10)
    print(f"  [OK] Подключено к {host}")
    
    # Шаг 1: Проверяем media_type
    print("\n1. Проверка media_type...")
    command_check = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(*) as total, SUM(CASE WHEN media_type IS NULL THEN 1 ELSE 0 END) as without_type FROM media WHERE mime_type LIKE 'image/%';\" 2>&1 | grep -v Warning | tail -1"
    stdin, stdout, stderr = ssh.exec_command(command_check, timeout=30)
    output = stdout.read().decode().strip()
    if output:
        parts = output.split('\t')
        if len(parts) >= 2:
            total = parts[0].strip()
            without_type = parts[1].strip()
            print(f"   Всего изображений: {total}")
            print(f"   Без media_type: {without_type}")
            if int(without_type) > 0:
                print("   ⚠️  Нужно запустить media:generate-media-types")
    
    # Шаг 2: Запускаем media:generate-media-types
    print("\n2. Запуск media:generate-media-types...")
    command_types = f"docker exec {container_name} php bin/console media:generate-media-types"
    stdin, stdout, stderr = ssh.exec_command(command_types, timeout=300)
    
    for line in stdout:
        try:
            line_str = line.decode('utf-8', errors='ignore').strip()
            if line_str:
                print(f"   {line_str}")
        except:
            pass
    
    exit_status = stdout.channel.recv_exit_status()
    if exit_status == 0:
        print("   ✅ media:generate-media-types выполнен")
    else:
        error = stderr.read().decode().strip()
        print(f"   ⚠️  Предупреждение: {error[:200]}")
    
    # Шаг 3: Запускаем media:generate-thumbnails
    print("\n3. Запуск media:generate-thumbnails...")
    command_thumbnails = f"docker exec {container_name} php bin/console media:generate-thumbnails"
    stdin, stdout, stderr = ssh.exec_command(command_thumbnails, timeout=600)
    
    generated = 0
    skipped = 0
    errors = 0
    
    output_lines = []
    for line in stdout:
        try:
            line_str = line.decode('utf-8', errors='ignore').strip()
            if line_str:
                output_lines.append(line_str)
                if "Generated:" in line_str or "Skipped:" in line_str or "Errors:" in line_str:
                    print(f"   {line_str}")
        except:
            pass
    
    # Парсим результат
    for line in output_lines:
        line_lower = line.lower()
        if "generated:" in line_lower:
            try:
                parts = line.split(":")
                if len(parts) >= 2:
                    generated = int(parts[1].strip().split()[0])
            except:
                pass
        if "skipped:" in line_lower:
            try:
                parts = line.split(":")
                if len(parts) >= 2:
                    skipped = int(parts[1].strip().split()[0])
            except:
                pass
        if "errors:" in line_lower:
            try:
                parts = line.split(":")
                if len(parts) >= 2:
                    errors = int(parts[1].strip().split()[0])
            except:
                pass
    
    print(f"\n   Статистика генерации:")
    print(f"     Generated: {generated}")
    print(f"     Skipped: {skipped}")
    print(f"     Errors: {errors}")
    
    # Шаг 4: Проверяем thumbnails на диске
    print("\n4. Проверка thumbnails на диске...")
    command_check = f"docker exec {container_name} find /var/www/html/public/media -type d -name thumbnail -exec find {{}} -type f \\; 2>/dev/null | wc -l"
    stdin, stdout, stderr = ssh.exec_command(command_check, timeout=30)
    thumb_count = stdout.read().decode().strip()
    if thumb_count.isdigit():
        thumb_count_int = int(thumb_count)
        if thumb_count_int > 0:
            print(f"   ✅ Найдено {thumb_count_int} файлов thumbnails на диске")
        else:
            print(f"   ⚠️  Thumbnails не найдены на диске")
    else:
        print(f"   ⚠️  Не удалось проверить количество thumbnails")
    
    # Шаг 5: Очищаем кеш
    print("\n5. Очистка кеша...")
    command_cache = f"docker exec {container_name} php bin/console cache:clear"
    stdin, stdout, stderr = ssh.exec_command(command_cache, timeout=60)
    exit_status = stdout.channel.recv_exit_status()
    if exit_status == 0:
        print("   ✅ Кеш очищен")
    else:
        print("   ⚠️  Предупреждение при очистке кеша")
    
    ssh.close()
    
    print("\n" + "=" * 60)
    print("ИСПРАВЛЕНИЕ THUMBNAILS ЗАВЕРШЕНО")
    print("=" * 60)
    
    if generated > 0:
        print("\n✅ Thumbnails успешно сгенерированы!")
        print("Проверьте каталог на сайте - превьюшки должны появиться.")
    elif skipped > 0:
        print("\n⚠️  Thumbnails пропущены. Возможные причины:")
        print("   - Медиа не привязаны к товарам")
        print("   - Thumbnail sizes не настроены правильно")
        print("   - Медиа не являются изображениями")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)








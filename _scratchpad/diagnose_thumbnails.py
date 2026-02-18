"""
Диагностика проблемы с thumbnails.
"""
import sys
from pathlib import Path
import paramiko

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

print("=" * 60)
print("ДИАГНОСТИКА THUMBNAILS")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=ssh_username, password=ssh_password, timeout=10)
    print(f"  [OK] Подключено к {host}")
    
    # 1. Проверка thumbnail sizes
    print("\n1. Проверка thumbnail sizes в БД:")
    command1 = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e 'SELECT width, height FROM thumbnail_size ORDER BY width, height;' 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command1, timeout=30)
    output1 = stdout.read().decode().strip()
    if output1:
        lines = output1.split('\n')
        print(f"   Найдено размеров: {len(lines) - 1}")
        for line in lines[1:]:  # Пропускаем заголовок
            if line.strip():
                print(f"   - {line.strip()}")
    else:
        print("   ❌ Thumbnail sizes не найдены!")
    
    # 2. Проверка media_type
    print("\n2. Проверка media_type:")
    command2 = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e 'SELECT COUNT(*) as total, SUM(CASE WHEN media_type IS NULL THEN 1 ELSE 0 END) as without_type FROM media;' 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command2, timeout=30)
    output2 = stdout.read().decode().strip()
    if output2:
        lines = output2.split('\n')
        if len(lines) >= 2:
            parts = lines[1].split('\t')
            if len(parts) >= 2:
                total = parts[0].strip()
                without_type = parts[1].strip()
                print(f"   Всего медиа: {total}")
                print(f"   Без media_type: {without_type}")
                if int(without_type) > 0:
                    print(f"   ⚠️  Нужно запустить: media:generate-media-types")
    
    # 3. Проверка медиа товаров
    print("\n3. Проверка медиа товаров:")
    command3 = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(*) FROM product_media pm JOIN media m ON pm.media_id = m.id WHERE m.media_type IS NULL;\" 2>&1 | grep -v Warning | tail -1"
    stdin, stdout, stderr = ssh.exec_command(command3, timeout=30)
    output3 = stdout.read().decode().strip()
    if output3:
        print(f"   Медиа товаров без media_type: {output3}")
    
    # 4. Запуск media:generate-thumbnails с подробным выводом
    print("\n4. Запуск media:generate-thumbnails (verbose):")
    print("   Команда: media:generate-thumbnails -v")
    command4 = f"docker exec {container_name} php bin/console media:generate-thumbnails -v"
    stdin, stdout, stderr = ssh.exec_command(command4, timeout=300)
    
    output_lines = []
    for line in stdout:
        try:
            line_str = line.decode('utf-8', errors='ignore').strip()
            if line_str:
                output_lines.append(line_str)
                print(f"   {line_str}")
        except:
            pass
    
    # Парсим результат
    generated = 0
    skipped = 0
    errors = 0
    
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
    
    print(f"\n   Статистика:")
    print(f"     Generated: {generated}")
    print(f"     Skipped: {skipped}")
    print(f"     Errors: {errors}")
    
    if skipped > 0:
        print(f"\n   ⚠️  {skipped} медиа пропущено")
        print(f"   Возможные причины:")
        print(f"     - Thumbnail sizes не настроены")
        print(f"     - media_type не инициализирован")
        print(f"     - Медиа не привязано к товарам")
    
    # 5. Проверка thumbnails на диске
    print("\n5. Проверка thumbnails на диске:")
    command5 = f"docker exec {container_name} find /var/www/html/public/media -type d -name thumbnail -exec find {{}} -type f \\; 2>/dev/null | wc -l"
    stdin, stdout, stderr = ssh.exec_command(command5, timeout=30)
    thumb_count = stdout.read().decode().strip()
    if thumb_count.isdigit():
        thumb_count_int = int(thumb_count)
        if thumb_count_int > 0:
            print(f"   ✅ Найдено {thumb_count_int} файлов thumbnails на диске")
        else:
            print(f"   ❌ Thumbnails не найдены на диске")
    else:
        print(f"   ⚠️  Не удалось проверить количество thumbnails")
    
    ssh.close()
    
    print("\n" + "=" * 60)
    print("ДИАГНОСТИКА ЗАВЕРШЕНА")
    print("=" * 60)
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)









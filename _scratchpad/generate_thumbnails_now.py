"""
Генерация thumbnails для всех медиа.
"""
import sys
import paramiko

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

print("=" * 60)
print("ГЕНЕРАЦИЯ THUMBNAILS")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=ssh_username, password=ssh_password, timeout=10)
    print(f"  [OK] Подключено к {host}")
    
    # Запускаем генерацию thumbnails
    print("\nЗапуск media:generate-thumbnails...")
    command = f"docker exec {container_name} php bin/console media:generate-thumbnails -v"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=600)
    
    generated = 0
    skipped = 0
    errors = 0
    
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
    
    # Проверяем thumbnails на диске
    print("\nПроверка thumbnails на диске...")
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
    
    ssh.close()
    
    print("\n" + "=" * 60)
    print("ГЕНЕРАЦИЯ THUMBNAILS ЗАВЕРШЕНА")
    print("=" * 60)
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)








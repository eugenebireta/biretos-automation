"""
Принудительный reset состояния media и генерация thumbnails
"""
import paramiko

host = "77.233.222.214"
username = "root"
password = "HuPtNj39"

print("=" * 60)
print("ПРИНУДИТЕЛЬНЫЙ RESET И ГЕНЕРАЦИЯ THUMBNAILS")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    print("[OK] Подключено")
    
    container_name = "shopware"
    
    # Шаг 1: Удаляем локальные thumbnails (если есть)
    print("\n1. Удаление локальных thumbnails...")
    command = "docker exec shopware php bin/console media:delete-local-thumbnails"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
    
    output = stdout.read().decode()
    errors = stderr.read().decode()
    
    if output:
        print("   Вывод:")
        for line in output.split('\n'):
            if line.strip():
                print(f"     {line}")
    
    if errors and "error" not in errors.lower() and "only supported when remote" not in errors.lower():
        print(f"   Предупреждения: {errors[:200]}")
    
    # Шаг 2: Генерируем media types (если нужно)
    print("\n2. Генерация media types...")
    command = "docker exec shopware php bin/console media:generate-media-types"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
    
    output = stdout.read().decode()
    if output:
        print("   Вывод:")
        for line in output.split('\n')[:10]:
            if line.strip():
                print(f"     {line}")
    
    # Шаг 3: Генерируем thumbnails с --strict (проверяет физические файлы)
    print("\n3. Генерация thumbnails с --strict...")
    print("   Это может занять несколько минут...")
    command = "docker exec shopware php bin/console media:generate-thumbnails --strict -vv"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=600)
    
    generated_count = 0
    skipped_count = 0
    error_count = 0
    
    print("   Прогресс:")
    for line in stdout:
        line = line.strip()
        if line:
            print(f"     {line}")
            if "Generated" in line:
                try:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "Generated" and i + 1 < len(parts):
                            generated_count = int(parts[i + 1])
                except:
                    pass
            if "Skipped" in line:
                try:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "Skipped" and i + 1 < len(parts):
                            skipped_count = int(parts[i + 1])
                except:
                    pass
            if "Errors" in line:
                try:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "Errors" and i + 1 < len(parts):
                            error_count = int(parts[i + 1])
                except:
                    pass
    
    exit_status = stdout.channel.recv_exit_status()
    
    print(f"\n   Результат:")
    print(f"     Generated: {generated_count}")
    print(f"     Skipped: {skipped_count}")
    print(f"     Errors: {error_count}")
    print(f"     Exit code: {exit_status}")
    
    if generated_count > 0:
        print(f"\n   [SUCCESS] Thumbnails успешно сгенерированы!")
    elif skipped_count > 0 and generated_count == 0:
        print(f"\n   [WARNING] Все медиа пропущены. Проверяем причины...")
        
        # Если всё ещё пропускаются, пробуем без --strict
        print("\n4. Попытка генерации без --strict...")
        command = "docker exec shopware php bin/console media:generate-thumbnails -vv"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=300)
        
        for line in stdout:
            line = line.strip()
            if line and ("Generated" in line or "Skipped" in line or "Error" in line or "Processing" in line):
                print(f"     {line}")
    
    # Очищаем кеш
    print("\n5. Очистка кеша...")
    command = "docker exec shopware php bin/console cache:clear"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
    stdout.read()
    print("   [OK] Кеш очищен")
    
    ssh.close()
    
    print("\n" + "=" * 60)
    print("RESET ЗАВЕРШЁН")
    print("=" * 60)
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()









"""
Финальное исправление thumbnails - проверка всех вариантов.
"""
import sys
import paramiko

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

print("=" * 60)
print("ФИНАЛЬНОЕ ИСПРАВЛЕНИЕ THUMBNAILS")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=ssh_username, password=ssh_password, timeout=10)
    print(f"  [OK] Подключено к {host}")
    
    # Проверяем, есть ли команда media:thumbnail:generate
    print("\n1. Проверка доступных команд для thumbnails...")
    command_list = f"docker exec {container_name} php bin/console list media 2>&1 | grep -i thumbnail"
    stdin, stdout, stderr = ssh.exec_command(command_list, timeout=30)
    output = stdout.read().decode().strip()
    if output:
        print("   Доступные команды:")
        for line in output.split('\n'):
            if line.strip():
                print(f"   - {line.strip()}")
    else:
        print("   Команды не найдены в списке")
    
    # Пробуем запустить media:generate-thumbnails с разными опциями
    print("\n2. Запуск media:generate-thumbnails (без опций)...")
    command = f"docker exec {container_name} php bin/console media:generate-thumbnails 2>&1"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=600)
    
    # Читаем весь вывод
    all_output = []
    for line in stdout:
        try:
            line_str = line.decode('utf-8', errors='ignore').strip()
            if line_str:
                all_output.append(line_str)
        except:
            pass
    
    # Также читаем stderr
    for line in stderr:
        try:
            line_str = line.decode('utf-8', errors='ignore').strip()
            if line_str:
                all_output.append(f"[stderr] {line_str}")
        except:
            pass
    
    if all_output:
        print("   Вывод команды:")
        for line in all_output[:20]:  # Показываем первые 20 строк
            print(f"   {line}")
    else:
        print("   ⚠️  Команда не вывела ничего")
        print("   Возможно, thumbnails генерируются асинхронно или уже сгенерированы")
    
    exit_status = stdout.channel.recv_exit_status()
    print(f"\n   Exit status: {exit_status}")
    
    # Проверяем thumbnails на диске более детально
    print("\n3. Детальная проверка thumbnails на диске...")
    command_check = f"docker exec {container_name} find /var/www/html/public/media -type d -name thumbnail 2>/dev/null | head -5"
    stdin, stdout, stderr = ssh.exec_command(command_check, timeout=30)
    dirs = stdout.read().decode().strip()
    if dirs:
        print("   Найдены директории thumbnail:")
        for line in dirs.split('\n'):
            if line.strip():
                print(f"   - {line.strip()}")
        
        # Проверяем файлы в первой директории
        first_dir = dirs.split('\n')[0].strip()
        if first_dir:
            command_files = f"docker exec {container_name} ls -la {first_dir} 2>/dev/null | head -10"
            stdin, stdout, stderr = ssh.exec_command(command_files, timeout=30)
            files = stdout.read().decode().strip()
            if files:
                print(f"\n   Файлы в {first_dir}:")
                for line in files.split('\n'):
                    if line.strip():
                        print(f"   {line.strip()}")
    else:
        print("   ⚠️  Директории thumbnail не найдены")
    
    # Проверяем общее количество thumbnails
    command_count = f"docker exec {container_name} find /var/www/html/public/media -type d -name thumbnail -exec find {{}} -type f \\; 2>/dev/null | wc -l"
    stdin, stdout, stderr = ssh.exec_command(command_count, timeout=30)
    thumb_count = stdout.read().decode().strip()
    if thumb_count.isdigit():
        thumb_count_int = int(thumb_count)
        print(f"\n   Всего файлов thumbnails: {thumb_count_int}")
    
    # Очищаем кеш
    print("\n4. Очистка кеша...")
    command_cache = f"docker exec {container_name} php bin/console cache:clear"
    stdin, stdout, stderr = ssh.exec_command(command_cache, timeout=60)
    exit_status = stdout.channel.recv_exit_status()
    if exit_status == 0:
        print("   ✅ Кеш очищен")
    
    ssh.close()
    
    print("\n" + "=" * 60)
    print("ПРОВЕРКА ЗАВЕРШЕНА")
    print("=" * 60)
    print("\n💡 ВАЖНО:")
    print("   Shopware может использовать оригинальные изображения для превьюшек")
    print("   в каталоге, если thumbnails не настроены или не генерируются.")
    print("   Проверьте настройки темы/шаблона в админке Shopware.")
    print("   Также убедитесь, что у товаров установлен cover image.")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

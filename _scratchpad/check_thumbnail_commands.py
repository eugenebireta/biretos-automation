"""
Проверка доступных команд для работы с thumbnail sizes
"""
import paramiko

host = "77.233.222.214"
username = "root"
password = "HuPtNj39"

print("=" * 60)
print("ПРОВЕРКА КОМАНД ДЛЯ THUMBNAIL SIZES")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    print("[OK] Подключено")
    
    container_name = "shopware"
    
    # Ищем все команды связанные с thumbnail
    print("\n1. Поиск команд для thumbnail...")
    command = "docker exec shopware php bin/console list | grep -i thumbnail"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    output = stdout.read().decode()
    
    if output:
        print("   Найденные команды:")
        for line in output.split('\n'):
            if line.strip():
                print(f"     {line}")
    else:
        print("   Команды не найдены через grep, пробуем другой способ...")
    
    # Пробуем получить список всех команд media
    print("\n2. Список всех команд media...")
    command = "docker exec shopware php bin/console list media"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    output = stdout.read().decode()
    
    if output:
        print("   Команды media:")
        for line in output.split('\n'):
            if "thumbnail" in line.lower() or "size" in line.lower():
                print(f"     {line}")
    
    # Проверяем, может быть нужно создать через API или SQL
    print("\n3. Проверка существующих thumbnail sizes через SQL...")
    command = "docker exec shopware mysql -u shopware -pshopware shopware -e 'SELECT * FROM media_thumbnail_size LIMIT 10;'"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    output = stdout.read().decode()
    errors = stderr.read().decode()
    
    if output:
        print("   Существующие thumbnail sizes:")
        for line in output.split('\n'):
            if line.strip():
                print(f"     {line}")
    elif errors:
        print(f"   Ошибка SQL: {errors[:200]}")
        # Пробуем без пароля (может быть другой способ подключения)
        print("\n4. Альтернативный способ - через docker exec mysql...")
        command = "docker exec shopware bash -c 'mysql -u root -proot shopware -e \"SELECT id, width, height FROM media_thumbnail_size;\"'"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        output = stdout.read().decode()
        if output:
            print("   Thumbnail sizes:")
            for line in output.split('\n'):
                if line.strip():
                    print(f"     {line}")
    
    ssh.close()
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)









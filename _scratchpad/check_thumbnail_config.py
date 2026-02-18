"""
Проверка конфигурации thumbnail в Shopware
"""
import paramiko

host = "77.233.222.214"
username = "root"
password = "HuPtNj39"

print("=" * 60)
print("ПРОВЕРКА КОНФИГУРАЦИИ THUMBNAIL")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    print("[OK] Подключено")
    
    container_name = "shopware"
    
    # Проверяем настройки thumbnail
    print("\n1. Проверка настроек thumbnail sizes...")
    command = "docker exec shopware php bin/console system:config:get core.media.thumbnailSize"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    config_output = stdout.read().decode()
    if config_output:
        print("   Настройки thumbnail sizes:")
        for line in config_output.split('\n'):
            if line.strip():
                print(f"     {line}")
    else:
        print("   Настройки не найдены или пусты")
    
    # Проверяем список доступных thumbnail sizes
    print("\n2. Список доступных thumbnail sizes...")
    command = "docker exec shopware php bin/console media:thumbnail:generate --help"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    help_output = stdout.read().decode()
    if help_output:
        print("   Доступные опции:")
        for line in help_output.split('\n')[:15]:
            if line.strip():
                print(f"     {line}")
    
    # Пробуем сгенерировать для всех медиа с verbose
    print("\n3. Генерация thumbnails с verbose выводом...")
    command = "docker exec shopware php bin/console media:generate-thumbnails -v"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=300)
    
    print("   Вывод:")
    for line in stdout:
        line = line.strip()
        if line:
            print(f"     {line}")
    
    errors = stderr.read().decode()
    if errors:
        print("\n   Ошибки:")
        for line in errors.split('\n')[:10]:
            if line.strip():
                print(f"     {line}")
    
    exit_status = stdout.channel.recv_exit_status()
    print(f"\n   Код выхода: {exit_status}")
    
    ssh.close()
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)


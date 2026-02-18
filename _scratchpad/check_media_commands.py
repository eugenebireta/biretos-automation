"""
Проверка доступных команд для работы с media
"""
import paramiko

host = "77.233.222.214"
username = "root"
password = "HuPtNj39"

print("=" * 60)
print("ПРОВЕРКА ДОСТУПНЫХ КОМАНД ДЛЯ MEDIA")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    print("[OK] Подключено")
    
    container_name = "shopware"
    
    # Проверяем все команды media
    print("\n1. Список всех команд media...")
    command = "docker exec shopware php bin/console list media"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    output = stdout.read().decode()
    
    if output:
        print("   Доступные команды:")
        for line in output.split('\n'):
            if 'media:' in line.lower() or 'thumbnail' in line.lower():
                print(f"     {line.strip()}")
    
    # Проверяем help для media:generate-thumbnails
    print("\n2. Help для media:generate-thumbnails...")
    command = "docker exec shopware php bin/console media:generate-thumbnails --help"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    help_output = stdout.read().decode()
    
    if help_output:
        print("   Опции команды:")
        for line in help_output.split('\n'):
            if line.strip() and ('--' in line or 'option' in line.lower() or 'force' in line.lower()):
                print(f"     {line.strip()}")
    
    # Проверяем media:delete-thumbnails
    print("\n3. Проверка media:delete-thumbnails...")
    command = "docker exec shopware php bin/console media:delete-thumbnails --help"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    delete_help = stdout.read().decode()
    
    if delete_help:
        print("   Опции:")
        for line in delete_help.split('\n')[:10]:
            if line.strip():
                print(f"     {line.strip()}")
    else:
        print("   Команда не найдена или не имеет help")
    
    # Проверяем media:validate
    print("\n4. Проверка media:validate...")
    command = "docker exec shopware php bin/console media:validate --help 2>&1"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    validate_help = stdout.read().decode()
    
    if validate_help and "validate" in validate_help.lower():
        print("   Команда найдена")
        for line in validate_help.split('\n')[:10]:
            if line.strip():
                print(f"     {line.strip()}")
    else:
        print("   Команда не найдена")
    
    ssh.close()
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)









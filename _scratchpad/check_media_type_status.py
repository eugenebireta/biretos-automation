"""Проверка статуса media_type для медиа"""
import paramiko
import sys

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

print("=" * 60)
print("ПРОВЕРКА СТАТУСА media_type")
print("=" * 60)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=ssh_username, password=ssh_password, timeout=30)

# Проверяем media_type
print("\n1. Проверка media_type в базе данных...")
try:
    command = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT id, file_name, mime_type, media_type IS NULL as has_null_type FROM media WHERE mime_type LIKE 'image/%' LIMIT 10;\" 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    
    output = stdout.read().decode()
    errors = stderr.read().decode()
    
    if output:
        print("   Результаты:")
        for line in output.strip().split('\n'):
            if line and not line.startswith('id'):
                print(f"   {line}")
    else:
        print("   ⚠️ Нет результатов")
    
    if errors and "Warning" not in errors:
        print(f"   [ERROR] {errors}")
        
except Exception as e:
    print(f"   ❌ Ошибка: {e}")

# Проверяем количество медиа с NULL media_type
print("\n2. Подсчёт медиа с NULL media_type...")
try:
    command = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(*) as count FROM media WHERE media_type IS NULL AND mime_type LIKE 'image/%';\" 2>&1 | grep -v Warning | tail -1"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    output = stdout.read().decode().strip()
    
    if output and output.isdigit():
        count = int(output)
        print(f"   Медиа с NULL media_type: {count}")
        if count > 0:
            print(f"   ⚠️ Нужно запустить: media:generate-media-types")
        else:
            print(f"   ✅ Все медиа имеют media_type")
    else:
        print(f"   ⚠️ Не удалось получить количество")
        
except Exception as e:
    print(f"   ❌ Ошибка: {e}")

# Проверяем thumbnail sizes
print("\n3. Проверка настроек thumbnail sizes...")
try:
    command = f"docker exec {container_name} php bin/console media:thumbnail:size:list 2>&1"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    
    output = stdout.read().decode()
    errors = stderr.read().decode()
    
    if output:
        print("   Настройки thumbnail sizes:")
        for line in output.strip().split('\n')[:20]:  # Первые 20 строк
            if line:
                print(f"   {line}")
    else:
        print("   ⚠️ Нет настроек или ошибка")
    
    if errors and "Warning" not in errors:
        print(f"   [ERROR] {errors}")
        
except Exception as e:
    print(f"   ❌ Ошибка: {e}")

ssh.close()

print("\n" + "=" * 60)









"""Диагностика пропуска thumbnails"""
import paramiko
import sys

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

print("=" * 60)
print("ДИАГНОСТИКА ПРОПУСКА THUMBNAILS")
print("=" * 60)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=ssh_username, password=ssh_password, timeout=30)

# Проверяем thumbnail sizes через БД
print("\n1. Проверка thumbnail sizes в базе данных...")
try:
    command = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT id, width, height FROM thumbnail_size LIMIT 10;\" 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    
    output = stdout.read().decode()
    
    if output and output.strip():
        print("   Найденные thumbnail sizes:")
        for line in output.strip().split('\n'):
            if line and not line.startswith('id'):
                parts = line.split('\t')
                if len(parts) >= 3:
                    print(f"   ID: {parts[0]}, Размер: {parts[1]}x{parts[2]}")
    else:
        print("   ⚠️ Thumbnail sizes не найдены или таблица пуста")
        
except Exception as e:
    print(f"   ❌ Ошибка: {e}")

# Проверяем детали одного медиа
print("\n2. Проверка деталей медиа...")
try:
    command = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT id, file_name, mime_type, file_extension, file_size, media_type IS NOT NULL as has_type FROM media WHERE mime_type LIKE 'image/%' LIMIT 3;\" 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    
    output = stdout.read().decode()
    
    if output and output.strip():
        print("   Детали медиа:")
        for line in output.strip().split('\n'):
            if line and not line.startswith('id'):
                print(f"   {line}")
    else:
        print("   ⚠️ Медиа не найдены")
        
except Exception as e:
    print(f"   ❌ Ошибка: {e}")

# Пробуем запустить с verbose режимом
print("\n3. Запуск генерации с подробным выводом...")
try:
    command = f"docker exec {container_name} php bin/console media:generate-thumbnails -vvv 2>&1 | head -50"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
    
    output = stdout.read().decode()
    errors = stderr.read().decode()
    
    if output:
        print("   Вывод команды:")
        for line in output.strip().split('\n')[:30]:
            if line:
                print(f"   {line}")
    
    if errors:
        print("   Ошибки:")
        for line in errors.strip().split('\n')[:20]:
            if line:
                print(f"   [ERROR] {line}")
        
except Exception as e:
    print(f"   ❌ Ошибка: {e}")

# Проверяем, есть ли уже thumbnails
print("\n4. Проверка существующих thumbnails...")
try:
    command = f"docker exec {container_name} find public/media -name '*.jpg' -o -name '*.png' 2>/dev/null | grep thumbnail | head -5"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    
    thumbnails = []
    for line in stdout:
        line = line.rstrip()
        if line:
            thumbnails.append(line)
    
    if thumbnails:
        print(f"   ✅ Найдено {len(thumbnails)} thumbnail файлов:")
        for thumb in thumbnails[:5]:
            print(f"   {thumb}")
    else:
        print("   ⚠️ Thumbnail файлы не найдены")
        
except Exception as e:
    print(f"   ⚠️ Ошибка проверки: {e}")

ssh.close()

print("\n" + "=" * 60)









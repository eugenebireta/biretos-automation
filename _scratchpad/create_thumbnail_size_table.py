"""Создание таблицы thumbnail_size с правильной структурой Shopware"""
import paramiko

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

print("=" * 60)
print("СОЗДАНИЕ ТАБЛИЦЫ thumbnail_size")
print("=" * 60)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=ssh_username, password=ssh_password, timeout=30)

# Проверяем структуру других таблиц Shopware для понимания формата
print("\n1. Проверка структуры таблиц Shopware...")
try:
    # Проверяем структуру media таблицы как образец
    command_media = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"DESCRIBE media;\" 2>&1 | grep -v Warning | head -5"
    stdin_media, stdout_media, stderr_media = ssh.exec_command(command_media, timeout=30)
    output_media = stdout_media.read().decode()
    
    # Создаём таблицу thumbnail_size с правильной структурой Shopware
    # Shopware использует BINARY(16) для UUID, DATETIME для дат
    # Используем однострочный SQL
    create_table_sql = "CREATE TABLE IF NOT EXISTS `thumbnail_size` (`id` BINARY(16) NOT NULL, `width` INT(11) NOT NULL, `height` INT(11) NOT NULL, `created_at` DATETIME(3) NOT NULL, `updated_at` DATETIME(3) NULL, PRIMARY KEY (`id`), UNIQUE KEY `uniq.thumbnail_size.width_height` (`width`, `height`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"
    
    print("\n2. Создание таблицы thumbnail_size...")
    command_create = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"{create_table_sql}\" 2>&1 | grep -v Warning"
    stdin_create, stdout_create, stderr_create = ssh.exec_command(command_create, timeout=30)
    output_create = stdout_create.read().decode()
    errors_create = stderr_create.read().decode()
    
    if "ERROR" not in output_create and "ERROR" not in errors_create:
        print("   ✅ Таблица создана")
    else:
        print(f"   ⚠️ Ошибка или таблица уже существует: {output_create[:100]}")
        
except Exception as e:
    print(f"   ❌ Ошибка: {e}")

# Теперь создаём thumbnail sizes
print("\n3. Создание thumbnail sizes...")
import uuid
from datetime import datetime

thumbnail_sizes = [
    {"width": 192, "height": 192},
    {"width": 400, "height": 400},
    {"width": 800, "height": 800},
    {"width": 1920, "height": 1920},
]

created = 0
for size in thumbnail_sizes:
    width = size["width"]
    height = size["height"]
    
    # Проверяем, существует ли
    command_check = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(*) FROM thumbnail_size WHERE width={width} AND height={height};\" 2>&1 | grep -v Warning | tail -1"
    stdin_check, stdout_check, stderr_check = ssh.exec_command(command_check, timeout=30)
    output_check = stdout_check.read().decode().strip()
    
    if output_check and output_check.isdigit() and int(output_check) > 0:
        print(f"   [SKIP] Размер {width}x{height} уже существует")
    else:
        # Генерируем UUID и конвертируем в BINARY(16)
        size_uuid = uuid.uuid4()
        size_id_hex = size_uuid.hex
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # Миллисекунды
        
        # Вставляем с UNHEX для BINARY(16)
        sql = f"INSERT INTO thumbnail_size (id, width, height, created_at, updated_at) VALUES (UNHEX('{size_id_hex}'), {width}, {height}, '{now}', '{now}');"
        command_sql = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"{sql}\" 2>&1 | grep -v Warning"
        stdin_sql, stdout_sql, stderr_sql = ssh.exec_command(command_sql, timeout=30)
        output_sql = stdout_sql.read().decode()
        errors_sql = stderr_sql.read().decode()
        
        if "ERROR" not in output_sql and "ERROR" not in errors_sql:
            print(f"   ✅ Создан размер: {width}x{height}")
            created += 1
        else:
            print(f"   ❌ Ошибка создания {width}x{height}: {output_sql[:150]}")

print(f"\n   Итого создано: {created} из {len(thumbnail_sizes)}")

# Проверяем результат
print("\n4. Проверка созданных размеров...")
try:
    command_list = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT width, height FROM thumbnail_size ORDER BY width, height;\" 2>&1 | grep -v Warning"
    stdin_list, stdout_list, stderr_list = ssh.exec_command(command_list, timeout=30)
    output_list = stdout_list.read().decode()
    
    if output_list:
        sizes = [line for line in output_list.strip().split('\n') if line and not line.startswith('width')]
        print(f"   ✅ Найдено размеров: {len(sizes)}")
        for line in sizes:
            parts = line.split('\t')
            if len(parts) >= 2:
                print(f"     {parts[0]}x{parts[1]}")
except Exception as e:
    print(f"   ⚠️ Ошибка проверки: {e}")

ssh.close()

print("\n" + "=" * 60)
print("СОЗДАНИЕ ЗАВЕРШЕНО")
print("=" * 60)


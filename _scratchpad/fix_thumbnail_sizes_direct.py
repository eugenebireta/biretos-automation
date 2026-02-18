"""
Создание thumbnail sizes напрямую через SQL.
"""
import sys
from pathlib import Path
import paramiko
import uuid
from datetime import datetime

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

print("=" * 60)
print("СОЗДАНИЕ THUMBNAIL SIZES (ПРЯМОЙ SQL)")
print("=" * 60)

thumbnail_sizes = [
    (192, 192),
    (400, 400),
    (800, 800),
    (1920, 1920),
]

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=ssh_username, password=ssh_password, timeout=10)
    print(f"  [OK] Подключено к {host}")
    
    # Создаём таблицу одной командой
    print("\n1. Создание таблицы thumbnail_size:")
    create_table_sql = "CREATE TABLE IF NOT EXISTS `thumbnail_size` (`id` BINARY(16) NOT NULL, `width` INT(11) NOT NULL, `height` INT(11) NOT NULL, `created_at` DATETIME(3) NOT NULL, `updated_at` DATETIME(3) NULL DEFAULT NULL, PRIMARY KEY (`id`), UNIQUE KEY `uniq.thumbnail_size.width_height` (`width`, `height`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"
    
    command_create = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"{create_table_sql}\" 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command_create, timeout=30)
    exit_status = stdout.channel.recv_exit_status()
    
    if exit_status == 0:
        print("   ✅ Таблица создана/проверена")
    else:
        error = stderr.read().decode().strip()
        print(f"   ⚠️  Предупреждение: {error[:200]}")
    
    # Создаём thumbnail sizes
    print(f"\n2. Создание {len(thumbnail_sizes)} thumbnail sizes:")
    created = 0
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S.000')
    
    for width, height in thumbnail_sizes:
        # Генерируем UUID для ID
        size_id = uuid.uuid4()
        size_id_hex = size_id.hex
        
        # Проверяем, существует ли уже такой размер
        command_check = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(*) FROM thumbnail_size WHERE width={width} AND height={height};\" 2>&1 | grep -v Warning | tail -1"
        stdin, stdout, stderr = ssh.exec_command(command_check, timeout=30)
        count_output = stdout.read().decode().strip()
        
        if count_output.isdigit() and int(count_output) > 0:
            print(f"   [SKIP] {width}x{height} - уже существует")
            continue
        
        # Создаём размер
        sql = f"INSERT INTO thumbnail_size (id, width, height, created_at, updated_at) VALUES (UNHEX('{size_id_hex}'), {width}, {height}, '{now}', '{now}');"
        
        command_insert = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"{sql}\" 2>&1 | grep -v Warning"
        stdin, stdout, stderr = ssh.exec_command(command_insert, timeout=30)
        exit_status = stdout.channel.recv_exit_status()
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        
        if exit_status == 0 and not error:
            print(f"   ✅ {width}x{height} - создан")
            created += 1
        else:
            if "Duplicate entry" in error:
                print(f"   [SKIP] {width}x{height} - уже существует")
            else:
                print(f"   ❌ {width}x{height} - ошибка: {error[:100]}")
    
    print(f"\n   Итого создано: {created} из {len(thumbnail_sizes)}")
    
    # Проверяем результат
    print("\n3. Проверка созданных sizes:")
    command_list = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e 'SELECT width, height FROM thumbnail_size ORDER BY width, height;' 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command_list, timeout=30)
    output_list = stdout.read().decode().strip()
    if output_list:
        lines = [l for l in output_list.split('\n') if l.strip() and not l.strip().startswith('width')]
        print(f"   Найдено размеров: {len(lines)}")
        for line in lines:
            if line.strip():
                print(f"   - {line.strip()}")
    else:
        print("   ⚠️  Не удалось получить список sizes")
    
    ssh.close()
    
    print("\n" + "=" * 60)
    print("СОЗДАНИЕ THUMBNAIL SIZES ЗАВЕРШЕНО")
    print("=" * 60)
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)









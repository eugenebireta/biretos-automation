"""
Создание thumbnail sizes пошагово.
"""
import sys
import paramiko
import uuid
from datetime import datetime

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

print("=" * 60)
print("СОЗДАНИЕ THUMBNAIL SIZES (ПОШАГОВО)")
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
    
    # Шаг 1: Проверяем таблицу
    print("\n1. Проверка таблицы thumbnail_size:")
    command_check = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e 'SHOW TABLES LIKE \"thumbnail_size\";' 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command_check, timeout=30)
    output = stdout.read().decode().strip()
    
    if "thumbnail_size" not in output:
        print("   Таблица не существует, создаём...")
        # Создаём таблицу
        create_sql = "CREATE TABLE thumbnail_size (id BINARY(16) NOT NULL, width INT(11) NOT NULL, height INT(11) NOT NULL, created_at DATETIME(3) NOT NULL, updated_at DATETIME(3) NULL, PRIMARY KEY (id), UNIQUE KEY uniq_width_height (width, height)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"
        command_create = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"{create_sql}\" 2>&1 | grep -v Warning"
        stdin, stdout, stderr = ssh.exec_command(command_create, timeout=30)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status == 0:
            print("   ✅ Таблица создана")
        else:
            error = stderr.read().decode().strip()
            print(f"   ❌ Ошибка: {error[:200]}")
            sys.exit(1)
    else:
        print("   ✅ Таблица существует")
    
    # Шаг 2: Создаём размеры
    print(f"\n2. Создание {len(thumbnail_sizes)} thumbnail sizes:")
    created = 0
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S.000')
    
    for width, height in thumbnail_sizes:
        size_id = uuid.uuid4()
        size_id_hex = size_id.hex
        
        # Проверяем существование
        check_sql = f"SELECT COUNT(*) FROM thumbnail_size WHERE width={width} AND height={height};"
        command_check = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"{check_sql}\" 2>&1 | grep -v Warning | tail -1"
        stdin, stdout, stderr = ssh.exec_command(command_check, timeout=30)
        count = stdout.read().decode().strip()
        
        if count.isdigit() and int(count) > 0:
            print(f"   [SKIP] {width}x{height} - уже существует")
            continue
        
        # Вставляем
        insert_sql = f"INSERT INTO thumbnail_size (id, width, height, created_at, updated_at) VALUES (UNHEX('{size_id_hex}'), {width}, {height}, '{now}', '{now}');"
        command_insert = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"{insert_sql}\" 2>&1 | grep -v Warning"
        stdin, stdout, stderr = ssh.exec_command(command_insert, timeout=30)
        exit_status = stdout.channel.recv_exit_status()
        error = stderr.read().decode().strip()
        
        if exit_status == 0 and not error:
            print(f"   ✅ {width}x{height} - создан")
            created += 1
        elif "Duplicate entry" in error:
            print(f"   [SKIP] {width}x{height} - уже существует")
        else:
            print(f"   ❌ {width}x{height} - ошибка: {error[:100]}")
    
    print(f"\n   Итого создано: {created} из {len(thumbnail_sizes)}")
    
    # Шаг 3: Проверяем результат
    print("\n3. Проверка созданных sizes:")
    list_sql = "SELECT width, height FROM thumbnail_size ORDER BY width, height;"
    command_list = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"{list_sql}\" 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command_list, timeout=30)
    output = stdout.read().decode().strip()
    error = stderr.read().decode().strip()
    
    if output and "ERROR" not in output:
        lines = [l for l in output.split('\n') if l.strip() and 'width' not in l.lower()]
        if lines:
            print(f"   ✅ Найдено размеров: {len(lines)}")
            for line in lines[:10]:
                print(f"   - {line.strip()}")
        else:
            print("   ⚠️  Таблица пуста")
    else:
        print(f"   ⚠️  Не удалось получить список: {error[:200]}")
    
    ssh.close()
    
    print("\n" + "=" * 60)
    print("СОЗДАНИЕ THUMBNAIL SIZES ЗАВЕРШЕНО")
    print("=" * 60)
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)









"""
Создание thumbnail sizes для Shopware.
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
print("СОЗДАНИЕ THUMBNAIL SIZES")
print("=" * 60)

# Стандартные размеры для Shopware
thumbnail_sizes = [
    (192, 192),   # Для превьюшек в каталоге
    (400, 400),   # Для карточек товаров
    (800, 800),   # Для больших изображений
    (1920, 1920), # Для полноразмерных изображений
]

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=ssh_username, password=ssh_password, timeout=10)
    print(f"  [OK] Подключено к {host}")
    
    # Проверяем, существует ли таблица
    print("\n1. Проверка таблицы thumbnail_size:")
    command_check_table = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e 'SHOW TABLES LIKE \"thumbnail_size\";' 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command_check_table, timeout=30)
    output_table = stdout.read().decode().strip()
    
    if "thumbnail_size" not in output_table:
        print("   ❌ Таблица thumbnail_size не существует, создаём...")
        # Создаём таблицу
        create_table_sql = """CREATE TABLE IF NOT EXISTS `thumbnail_size` (
  `id` BINARY(16) NOT NULL,
  `width` INT(11) NOT NULL,
  `height` INT(11) NOT NULL,
  `created_at` DATETIME(3) NOT NULL,
  `updated_at` DATETIME(3) NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq.thumbnail_size.width_height` (`width`, `height`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"""
        
        # Сохраняем SQL во временный файл
        command_create = f"docker exec {container_name} bash -c 'cat > /tmp/create_thumbnail_size.sql << \"EOF\"\n{create_table_sql}\nEOF'"
        stdin, stdout, stderr = ssh.exec_command(command_create, timeout=30)
        stdout.channel.recv_exit_status()
        
        # Выполняем SQL
        command_exec = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware < /tmp/create_thumbnail_size.sql 2>&1 | grep -v Warning"
        stdin, stdout, stderr = ssh.exec_command(command_exec, timeout=30)
        exit_status = stdout.channel.recv_exit_status()
        
        if exit_status == 0:
            print("   ✅ Таблица создана")
        else:
            error = stderr.read().decode().strip()
            print(f"   ❌ Ошибка создания таблицы: {error}")
    else:
        print("   ✅ Таблица существует")
    
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
        
        if exit_status == 0:
            print(f"   ✅ {width}x{height} - создан")
            created += 1
        else:
            error = stderr.read().decode().strip()
            print(f"   ❌ {width}x{height} - ошибка: {error[:100]}")
    
    print(f"\n   Итого создано: {created} из {len(thumbnail_sizes)}")
    
    # Проверяем результат
    print("\n3. Проверка созданных sizes:")
    command_list = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e 'SELECT width, height FROM thumbnail_size ORDER BY width, height;' 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command_list, timeout=30)
    output_list = stdout.read().decode().strip()
    if output_list:
        lines = output_list.split('\n')
        print(f"   Найдено размеров: {len(lines) - 1}")
        for line in lines[1:]:
            if line.strip():
                print(f"   - {line.strip()}")
    
    ssh.close()
    
    print("\n" + "=" * 60)
    print("СОЗДАНИЕ THUMBNAIL SIZES ЗАВЕРШЕНО")
    print("=" * 60)
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)









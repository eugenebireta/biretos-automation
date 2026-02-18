"""
Создание thumbnail sizes через один SQL запрос.
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
    
    # Создаём все размеры одним SQL запросом
    print(f"\nСоздание {len(thumbnail_sizes)} thumbnail sizes:")
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S.000')
    
    sql_parts = []
    for width, height in thumbnail_sizes:
        size_id = uuid.uuid4()
        size_id_hex = size_id.hex
        sql_parts.append(f"(UNHEX('{size_id_hex}'), {width}, {height}, '{now}', '{now}')")
    
    # Создаём таблицу и вставляем данные
    full_sql = f"""CREATE TABLE IF NOT EXISTS `thumbnail_size` (
  `id` BINARY(16) NOT NULL,
  `width` INT(11) NOT NULL,
  `height` INT(11) NOT NULL,
  `created_at` DATETIME(3) NOT NULL,
  `updated_at` DATETIME(3) NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq.thumbnail_size.width_height` (`width`, `height`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO thumbnail_size (id, width, height, created_at, updated_at) VALUES
{', '.join(sql_parts)};
"""
    
    # Сохраняем SQL в файл на сервере
    print("   Сохранение SQL...")
    command_save = f"docker exec {container_name} bash -c 'cat > /tmp/thumbnails.sql << \"EOFSQL\"\n{full_sql}\nEOFSQL'"
    stdin, stdout, stderr = ssh.exec_command(command_save, timeout=30)
    exit_status = stdout.channel.recv_exit_status()
    
    if exit_status != 0:
        error = stderr.read().decode().strip()
        print(f"   ❌ Ошибка сохранения SQL: {error[:200]}")
        # Пробуем выполнить напрямую
        print("   Пробуем выполнить напрямую...")
        for width, height in thumbnail_sizes:
            size_id = uuid.uuid4()
            size_id_hex = size_id.hex
            sql = f"INSERT IGNORE INTO thumbnail_size (id, width, height, created_at, updated_at) VALUES (UNHEX('{size_id_hex}'), {width}, {height}, NOW(), NOW());"
            command = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"{sql}\" 2>&1"
            stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0:
                print(f"   ✅ {width}x{height}")
            else:
                error = stderr.read().decode().strip()
                if "Table" in error and "doesn't exist" in error:
                    # Создаём таблицу сначала
                    create_sql = "CREATE TABLE IF NOT EXISTS thumbnail_size (id BINARY(16) NOT NULL, width INT(11) NOT NULL, height INT(11) NOT NULL, created_at DATETIME(3) NOT NULL, updated_at DATETIME(3) NULL, PRIMARY KEY (id), UNIQUE KEY uniq_width_height (width, height)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
                    command_create = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"{create_sql}\" 2>&1"
                    stdin2, stdout2, stderr2 = ssh.exec_command(command_create, timeout=30)
                    stdout2.channel.recv_exit_status()
                    # Повторяем вставку
                    stdin3, stdout3, stderr3 = ssh.exec_command(command, timeout=30)
                    if stdout3.channel.recv_exit_status() == 0:
                        print(f"   ✅ {width}x{height}")
                    else:
                        print(f"   ❌ {width}x{height}: {stderr3.read().decode().strip()[:100]}")
                else:
                    print(f"   ❌ {width}x{height}: {error[:100]}")
    else:
        # Выполняем SQL из файла
        print("   Выполнение SQL...")
        command_exec = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware < /tmp/thumbnails.sql 2>&1 | grep -v Warning"
        stdin, stdout, stderr = ssh.exec_command(command_exec, timeout=30)
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        exit_status = stdout.channel.recv_exit_status()
        
        if exit_status == 0:
            print("   ✅ Thumbnail sizes созданы")
        else:
            print(f"   ⚠️  Предупреждение: {error[:200]}")
    
    # Проверяем результат
    print("\nПроверка созданных sizes:")
    command_list = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e 'SELECT width, height FROM thumbnail_size ORDER BY width, height;' 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command_list, timeout=30)
    output_list = stdout.read().decode().strip()
    if output_list:
        lines = [l for l in output_list.split('\n') if l.strip() and 'width' not in l.lower() and 'ERROR' not in l]
        if lines:
            print(f"   Найдено размеров: {len(lines)}")
            for line in lines[:10]:
                if line.strip():
                    print(f"   - {line.strip()}")
        else:
            print("   ⚠️  Не удалось получить список")
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









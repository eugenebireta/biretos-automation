"""
Создание thumbnail sizes через SQL файл на сервере.
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
print("СОЗДАНИЕ THUMBNAIL SIZES ЧЕРЕЗ SQL ФАЙЛ")
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
    
    # Создаём SQL файл
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S.000')
    sql_lines = [
        "CREATE TABLE IF NOT EXISTS `thumbnail_size` (",
        "  `id` BINARY(16) NOT NULL,",
        "  `width` INT(11) NOT NULL,",
        "  `height` INT(11) NOT NULL,",
        "  `created_at` DATETIME(3) NOT NULL,",
        "  `updated_at` DATETIME(3) NULL DEFAULT NULL,",
        "  PRIMARY KEY (`id`),",
        "  UNIQUE KEY `uniq.thumbnail_size.width_height` (`width`, `height`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
        ""
    ]
    
    for width, height in thumbnail_sizes:
        size_id = uuid.uuid4()
        size_id_hex = size_id.hex
        sql_lines.append(f"INSERT IGNORE INTO thumbnail_size (id, width, height, created_at, updated_at) VALUES (UNHEX('{size_id_hex}'), {width}, {height}, '{now}', '{now}');")
    
    sql_content = "\n".join(sql_lines)
    
    # Сохраняем SQL в файл на хосте (не в контейнере)
    print("\n1. Создание SQL файла на сервере...")
    sftp = ssh.open_sftp()
    try:
        remote_file = sftp.file('/tmp/create_thumbnails.sql', 'w')
        remote_file.write(sql_content)
        remote_file.close()
        print("   ✅ Файл создан")
    except Exception as e:
        print(f"   ❌ Ошибка создания файла: {e}")
        sftp.close()
        ssh.close()
        sys.exit(1)
    finally:
        sftp.close()
    
    # Копируем файл в контейнер и выполняем
    print("\n2. Выполнение SQL...")
    command = f"docker cp /tmp/create_thumbnails.sql {container_name}:/tmp/create_thumbnails.sql && docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware < /tmp/create_thumbnails.sql 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
    output = stdout.read().decode().strip()
    error = stderr.read().decode().strip()
    exit_status = stdout.channel.recv_exit_status()
    
    if exit_status == 0 and not error:
        print("   ✅ SQL выполнен успешно")
    else:
        if error and "ERROR" not in error:
            print(f"   ⚠️  Предупреждение: {error[:200]}")
        else:
            print(f"   ⚠️  Вывод: {output[:200]}")
    
    # Проверяем результат
    print("\n3. Проверка созданных sizes:")
    command_check = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e 'SELECT width, height FROM thumbnail_size ORDER BY width, height;' 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command_check, timeout=30)
    output = stdout.read().decode().strip()
    error = stderr.read().decode().strip()
    
    if output and "ERROR" not in output:
        lines = [l for l in output.split('\n') if l.strip() and 'width' not in l.lower() and 'ERROR' not in l]
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








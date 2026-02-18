"""Финальное исправление thumbnail sizes"""
import paramiko
import uuid
from datetime import datetime

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

print("=" * 60)
print("ФИНАЛЬНОЕ ИСПРАВЛЕНИЕ THUMBNAIL SIZES")
print("=" * 60)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=ssh_username, password=ssh_password, timeout=30)

# Создаём SQL файл внутри контейнера
print("\n1. Создание SQL скрипта...")
sql_content = """CREATE TABLE IF NOT EXISTS `thumbnail_size` (
  `id` BINARY(16) NOT NULL,
  `width` INT(11) NOT NULL,
  `height` INT(11) NOT NULL,
  `created_at` DATETIME(3) NOT NULL,
  `updated_at` DATETIME(3) NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq.thumbnail_size.width_height` (`width`, `height`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

try:
    # Создаём временный SQL файл
    command_create_sql = f"docker exec {container_name} bash -c 'cat > /tmp/create_thumbnail_size.sql << \"EOF\"\n{sql_content}EOF'"
    stdin_create, stdout_create, stderr_create = ssh.exec_command(command_create_sql, timeout=30)
    stdout_create.read()
    
    # Выполняем SQL файл
    print("2. Создание таблицы thumbnail_size...")
    command_exec = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware < /tmp/create_thumbnail_size.sql 2>&1 | grep -v Warning"
    stdin_exec, stdout_exec, stderr_exec = ssh.exec_command(command_exec, timeout=30)
    output_exec = stdout_exec.read().decode()
    errors_exec = stderr_exec.read().decode()
    
    if "ERROR" not in output_exec and "ERROR" not in errors_exec:
        print("   ✅ Таблица создана или уже существует")
    else:
        print(f"   ⚠️ {output_exec[:100]}")
        
except Exception as e:
    print(f"   ⚠️ Ошибка создания таблицы: {e}")

# Создаём thumbnail sizes
print("\n3. Создание thumbnail sizes...")
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
    
    # Проверяем существование
    command_check = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e 'SELECT COUNT(*) FROM thumbnail_size WHERE width={width} AND height={height};' 2>&1 | grep -v Warning | tail -1"
    stdin_check, stdout_check, stderr_check = ssh.exec_command(command_check, timeout=30)
    output_check = stdout_check.read().decode().strip()
    
    if output_check and output_check.isdigit() and int(output_check) > 0:
        print(f"   [SKIP] Размер {width}x{height} уже существует")
    else:
        # Генерируем UUID
        size_uuid = uuid.uuid4()
        size_id_hex = size_uuid.hex
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        # Вставляем через SQL с правильным экранированием
        sql_insert = f"INSERT INTO thumbnail_size (id, width, height, created_at, updated_at) VALUES (UNHEX('{size_id_hex}'), {width}, {height}, '{now}', '{now}');"
        command_insert = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e '{sql_insert}' 2>&1 | grep -v Warning"
        stdin_insert, stdout_insert, stderr_insert = ssh.exec_command(command_insert, timeout=30)
        output_insert = stdout_insert.read().decode()
        errors_insert = stderr_insert.read().decode()
        
        if "ERROR" not in output_insert and "ERROR" not in errors_insert:
            print(f"   ✅ Создан размер: {width}x{height}")
            created += 1
        else:
            if "Duplicate" in output_insert or "duplicate" in output_insert:
                print(f"   [SKIP] Размер {width}x{height} уже существует")
            else:
                print(f"   ❌ Ошибка создания {width}x{height}: {output_insert[:100]}")

print(f"\n   Итого создано: {created} из {len(thumbnail_sizes)}")

# Очистка кеша
print("\n4. Очистка кеша...")
try:
    command_cache = f"docker exec {container_name} php bin/console cache:clear 2>&1"
    stdin_cache, stdout_cache, stderr_cache = ssh.exec_command(command_cache, timeout=60)
    output_cache = stdout_cache.read().decode()
    if "ERROR" not in output_cache:
        print("   ✅ Кеш очищен")
except Exception as e:
    print(f"   ⚠️ Ошибка очистки кеша: {e}")

# Генерация thumbnails
print("\n5. Генерация thumbnails...")
try:
    command_gen = f"docker exec {container_name} php bin/console media:generate-thumbnails 2>&1"
    stdin_gen, stdout_gen, stderr_gen = ssh.exec_command(command_gen, timeout=600)
    
    output_lines = []
    for line in iter(stdout_gen.readline, ""):
        if line:
            line = line.rstrip()
            if any(kw in line for kw in ["Generated", "Skipped", "Errors", "Action", "Number", "---", "%"]):
                print(f"   {line}")
            output_lines.append(line)
    
    exit_status = stdout_gen.channel.recv_exit_status()
    
    if exit_status == 0:
        generated = 0
        skipped = 0
        for line in output_lines:
            if "Generated" in line and "Number" not in line:
                parts = line.split()
                for p in parts:
                    if p.isdigit():
                        generated = int(p)
                        break
            if "Skipped" in line and "Number" not in line:
                parts = line.split()
                for p in parts:
                    if p.isdigit():
                        skipped = int(p)
                        break
        
        if generated > 0:
            print(f"\n   ✅ Сгенерировано: {generated}")
        if skipped > 0:
            print(f"   ⚠️ Пропущено: {skipped}")
except Exception as e:
    print(f"   ❌ Ошибка: {e}")

# Проверка результата
print("\n6. Проверка результата...")
try:
    command_list = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e 'SELECT width, height FROM thumbnail_size ORDER BY width, height;' 2>&1 | grep -v Warning"
    stdin_list, stdout_list, stderr_list = ssh.exec_command(command_list, timeout=30)
    output_list = stdout_list.read().decode()
    
    if output_list:
        sizes = [l for l in output_list.strip().split('\n') if l and not l.startswith('width')]
        print(f"   ✅ Thumbnail sizes в БД: {len(sizes)}")
        for line in sizes:
            parts = line.split('\t')
            if len(parts) >= 2:
                print(f"     {parts[0]}x{parts[1]}")
    
    # Проверка файлов
    command_files = f"docker exec {container_name} find public/media -type f -name '*.jpg' -o -name '*.png' 2>/dev/null | grep thumbnail | wc -l"
    stdin_files, stdout_files, stderr_files = ssh.exec_command(command_files, timeout=30)
    output_files = stdout_files.read().decode().strip()
    
    if output_files and output_files.isdigit():
        count = int(output_files)
        if count > 0:
            print(f"   ✅ Thumbnail файлов на диске: {count}")
        else:
            print(f"   ⚠️ Thumbnail файлы не найдены на диске")
except Exception as e:
    print(f"   ⚠️ Ошибка проверки: {e}")

ssh.close()

print("\n" + "=" * 60)
print("ИСПРАВЛЕНИЕ ЗАВЕРШЕНО")
print("=" * 60)









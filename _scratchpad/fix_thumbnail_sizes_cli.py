"""Исправление проблемы с thumbnail sizes через консольные команды"""
import paramiko
import sys

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

print("=" * 60)
print("ИСПРАВЛЕНИЕ THUMBNAIL SIZES ЧЕРЕЗ CLI")
print("=" * 60)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=ssh_username, password=ssh_password, timeout=30)

# ШАГ 1: Проверка существования thumbnail sizes
print("\n1. Проверка существования thumbnail sizes...")
try:
    command = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(*) FROM thumbnail_size;\" 2>&1 | grep -v Warning | tail -1"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    output = stdout.read().decode().strip()
    
    if output and output.isdigit():
        count = int(output)
        if count > 0:
            print(f"   ✅ Найдено thumbnail sizes: {count}")
            # Показываем существующие
            command_list = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT width, height FROM thumbnail_size;\" 2>&1 | grep -v Warning"
            stdin_list, stdout_list, stderr_list = ssh.exec_command(command_list, timeout=30)
            output_list = stdout_list.read().decode()
            if output_list:
                print("   Существующие размеры:")
                for line in output_list.strip().split('\n'):
                    if line and not line.startswith('width'):
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            print(f"     {parts[0]}x{parts[1]}")
            skip_creation = True
        else:
            print("   ⚠️ Thumbnail sizes отсутствуют")
            skip_creation = False
    else:
        # Проверяем существование таблицы
        command_table = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SHOW TABLES LIKE 'thumbnail_size';\" 2>&1 | grep -v Warning"
        stdin_table, stdout_table, stderr_table = ssh.exec_command(command_table, timeout=30)
        output_table = stdout_table.read().decode().strip()
        
        if "thumbnail_size" in output_table:
            print("   ⚠️ Таблица существует, но пустая")
            skip_creation = False
        else:
            print("   ⚠️ Таблица не существует")
            skip_creation = False
            
except Exception as e:
    print(f"   ⚠️ Ошибка проверки: {e}")
    skip_creation = False

# ШАГ 2: Создание thumbnail sizes
if not skip_creation:
    print("\n2. Создание стандартных thumbnail sizes...")
    
    thumbnail_sizes = [
        {"width": 192, "height": 192},
        {"width": 400, "height": 400},
        {"width": 800, "height": 800},
        {"width": 1920, "height": 1920},
    ]
    
    print(f"   Создаём {len(thumbnail_sizes)} размеров...")
    
    # Проверяем структуру таблицы
    try:
        command_describe = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"DESCRIBE thumbnail_size;\" 2>&1 | grep -v Warning"
        stdin_desc, stdout_desc, stderr_desc = ssh.exec_command(command_describe, timeout=30)
        output_desc = stdout_desc.read().decode()
        
        if "ERROR 1146" in output_desc:
            print("   ⚠️ Таблица не существует, создаём через Shopware...")
            # Shopware создаст таблицу автоматически при первом INSERT
            # Но нужно использовать правильную структуру Shopware
            
        # Создаём размеры через SQL с правильной структурой Shopware
        # Shopware использует UUID для id, created_at, updated_at
        import uuid
        from datetime import datetime
        
        created = 0
        for size in thumbnail_sizes:
            width = size["width"]
            height = size["height"]
            
            # Проверяем, существует ли уже такой размер
            command_check = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(*) FROM thumbnail_size WHERE width={width} AND height={height};\" 2>&1 | grep -v Warning | tail -1"
            stdin_check, stdout_check, stderr_check = ssh.exec_command(command_check, timeout=30)
            output_check = stdout_check.read().decode().strip()
            
            if output_check and output_check.isdigit() and int(output_check) > 0:
                print(f"   [SKIP] Размер {width}x{height} уже существует")
            else:
                # Генерируем UUID для id
                size_id = str(uuid.uuid4()).replace('-', '')
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Shopware структура: id (BINARY(16)), width, height, created_at, updated_at
                # Используем HEX для UUID
                size_id_hex = size_id
                
                # Создаём через SQL
                sql = f"INSERT INTO thumbnail_size (id, width, height, created_at, updated_at) VALUES (UNHEX('{size_id}'), {width}, {height}, '{now}', '{now}');"
                command_sql = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"{sql}\" 2>&1 | grep -v Warning"
                stdin_sql, stdout_sql, stderr_sql = ssh.exec_command(command_sql, timeout=30)
                output_sql = stdout_sql.read().decode()
                errors_sql = stderr_sql.read().decode()
                
                if "ERROR" not in output_sql and "ERROR" not in errors_sql:
                    print(f"   ✅ Создан размер: {width}x{height}")
                    created += 1
                else:
                    # Пробуем без UNHEX (если id - VARCHAR)
                    sql2 = f"INSERT INTO thumbnail_size (id, width, height, created_at, updated_at) VALUES ('{size_id}', {width}, {height}, '{now}', '{now}');"
                    command_sql2 = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"{sql2}\" 2>&1 | grep -v Warning"
                    stdin_sql2, stdout_sql2, stderr_sql2 = ssh.exec_command(command_sql2, timeout=30)
                    output_sql2 = stdout_sql2.read().decode()
                    
                    if "ERROR" not in output_sql2:
                        print(f"   ✅ Создан размер: {width}x{height}")
                        created += 1
                    else:
                        print(f"   ❌ Ошибка создания {width}x{height}: {output_sql2[:150]}")
        
        print(f"\n   Итого создано: {created} из {len(thumbnail_sizes)}")
        
    except Exception as e:
        print(f"   ❌ Ошибка создания: {e}")
        import traceback
        traceback.print_exc()

# ШАГ 3: Очистка кеша
print("\n3. Очистка кеша...")
try:
    commands = [
        ("cache:clear", "Очистка кеша"),
    ]
    
    for cmd, desc in commands:
        print(f"   {desc}...")
        command = f"docker exec {container_name} php bin/console {cmd} 2>&1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
        output = stdout.read().decode()
        
        if "ERROR" not in output and "Exception" not in output:
            print(f"   ✅ {desc} выполнено")
        else:
            error_lines = [line for line in output.split('\n') if 'ERROR' in line or 'Exception' in line][:2]
            if error_lines:
                print(f"   ⚠️ Предупреждения: {error_lines[0][:80]}")
    
    # Пробуем обновить индексы
    try:
        command_dal = f"docker exec {container_name} php bin/console dal:refresh:index 2>&1"
        stdin_dal, stdout_dal, stderr_dal = ssh.exec_command(command_dal, timeout=60)
        output_dal = stdout_dal.read().decode()
        if "ERROR" not in output_dal and "Exception" not in output_dal:
            print(f"   ✅ Обновление индексов DAL выполнено")
    except:
        pass
        
except Exception as e:
    print(f"   ⚠️ Ошибка очистки кеша: {e}")

# ШАГ 4: Генерация thumbnails
print("\n4. Генерация thumbnails...")
try:
    command = f"docker exec {container_name} php bin/console media:generate-thumbnails 2>&1"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=600)
    
    output_lines = []
    for line in iter(stdout.readline, ""):
        if line:
            line = line.rstrip()
            if any(keyword in line for keyword in ["Generated", "Skipped", "Errors", "Action", "Number", "---", "%", "/"]):
                print(f"   {line}")
            output_lines.append(line)
    
    exit_status = stdout.channel.recv_exit_status()
    
    if exit_status == 0:
        output_text = "\n".join(output_lines)
        generated_count = 0
        skipped_count = 0
        
        for line in output_lines:
            if "Generated" in line and "Number" not in line:
                # Извлекаем число
                parts = line.split()
                for part in parts:
                    if part.isdigit():
                        generated_count = int(part)
                        break
            if "Skipped" in line and "Number" not in line:
                parts = line.split()
                for part in parts:
                    if part.isdigit():
                        skipped_count = int(part)
                        break
        
        if generated_count > 0:
            print(f"\n   ✅ Сгенерировано thumbnails: {generated_count}")
        if skipped_count > 0:
            print(f"   ⚠️ Пропущено: {skipped_count}")
    else:
        print(f"   ⚠️ Команда завершилась с кодом: {exit_status}")
        
except Exception as e:
    print(f"   ❌ Ошибка генерации: {e}")

# ШАГ 5: Проверка результата
print("\n5. Проверка результата...")

# 5.1 Проверка таблицы
print("   5.1. Проверка таблицы thumbnail_size...")
try:
    command = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT width, height FROM thumbnail_size ORDER BY width, height;\" 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    output = stdout.read().decode()
    
    if output and output.strip():
        sizes = [line for line in output.strip().split('\n') if line and not line.startswith('width')]
        print(f"   ✅ Найдено thumbnail sizes: {len(sizes)}")
        print("   Размеры:")
        for line in sizes:
            parts = line.split('\t')
            if len(parts) >= 2:
                print(f"     {parts[0]}x{parts[1]}")
    else:
        print("   ⚠️ Thumbnail sizes не найдены")
        
except Exception as e:
    print(f"   ⚠️ Ошибка проверки: {e}")

# 5.2 Проверка файлов
print("   5.2. Проверка файлов thumbnails на диске...")
try:
    command_count = f"docker exec {container_name} find public/media -type f \\( -name '*.jpg' -o -name '*.png' \\) 2>/dev/null | grep -c thumbnail || echo 0"
    stdin_count, stdout_count, stderr_count = ssh.exec_command(command_count, timeout=30)
    output_count = stdout_count.read().decode().strip()
    
    if output_count and output_count.isdigit():
        count = int(output_count)
        if count > 0:
            print(f"   ✅ Найдено thumbnail файлов: {count}")
            
            # Показываем примеры
            command_examples = f"docker exec {container_name} find public/media -type f \\( -name '*.jpg' -o -name '*.png' \\) 2>/dev/null | grep thumbnail | head -5"
            stdin_ex, stdout_ex, stderr_ex = ssh.exec_command(command_examples, timeout=30)
            examples = [line.rstrip() for line in stdout_ex if line.rstrip()]
            if examples:
                print("   Примеры файлов:")
                for ex in examples[:3]:
                    print(f"     {ex}")
        else:
            print("   ⚠️ Thumbnail файлы не найдены на диске")
    else:
        print("   ⚠️ Не удалось подсчитать файлы")
        
except Exception as e:
    print(f"   ⚠️ Ошибка проверки: {e}")

ssh.close()

print("\n" + "=" * 60)
print("ИСПРАВЛЕНИЕ ЗАВЕРШЕНО")
print("=" * 60)









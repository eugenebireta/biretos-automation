"""
Поиск правильной таблицы для mediaType
"""
import paramiko

host = "77.233.222.214"
username = "root"
password = "HuPtNj39"

print("=" * 60)
print("ПОИСК ТАБЛИЦЫ MEDIATYPE")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    
    # Ищем все таблицы связанные с media
    print("\n1. Поиск таблиц связанных с media...")
    command = "docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SHOW TABLES LIKE '%media%';\" 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    tables = stdout.read().decode()
    
    if tables.strip():
        print("   Найденные таблицы:")
        for line in tables.split('\n'):
            if line.strip():
                print(f"     {line}")
    
    # Проверяем структуру таблицы media
    print("\n2. Структура таблицы media...")
    command = "docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"DESCRIBE media;\" 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    structure = stdout.read().decode()
    
    if structure.strip():
        print("   Поля таблицы media:")
        for line in structure.split('\n'):
            if line.strip() and "Field" not in line:
                print(f"     {line}")
                if "type" in line.lower():
                    print(f"       [FOUND] Поле связано с type!")
    
    # Проверяем одно медиа
    print("\n3. Проверка конкретного медиа...")
    command = "docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT id, file_name, mime_type FROM media WHERE mime_type LIKE 'image/%' LIMIT 1\\G\" 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    media_info = stdout.read().decode()
    
    if media_info.strip():
        print("   Информация о медиа:")
        for line in media_info.split('\n'):
            if line.strip():
                print(f"     {line}")
    
    ssh.close()
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)









"""Настройка thumbnail sizes для Shopware"""
import paramiko
import sys

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

print("=" * 60)
print("НАСТРОЙКА THUMBNAIL SIZES")
print("=" * 60)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=ssh_username, password=ssh_password, timeout=30)

# Проверяем, существует ли таблица
print("\n1. Проверка таблицы thumbnail_size...")
try:
    command = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SHOW TABLES LIKE 'thumbnail_size';\" 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    output = stdout.read().decode().strip()
    
    if "thumbnail_size" in output:
        print("   ✅ Таблица существует")
    else:
        print("   ⚠️ Таблица не найдена, возможно используется другая структура")
        
except Exception as e:
    print(f"   ❌ Ошибка: {e}")

# Проверяем количество размеров
print("\n2. Проверка количества thumbnail sizes...")
try:
    command = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(*) as count FROM thumbnail_size;\" 2>&1 | grep -v Warning | tail -1"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    output = stdout.read().decode().strip()
    
    if output and output.isdigit():
        count = int(output)
        print(f"   Найдено размеров: {count}")
        if count == 0:
            print("   ⚠️ Thumbnail sizes не настроены!")
            print("   Нужно настроить через админку Shopware или создать стандартные размеры")
        else:
            print("   ✅ Thumbnail sizes настроены")
    else:
        print("   ⚠️ Не удалось получить количество")
        
except Exception as e:
    print(f"   ❌ Ошибка: {e}")

# Пробуем использовать команду Shopware для создания стандартных размеров
print("\n3. Попытка создания стандартных thumbnail sizes...")
try:
    # Пробуем разные варианты команд
    commands_to_try = [
        "media:thumbnail:generate:all",
        "media:generate-thumbnails --all",
        "media:thumbnail:create",
    ]
    
    for cmd in commands_to_try:
        try:
            full_cmd = f"docker exec {container_name} php bin/console {cmd} 2>&1"
            stdin, stdout, stderr = ssh.exec_command(full_cmd, timeout=30)
            output = stdout.read().decode()
            errors = stderr.read().decode()
            
            if "command" not in output.lower() or "not found" not in output.lower():
                print(f"   Команда '{cmd}':")
                if output:
                    for line in output.strip().split('\n')[:5]:
                        if line:
                            print(f"     {line}")
                break
        except:
            continue
    else:
        print("   ⚠️ Не найдена команда для создания thumbnail sizes")
        print("   Рекомендация: настроить через админку Shopware:")
        print("   Settings → Media → Thumbnail Sizes")
        
except Exception as e:
    print(f"   ⚠️ Ошибка: {e}")

# Проверяем структуру таблицы
print("\n4. Проверка структуры таблицы thumbnail_size...")
try:
    command = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"DESCRIBE thumbnail_size;\" 2>&1 | grep -v Warning"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    output = stdout.read().decode()
    
    if output and output.strip():
        print("   Структура таблицы:")
        for line in output.strip().split('\n'):
            if line:
                print(f"   {line}")
    else:
        print("   ⚠️ Не удалось получить структуру")
        
except Exception as e:
    print(f"   ❌ Ошибка: {e}")

ssh.close()

print("\n" + "=" * 60)
print("РЕКОМЕНДАЦИИ")
print("=" * 60)
print("Если thumbnail sizes не настроены:")
print("1. Войдите в админку Shopware: https://77.233.222.214/admin")
print("2. Перейдите: Settings → Media → Thumbnail Sizes")
print("3. Создайте стандартные размеры (например: 192x192, 800x800, 1920x1920)")
print("4. После этого запустите: media:generate-thumbnails")
print("=" * 60)

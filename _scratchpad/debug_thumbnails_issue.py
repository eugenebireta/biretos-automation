"""
Диагностика проблемы с thumbnails.
"""
import sys
import paramiko

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

print("=" * 60)
print("ДИАГНОСТИКА ПРОБЛЕМЫ С THUMBNAILS")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=ssh_username, password=ssh_password, timeout=10)
    print(f"  [OK] Подключено к {host}")
    
    # 1. Проверяем thumbnail sizes
    print("\n1. Проверка thumbnail sizes:")
    command1 = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e 'SELECT COUNT(*) FROM thumbnail_size;' 2>&1 | grep -v Warning | tail -1"
    stdin, stdout, stderr = ssh.exec_command(command1, timeout=30)
    count = stdout.read().decode().strip()
    print(f"   Количество sizes: {count}")
    
    # 2. Проверяем product_media
    print("\n2. Проверка product_media:")
    command2 = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e 'SELECT COUNT(*) FROM product_media;' 2>&1 | grep -v Warning | tail -1"
    stdin, stdout, stderr = ssh.exec_command(command2, timeout=30)
    count_pm = stdout.read().decode().strip()
    print(f"   Количество product_media: {count_pm}")
    
    # 3. Проверяем медиа с mime_type image
    print("\n3. Проверка медиа (изображения):")
    command3 = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(*) FROM media WHERE mime_type LIKE 'image/%';\" 2>&1 | grep -v Warning | tail -1"
    stdin, stdout, stderr = ssh.exec_command(command3, timeout=30)
    count_img = stdout.read().decode().strip()
    print(f"   Количество изображений: {count_img}")
    
    # 4. Проверяем медиа, привязанные к товарам
    print("\n4. Проверка медиа, привязанных к товарам:")
    command4 = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(DISTINCT pm.media_id) FROM product_media pm JOIN media m ON pm.media_id = m.id WHERE m.mime_type LIKE 'image/%';\" 2>&1 | grep -v Warning | tail -1"
    stdin, stdout, stderr = ssh.exec_command(command4, timeout=30)
    count_linked = stdout.read().decode().strip()
    print(f"   Медиа, привязанные к товарам: {count_linked}")
    
    # 5. Запускаем media:generate-thumbnails с подробным выводом
    print("\n5. Запуск media:generate-thumbnails (с выводом):")
    command5 = f"docker exec {container_name} php bin/console media:generate-thumbnails --verbose 2>&1"
    stdin, stdout, stderr = ssh.exec_command(command5, timeout=600)
    
    output_lines = []
    for line in stdout:
        try:
            line_str = line.decode('utf-8', errors='ignore').strip()
            if line_str:
                output_lines.append(line_str)
                print(f"   {line_str}")
        except:
            pass
    
    # Если нет вывода, проверяем stderr
    if not output_lines:
        print("   Нет вывода в stdout, проверяем stderr...")
        for line in stderr:
            try:
                line_str = line.decode('utf-8', errors='ignore').strip()
                if line_str:
                    print(f"   [stderr] {line_str}")
            except:
                pass
    
    ssh.close()
    
    print("\n" + "=" * 60)
    print("ДИАГНОСТИКА ЗАВЕРШЕНА")
    print("=" * 60)
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)








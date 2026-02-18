"""
Принудительная генерация thumbnails для медиа в Shopware
"""
import paramiko

host = "77.233.222.214"
username = "root"
password = "HuPtNj39"

print("=" * 60)
print("ПРИНУДИТЕЛЬНАЯ ГЕНЕРАЦИЯ THUMBNAILS")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    print("✓ Подключено к серверу")
    
    container_name = "shopware"
    
    # Пробуем с параметром --force
    print("\n1. Генерация thumbnails с --force...")
    command = f"docker exec {container_name} php bin/console media:generate-thumbnails --force"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=300)
    
    for line in stdout:
        line = line.strip()
        if line:
            print(f"   {line}")
    
    exit_status = stdout.channel.recv_exit_status()
    
    if exit_status == 0:
        print("\n✓ Генерация завершена")
    else:
        print(f"\n⚠ Код выхода: {exit_status}")
        
        # Пробуем альтернативный способ - через API или напрямую
        print("\n2. Альтернативный способ - проверка настроек thumbnail...")
        command = f"docker exec {container_name} php bin/console media:thumbnail:generate --help"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        help_text = stdout.read().decode()
        if help_text:
            print("   Доступные опции:")
            for line in help_text.split('\n')[:10]:
                if line.strip():
                    print(f"     {line}")
    
    ssh.close()
    
except Exception as e:
    print(f"✗ Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)









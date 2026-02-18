"""
Обновление индексов Shopware для отображения изменений на сайте.
"""
import sys
from pathlib import Path
import paramiko

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from import_utils import load_json, ROOT

config = load_json(ROOT / "config.json")

# Параметры SSH
host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

print("Обновление индексов Shopware...")
print(f"Подключение к {host}...")

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=ssh_username, password=ssh_password, timeout=10)
    print(f"  [OK] Подключено к {host}")
    
    # Обновление индексов DAL
    print("\nВыполнение dal:refresh:index...")
    command1 = f"docker exec {container_name} php bin/console dal:refresh:index"
    stdin, stdout, stderr = ssh.exec_command(command1, timeout=120)
    
    for line in stdout:
        try:
            line_str = line.decode('utf-8', errors='ignore').strip()
            if line_str:
                print(f"    {line_str}")
        except:
            pass
    
    exit_status1 = stdout.channel.recv_exit_status()
    
    if exit_status1 == 0:
        print(f"  [OK] Индексы обновлены")
    else:
        print(f"  [WARNING] Обновление индексов завершилось с кодом {exit_status1}")
    
    # Очистка кеша
    print("\nВыполнение cache:clear...")
    command2 = f"docker exec {container_name} php bin/console cache:clear"
    stdin, stdout, stderr = ssh.exec_command(command2, timeout=60)
    
    for line in stdout:
        try:
            line_str = line.decode('utf-8', errors='ignore').strip()
            if line_str:
                print(f"    {line_str}")
        except:
            pass
    
    exit_status2 = stdout.channel.recv_exit_status()
    
    if exit_status2 == 0:
        print(f"  [OK] Кеш очищен")
    else:
        print(f"  [WARNING] Очистка кеша завершилась с кодом {exit_status2}")
    
    ssh.close()
    
except Exception as e:
    print(f"  [ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✅ Готово! Индексы обновлены, кеш очищен.")
print("Проверьте сайт - категории должны отображаться корректно.")









"""
Агрессивная очистка кэша Shopware через консольные команды
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

import paramiko

HOST = "77.233.222.214"
USER = "root"
PASSWORD = "HuPtNj39"

print("=== Агрессивная очистка кэша Shopware ===")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    client.connect(HOST, username=USER, password=PASSWORD, timeout=20)
    
    commands = [
        "docker exec shopware php bin/console cache:clear",
        "docker exec shopware php bin/console cache:pool:clear cache.object",
        "docker exec shopware php bin/console cache:pool:clear cache.global_clearer",
    ]
    
    for cmd in commands:
        print(f"\nВыполняю: {cmd}")
        stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
        exit_status = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="ignore")
        err = stderr.read().decode("utf-8", errors="ignore")
        
        if exit_status == 0:
            print(f"✓ Успешно")
            if out:
                print(f"  Output: {out[:200]}")
        else:
            print(f"⚠ Exit code: {exit_status}")
            if err:
                print(f"  Error: {err[:200]}")
    
    print("\n✓ Кэш очищен")
    
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()
finally:
    client.close()









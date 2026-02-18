"""Выполнение SQL фикса на сервере через SSH"""
import subprocess
import sys

# SQL команда
sql = "UPDATE media_folder SET configuration_id = UNHEX('616401b99bee440c8333087ecc4ce4e8') WHERE id = UNHEX('01994d23ada87207aa7d8cb9994f5198');"

# Команда для выполнения через SSH (non-interactive с MYSQL_PWD)
ssh_cmd = f"""ssh -o BatchMode=yes root@216.9.227.124 'cd /var/www/shopware && export MYSQL_PWD=$(grep "^DATABASE_PASSWORD=" .env | cut -d= -f2 | tr -d "\\"" | tr -d "\\'" | xargs) && mysql -u root shopware -e "{sql}" 2>&1 | grep -v Warning:'"""

print("Выполнение SQL фикса...")
print(f"SQL: {sql}")
print()

try:
    result = subprocess.run(
        ssh_cmd,
        shell=True,
        capture_output=True,
        text=True,
        check=False
    )
    
    print("STDOUT:")
    print(result.stdout)
    print()
    print("STDERR:")
    print(result.stderr)
    print()
    print(f"Exit code: {result.returncode}")
    
    if result.returncode == 0:
        print("✓ SQL выполнен успешно")
    else:
        print("⚠ Ошибка при выполнении SQL")
        
except Exception as e:
    print(f"Ошибка: {e}")



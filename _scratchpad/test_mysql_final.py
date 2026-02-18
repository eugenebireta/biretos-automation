#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Финальный тест non-interactive MySQL через SSH"""
import subprocess
import sys

SSH_HOST = "root@216.9.227.124"
ENV_PATH = "/var/www/shopware/.env"

print("[TEST] Проверка SSH подключения без пароля...")
result = subprocess.run(
    ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", SSH_HOST, "echo OK"],
    capture_output=True,
    text=True,
    timeout=10
)

if result.returncode != 0:
    print(f"[ERROR] SSH подключение не работает: {result.stderr}")
    sys.exit(1)
print("[OK] SSH подключение работает")

print("[TEST] Выполнение MySQL запроса через SSH (non-interactive)...")

# Выполняем команду напрямую через SSH (без создания файла)
# Парсим DATABASE_URL или DATABASE_PASSWORD
cmd = f"""ENV_PATH="{ENV_PATH}" && DB_PASSWORD="" && if grep -q "^DATABASE_PASSWORD=" "$ENV_PATH"; then DB_PASSWORD=$(grep "^DATABASE_PASSWORD=" "$ENV_PATH" | cut -d= -f2 | tr -d '"' | tr -d "'" | xargs); elif grep -q "^DATABASE_URL=" "$ENV_PATH"; then DB_URL=$(grep "^DATABASE_URL=" "$ENV_PATH" | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs); DB_PASSWORD=$(echo "$DB_URL" | sed -n 's|.*://[^:]*:\\([^@]*\\)@.*|\\1|p'); fi && if [ -z "$DB_PASSWORD" ]; then echo "ERROR: Database password not found" >&2; exit 1; fi && export MYSQL_PWD="$DB_PASSWORD" && mysql -u root shopware -N -e "SELECT COUNT(*) as total_products FROM product;" 2>&1 | grep -v "Warning:" """

result = subprocess.run(
    ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", SSH_HOST, cmd],
    capture_output=True,
    text=True,
    timeout=30
)

if result.returncode == 0:
    print("[OK] MySQL запрос выполнен успешно")
    print(f"Результат: {result.stdout.strip()}")
    print("\n[SUCCESS] Все тесты пройдены! Non-interactive MySQL работает.")
    sys.exit(0)
else:
    print(f"[ERROR] Ошибка выполнения MySQL запроса:")
    print(f"STDOUT: {result.stdout}")
    print(f"STDERR: {result.stderr}")
    sys.exit(1)


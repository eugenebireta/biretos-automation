#!/usr/bin/env bash
# Non-interactive MySQL команды для Shopware
# Использование: 
#   ./non_interactive_mysql.sh "SELECT * FROM product LIMIT 1;"
#   или через SSH: ssh root@216.9.227.124 "bash -s" < non_interactive_mysql.sh "SELECT ..."

set -euo pipefail

# Путь к .env файлу Shopware
ENV_PATH="${ENV_PATH:-/var/www/shopware/.env}"
DB_NAME="${DB_NAME:-shopware}"
DB_USER="${DB_USER:-root}"

# Получаем пароль из .env (поддержка DATABASE_PASSWORD и DATABASE_URL)
if [ ! -f "$ENV_PATH" ]; then
    echo "ERROR: .env file not found at $ENV_PATH" >&2
    exit 1
fi

DB_PASSWORD=""
if grep -q "^DATABASE_PASSWORD=" "$ENV_PATH"; then
    DB_PASSWORD=$(grep "^DATABASE_PASSWORD=" "$ENV_PATH" | cut -d= -f2 | tr -d '"' | tr -d "'" | xargs)
elif grep -q "^DATABASE_URL=" "$ENV_PATH"; then
    DB_URL=$(grep "^DATABASE_URL=" "$ENV_PATH" | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
    DB_PASSWORD=$(echo "$DB_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
fi

if [ -z "$DB_PASSWORD" ]; then
    echo "ERROR: Database password not found in $ENV_PATH (check DATABASE_PASSWORD or DATABASE_URL)" >&2
    exit 1
fi

# Выполняем MySQL команду через MYSQL_PWD (non-interactive)
# Если SQL передан как аргумент, используем его
if [ $# -gt 0 ]; then
    SQL="$*"
    export MYSQL_PWD="$DB_PASSWORD"
    mysql -u "$DB_USER" "$DB_NAME" -e "$SQL" 2>&1 | grep -v "Warning:"
else
    # Если аргументов нет, читаем из stdin
    export MYSQL_PWD="$DB_PASSWORD"
    mysql -u "$DB_USER" "$DB_NAME" 2>&1 | grep -v "Warning:"
fi


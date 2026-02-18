#!/usr/bin/env bash
# Выполнение MySQL запроса через SSH (non-interactive)
# Использование: ./ssh_mysql_query.sh "SELECT * FROM product LIMIT 1;"

set -euo pipefail

SSH_HOST="${SSH_HOST:-root@216.9.227.124}"
SQL_QUERY="$*"

if [ -z "$SQL_QUERY" ]; then
    echo "Usage: $0 'SQL_QUERY'" >&2
    exit 1
fi

# Выполняем через SSH с использованием non_interactive_mysql.sh
ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH_HOST" \
    "bash -s" <<EOF
ENV_PATH=/var/www/shopware/.env
DB_NAME=shopware
DB_USER=root

if [ ! -f "\$ENV_PATH" ]; then
    echo "ERROR: .env file not found" >&2
    exit 1
fi

DB_PASSWORD=""
if grep -q "^DATABASE_PASSWORD=" "\$ENV_PATH"; then
    DB_PASSWORD=\$(grep "^DATABASE_PASSWORD=" "\$ENV_PATH" | cut -d= -f2 | tr -d '"' | tr -d "'" | xargs)
elif grep -q "^DATABASE_URL=" "\$ENV_PATH"; then
    DB_URL=\$(grep "^DATABASE_URL=" "\$ENV_PATH" | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
    DB_PASSWORD=\$(echo "\$DB_URL" | sed -n 's|.*://[^:]*:\\([^@]*\\)@.*|\\1|p')
fi

if [ -z "\$DB_PASSWORD" ]; then
    echo "ERROR: Database password not found (check DATABASE_PASSWORD or DATABASE_URL)" >&2
    exit 1
fi

export MYSQL_PWD="\$DB_PASSWORD"
mysql -u "\$DB_USER" "\$DB_NAME" -e "$SQL_QUERY" 2>&1 | grep -v "Warning:"
EOF


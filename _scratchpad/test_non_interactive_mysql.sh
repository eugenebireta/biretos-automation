#!/usr/bin/env bash
# Тест non-interactive MySQL команды

SSH_HOST="root@216.9.227.124"
ENV_PATH="/var/www/shopware/.env"
DB_NAME="shopware"
DB_USER="root"

# Получаем пароль и выполняем запрос
ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH_HOST" <<'EOF'
ENV_PATH="/var/www/shopware/.env"
DB_PASSWORD=$(grep "^DATABASE_PASSWORD=" "$ENV_PATH" | cut -d= -f2 | tr -d '"' | tr -d "'" | xargs)

if [ -z "$DB_PASSWORD" ]; then
    echo "ERROR: DATABASE_PASSWORD not found" >&2
    exit 1
fi

export MYSQL_PWD="$DB_PASSWORD"
mysql -u root shopware -N -e "SELECT COUNT(*) as total_products FROM product;" 2>&1 | grep -v "Warning:"
EOF




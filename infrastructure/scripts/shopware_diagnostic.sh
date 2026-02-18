#!/usr/bin/env bash
# Non-interactive диагностика Shopware через SSH
# Использование: ./shopware_diagnostic.sh

set -euo pipefail

SSH_HOST="${SSH_HOST:-root@216.9.227.124}"
ENV_PATH="/var/www/shopware/.env"

echo "=== Shopware Diagnostic (Non-Interactive) ==="
echo ""

# Получаем пароль БД и выполняем диагностику
ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH_HOST" <<'EOF'
ENV_PATH="/var/www/shopware/.env"

# Получаем пароль БД
DB_PASSWORD=""
if grep -q "^DATABASE_PASSWORD=" "$ENV_PATH"; then
    DB_PASSWORD=$(grep "^DATABASE_PASSWORD=" "$ENV_PATH" | cut -d= -f2 | tr -d '"' | tr -d "'" | xargs)
elif grep -q "^DATABASE_URL=" "$ENV_PATH"; then
    DB_URL=$(grep "^DATABASE_URL=" "$ENV_PATH" | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
    DB_PASSWORD=$(echo "$DB_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
fi

if [ -z "$DB_PASSWORD" ]; then
    echo "ERROR: Database password not found" >&2
    exit 1
fi

export MYSQL_PWD="$DB_PASSWORD"

echo "1. Products:"
mysql -u root shopware -N -e "SELECT COUNT(*) FROM product;" 2>&1 | grep -v "Warning:"

echo ""
echo "2. Product Media:"
mysql -u root shopware -N -e "SELECT COUNT(*) FROM product_media;" 2>&1 | grep -v "Warning:"

echo ""
echo "3. Media:"
mysql -u root shopware -N -e "SELECT COUNT(*) FROM media;" 2>&1 | grep -v "Warning:"

echo ""
echo "4. Product Listing Index:"
mysql -u root shopware -N -e "SELECT COUNT(*) FROM product_listing_index;" 2>&1 | grep -v "Warning:"

echo ""
echo "5. Recent Products (last 5):"
mysql -u root shopware -e "SELECT product_number, name, created_at FROM product ORDER BY created_at DESC LIMIT 5;" 2>&1 | grep -v "Warning:"
EOF

echo ""
echo "=== Diagnostic Complete ==="




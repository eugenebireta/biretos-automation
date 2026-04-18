#!/bin/bash
# Biretos Observable Recovery — weekly automated restore test
# Per critique 3: "Бэкап не существует, пока из него не удалось развернуть систему"
#
# What this does:
#   1. Pick the latest hourly DB dump from /root/backups/hourly/db_*.sql.gz
#   2. Restore into a TEST database (NOT production)
#   3. Verify schema present (count tables) + data sanity (count products if exists)
#   4. Drop test DB (cleanup)
#   5. Telegram: OK or FAIL
#
# Runs on both biretos.ae and dev.bireta.ru (detects env).
# Install: weekly cron Sunday 02:00

set -e
HOSTLABEL="${BACKUP_HOST_LABEL:-$(hostname)}"

# Inline Telegram (don't source backup_telegram_alerts.sh — it installs conflicting EXIT trap)
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-8342176349:AAF-rbQlHceG-DO21EQcUyQe7aoVc0egj38}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-186497598}"
send_telegram() {
    curl -sf --max-time 15 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" -d text="$1" -d parse_mode="Markdown" > /dev/null 2>&1 || true
}
TEST_DB="shopware_restore_verify"
RESULT=""
FAILED=false

HOURLY_DIR=/root/backups/hourly
LATEST_DB=$(ls -t "$HOURLY_DIR"/db_*.sql.gz 2>/dev/null | head -1)

if [ -z "$LATEST_DB" ]; then
    send_telegram "🔴 restore_verify on ${HOSTLABEL}: NO backup files found in $HOURLY_DIR"
    exit 1
fi

echo "=== Restore verify on $HOSTLABEL ==="
echo "Source: $LATEST_DB ($(du -h "$LATEST_DB" | cut -f1))"

# --- Detect environment: native MySQL (biretos.ae) or Dockware (dev) ---
# Need root-level access to CREATE/DROP DATABASE. shopware user only has privileges on its own DB.
if mysql --no-defaults --socket=/var/run/mysqld/mysqld.sock -uroot -e "SELECT 1" > /dev/null 2>&1; then
    MODE=native
    MYSQL_CMD="mysql --no-defaults --socket=/var/run/mysqld/mysqld.sock -uroot"
elif docker ps --format '{{.Names}}' | grep -q '^shopware$'; then
    MODE=dockware
    MYSQL_CMD="docker exec -i shopware mysql -h127.0.0.1 -uroot -proot"
else
    send_telegram "🔴 restore_verify on ${HOSTLABEL}: cannot detect MySQL access mode"
    exit 1
fi

echo "Mode: $MODE"

# --- Create test DB ---
$MYSQL_CMD -e "DROP DATABASE IF EXISTS $TEST_DB; CREATE DATABASE $TEST_DB;" 2>/dev/null

# --- Restore ---
echo "Restoring into $TEST_DB..."
START=$(date +%s)
if gunzip < "$LATEST_DB" | $MYSQL_CMD "$TEST_DB" 2>/tmp/restore.err; then
    ELAPSED=$(($(date +%s) - START))
    echo "Restore OK in ${ELAPSED}s"
else
    FAILED=true
    RESULT="Restore FAILED: $(cat /tmp/restore.err | head -c 500)"
    echo "$RESULT"
fi
rm -f /tmp/restore.err

# --- Verify ---
if [ "$FAILED" = false ]; then
    TABLE_COUNT=$($MYSQL_CMD "$TEST_DB" -Nse "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$TEST_DB'")
    PRODUCT_COUNT=$($MYSQL_CMD "$TEST_DB" -Nse "SELECT COUNT(*) FROM product" 2>/dev/null || echo "N/A")
    CATEGORY_COUNT=$($MYSQL_CMD "$TEST_DB" -Nse "SELECT COUNT(*) FROM category" 2>/dev/null || echo "N/A")

    echo "Tables: $TABLE_COUNT"
    echo "Products: $PRODUCT_COUNT"
    echo "Categories: $CATEGORY_COUNT"

    if [ "$TABLE_COUNT" -lt 10 ]; then
        FAILED=true
        RESULT="Schema missing — only $TABLE_COUNT tables restored"
    elif [ "$PRODUCT_COUNT" != "N/A" ] && [ "$PRODUCT_COUNT" -lt 1 ]; then
        # 0 products — suspicious but not necessarily a failure (fresh install)
        RESULT="WARN: 0 products in restored DB (tables=$TABLE_COUNT). OK if fresh install."
    else
        RESULT="OK: tables=$TABLE_COUNT products=$PRODUCT_COUNT categories=$CATEGORY_COUNT"
    fi
fi

# --- Cleanup test DB ---
$MYSQL_CMD -e "DROP DATABASE IF EXISTS $TEST_DB;" 2>/dev/null

# --- Report ---
if [ "$FAILED" = true ]; then
    send_telegram "🔴 restore_verify on ${HOSTLABEL}: FAILED

File: \`${LATEST_DB##*/}\`
Error: ${RESULT}"
    exit 1
else
    send_telegram "✅ restore_verify on ${HOSTLABEL}: $RESULT

File: \`${LATEST_DB##*/}\` ($(du -h "$LATEST_DB" | cut -f1))"
    exit 0
fi

#!/bin/bash
# usa_vps_ping_monitor.sh — notify when biretos.ae (216.9.227.124) returns online
# Runs on Russia VPS. Pings USA every 2 min; when first successful reply after
# downtime, sends single Telegram alert and marks monitor as "done".
#
# Install as cron: */2 * * * * /root/usa_vps_ping_monitor.sh

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-8342176349:AAF-rbQlHceG-DO21EQcUyQe7aoVc0egj38}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-186497598}"
TARGET_IP=216.9.227.124
TARGET_NAME=biretos.ae
STATE_FILE=/var/lib/misc/usa_vps_ping_state

tg() {
    curl -sf --max-time 15 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" -d text="$1" -d parse_mode="Markdown" > /dev/null 2>&1 || true
}

mkdir -p "$(dirname "$STATE_FILE")"

# Current state: alive or dead
if ping -c 2 -W 3 "$TARGET_IP" > /dev/null 2>&1; then
    CURRENT=alive
else
    CURRENT=dead
fi

# Previous state
PREV=$(cat "$STATE_FILE" 2>/dev/null || echo unknown)

# Transition handling
if [ "$PREV" = "dead" ] && [ "$CURRENT" = "alive" ]; then
    tg "✅ ${TARGET_NAME} BACK ONLINE (IP ${TARGET_IP})

First successful ping after downtime. SSH should be available shortly. backup.sh cron will resume on its next tick."
elif [ "$PREV" = "alive" ] && [ "$CURRENT" = "dead" ]; then
    tg "🔴 ${TARGET_NAME} WENT OFFLINE (IP ${TARGET_IP})

Ping failed. Will notify on recovery."
fi

echo "$CURRENT" > "$STATE_FILE"

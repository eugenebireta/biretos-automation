#!/bin/bash
# Biretos backup telegram alerting — source this at top of backup.sh
# Requires: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env vars OR defaults below

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-8342176349:AAF-rbQlHceG-DO21EQcUyQe7aoVc0egj38}"  # @bireta_code_bot
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-186497598}"
BACKUP_HOST="${BACKUP_HOST:-$(hostname)}"
BACKUP_LOG="/tmp/backup_run_$$.log"

# Mirror all stdout+stderr of the script into a log file (for trap)
exec > >(tee -a "$BACKUP_LOG") 2>&1

send_telegram() {
    local msg="$1"
    curl -sf --max-time 15 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d text="${msg}" \
        -d parse_mode="Markdown" > /dev/null 2>&1
}

backup_finish_handler() {
    local ec=$?
    local last_lines
    last_lines=$(tail -20 "$BACKUP_LOG" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' || echo "no-log")
    if [ $ec -ne 0 ]; then
        send_telegram "🔴 BACKUP FAILED on ${BACKUP_HOST} (exit=${ec})

Last lines:
\`\`\`
${last_lines}
\`\`\`"
    fi
    rm -f "$BACKUP_LOG"
}
trap backup_finish_handler EXIT

# Disk space pre-check
DISK_PCT_USED=$(df / | awk 'NR==2 {print int($5)}' | tr -d %)
if [ "$DISK_PCT_USED" -gt 85 ]; then
    send_telegram "🟡 Disk warning on ${BACKUP_HOST}: ${DISK_PCT_USED}% used (< 15% free). Backup may fail soon."
fi

# Anomaly detection: backup size change detection (called AFTER backup completes)
backup_size_check() {
    local name="$1"
    local file="$2"
    local history_file="/root/backups/.size_history_${name}"
    [ ! -f "$file" ] && return
    local cur_size=$(stat -c%s "$file" 2>/dev/null || echo 0)
    [ "$cur_size" -eq 0 ] && return
    if [ -f "$history_file" ]; then
        local prev_size=$(cat "$history_file")
        if [ "$prev_size" -gt 0 ]; then
            local ratio=$((cur_size * 100 / prev_size))
            if [ "$ratio" -lt 50 ] || [ "$ratio" -gt 300 ]; then
                send_telegram "🟡 Anomaly: ${name} backup on ${BACKUP_HOST} size changed ${prev_size}→${cur_size} bytes (${ratio}%). Possible corruption or bloat."
            fi
        fi
    fi
    echo "$cur_size" > "$history_file"
}

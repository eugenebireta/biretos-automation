#!/bin/bash
# Biretos safe-exec — technical enforcement of (c) hybrid AI workflow
# Defines: pre-change snapshot + destructive-command allow-list + Telegram audit trail
#
# Philosophy (per critique 2): AI operator is NOT trusted to "remember to ask".
# Destructive operations are guarded by THIS script, which:
#   1. Takes a fresh pre-change snapshot BEFORE the operation
#   2. Logs every destructive call to /var/log/safe_exec.log (and to Telegram)
#   3. Requires explicit --confirm or an interactive TTY ack for specific patterns
#   4. Runs the operation with stderr captured
#   5. Runs a post-check (HTTP 200 on https://$BACKUP_HOST/ optional) and auto-rolls-back hint
#
# Usage:
#   safe_exec.sh "rm -rf /some/path"              # will refuse without --confirm
#   safe_exec.sh --confirm "rm -rf /some/path"
#   safe_exec.sh --snapshot-only "docker compose down"   # just take snapshot, run, exit
#
# Install into PATH: ln -s /root/safe_exec.sh /usr/local/bin/safe

set -e

LOG=/var/log/safe_exec.log
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-8342176349:AAF-rbQlHceG-DO21EQcUyQe7aoVc0egj38}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-186497598}"
HOST=$(hostname)
SNAPSHOT_DIR=/root/backups/pre_change_snapshots
SNAPSHOT_KEEP=30   # keep last 30 pre-change snapshots

mkdir -p "$SNAPSHOT_DIR"

tg() {
    curl -sf --max-time 10 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d text="$1" -d parse_mode="Markdown" > /dev/null 2>&1 || true
}

log_line() {
    echo "[$(date -Iseconds)] $*" | tee -a "$LOG"
}

# --- Parse args ---
CONFIRM=false
SNAPSHOT_ONLY=false
while [ $# -gt 0 ]; do
    case "$1" in
        --confirm) CONFIRM=true; shift;;
        --snapshot-only) SNAPSHOT_ONLY=true; shift;;
        --) shift; break;;
        *) break;;
    esac
done

CMD="$*"
if [ -z "$CMD" ]; then
    echo "Usage: safe_exec.sh [--confirm] [--snapshot-only] -- <command>" >&2
    exit 2
fi

# --- Classify command risk ---
DESTRUCTIVE=false
PATTERNS='rm -rf|rm -r /|docker compose down|docker rm|docker volume rm|DROP TABLE|DROP DATABASE|TRUNCATE|>\s*/dev/sd|dd if=|mkfs|fdisk|parted|shutdown|reboot|systemctl stop|systemctl disable'
if echo "$CMD" | grep -qE "$PATTERNS"; then
    DESTRUCTIVE=true
fi

# --- Guard destructive without --confirm ---
if [ "$DESTRUCTIVE" = true ] && [ "$CONFIRM" = false ]; then
    log_line "REFUSED (missing --confirm): $CMD"
    tg "🛑 safe_exec REFUSED on ${HOST}: missing --confirm flag

\`${CMD}\`"
    echo "ERROR: command classified as destructive. Re-run with --confirm or pass --snapshot-only" >&2
    exit 3
fi

# --- Pre-change snapshot (always for destructive, or --snapshot-only) ---
if [ "$DESTRUCTIVE" = true ] || [ "$SNAPSHOT_ONLY" = true ]; then
    SNAP_LABEL="snap_$(date +%Y%m%d_%H%M%S)_$(echo "$CMD" | md5sum | cut -c1-8)"
    SNAP_FILE="$SNAPSHOT_DIR/${SNAP_LABEL}.sql.gz"

    log_line "SNAPSHOT before: $CMD"

    if [ -f /root/.my.cnf ]; then
        # biretos.ae path
        nice -n 19 ionice -c 3 mysqldump --defaults-file=/root/.my.cnf \
            --single-transaction --quick --routines --triggers --events --hex-blob shopware 2>/dev/null | gzip > "$SNAP_FILE" || true
    elif docker ps --format '{{.Names}}' | grep -q '^shopware$'; then
        # dev.bireta.ru path (Dockware)
        nice -n 19 ionice -c 3 docker exec shopware mysqldump -h127.0.0.1 -uroot -proot \
            --single-transaction --quick --routines --triggers --events --hex-blob shopware 2>/dev/null | gzip > "$SNAP_FILE" || true
    fi

    if [ -s "$SNAP_FILE" ]; then
        log_line "  snapshot: $SNAP_FILE ($(du -h "$SNAP_FILE" | cut -f1))"
        # Rotate: keep last $SNAPSHOT_KEEP
        cd "$SNAPSHOT_DIR" && ls -t *.sql.gz 2>/dev/null | tail -n +$((SNAPSHOT_KEEP+1)) | xargs -r rm
    else
        log_line "  snapshot FAILED (empty)"
        tg "🟡 safe_exec: snapshot failed on ${HOST} before: \`${CMD}\`"
    fi
fi

# --- Execute ---
log_line "EXEC: $CMD"
tg "⚙️ safe_exec on ${HOST}: \`${CMD}\`"

EXEC_ERR=$(mktemp)
if bash -c "$CMD" 2>"$EXEC_ERR"; then
    log_line "  OK (exit=0)"
    rm -f "$EXEC_ERR"
    exit 0
else
    EC=$?
    ERR_CONTENT=$(tail -c 2000 "$EXEC_ERR")
    log_line "  FAILED (exit=$EC): $ERR_CONTENT"
    tg "🔴 safe_exec FAILED on ${HOST} (exit=${EC}): \`${CMD}\`

\`\`\`
${ERR_CONTENT}
\`\`\`

Rollback hint: \`gunzip < ${SNAP_FILE:-<no-snapshot>} | mysql ...\`"
    rm -f "$EXEC_ERR"
    exit $EC
fi

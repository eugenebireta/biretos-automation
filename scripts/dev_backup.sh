#!/bin/bash
# Biretos Smart Backup System — dev.bireta.ru edition (Dockware-specific)
# Runs on Russia VPS 77.233.222.214. Adapted from biretos.ae v2 but:
#   - MySQL via `docker exec shopware mysqldump` (in-container)
#   - Media is inside shopware_shopware_files docker volume → tar via helper container
#   - Custom fields (bundle metadata) are inside DB, no special handling needed
#   - rsync offsite goes to biretos.ae (USA) — mirror direction of USA→RU

set -e

BACKUP_HOST=dev.bireta.ru
source /root/backup_telegram_alerts.sh

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

BACKUP_ROOT="/root/backups"
HOURLY_DIR="$BACKUP_ROOT/hourly"
DAILY_DIR="$BACKUP_ROOT/daily"
WEEKLY_DIR="$BACKUP_ROOT/weekly"
MONTHLY_DIR="$BACKUP_ROOT/monthly"
MILESTONE_DIR="$BACKUP_ROOT/milestone"
CONTAINER=shopware
VOLUME_FILES=shopware_shopware_files

mkdir -p "$HOURLY_DIR" "$DAILY_DIR" "$WEEKLY_DIR" "$MONTHLY_DIR" "$MILESTONE_DIR"

DATE=$(date +%Y%m%d_%H%M%S)
HOUR=$(date +%H)
DAY=$(date +%u)
DAY_OF_MONTH=$(date +%d)

echo -e "${GREEN}=== Dev Backup System (Dockware) ===${NC}"
echo "Time: $(date)"

# --- Pre-flight: container running? ---
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo -e "${RED}! Container '$CONTAINER' not running — abort${NC}"
    send_telegram "🔴 dev.bireta.ru backup ABORT: container $CONTAINER not running"
    exit 1
fi

# --- DB change detection ---
CURRENT_DB_HASH=$(docker exec "$CONTAINER" mysqldump -h127.0.0.1 -uroot -proot --single-transaction --quick --skip-dump-date shopware 2>/dev/null | md5sum | cut -d' ' -f1)
LAST_DB_HASH_FILE="$BACKUP_ROOT/.last_db_hash"
if [ -f "$LAST_DB_HASH_FILE" ] && [ "$CURRENT_DB_HASH" = "$(cat $LAST_DB_HASH_FILE)" ]; then
    DB_CHANGED=false
    echo -e "${BLUE}- No changes in DB${NC}"
else
    DB_CHANGED=true
    echo -e "${YELLOW}+ Changes in DB${NC}"
fi

# NOTE: dev.bireta.ru media (~6.5 GB) is NOT backed up hourly — too much disk churn.
# Media is captured once per day during the 23:00 daily promotion step below.
# Thumbnails excluded (regenerable via Shopware `bin/console media:generate-thumbnails`).

# --- Pre-flight disk space check ---
DISK_USED_PCT=$(df / | awk 'NR==2 {print int($5)}' | tr -d %)
if [ "$DISK_USED_PCT" -gt 90 ]; then
    send_telegram "🔴 dev_backup ABORT on ${BACKUP_HOST}: disk ${DISK_USED_PCT}%% used (need <90%%)"
    echo -e "${RED}! Disk ${DISK_USED_PCT}%% full — abort${NC}"
    exit 1
fi

if [ "$DB_CHANGED" = false ]; then
    echo -e "${GREEN}- DB unchanged, skipping hourly dump${NC}"
else
    echo -e "\n${YELLOW}Creating hourly backup...${NC}"

    TMP_ERR=$(mktemp)
    if nice -n 19 ionice -c 3 docker exec "$CONTAINER" mysqldump -h127.0.0.1 -uroot -proot \
        --single-transaction --quick --routines --triggers --events --hex-blob shopware 2>"$TMP_ERR" | gzip > "$HOURLY_DIR/db_$DATE.sql.gz"; then
        if [ -s "$TMP_ERR" ] && grep -qi "error" "$TMP_ERR"; then
            echo -e "${RED}MySQL dump had errors: $(cat $TMP_ERR)${NC}"
            rm -f "$HOURLY_DIR/db_$DATE.sql.gz" "$TMP_ERR"
            exit 1
        fi
        rm -f "$TMP_ERR"
        echo "$CURRENT_DB_HASH" > "$LAST_DB_HASH_FILE"
        echo "  MySQL: $(du -h $HOURLY_DIR/db_$DATE.sql.gz | cut -f1)"
    else
        echo -e "${RED}mysqldump failed${NC}"
        rm -f "$TMP_ERR"
        exit 1
    fi
fi

# Media: daily-only (heavy: ~6 GB for dev) — triggered in promotion step below
MEDIA_CHANGED=false  # placeholder — actual media work in daily promotion
LAST_MEDIA_HASH_FILE="$BACKUP_ROOT/.last_media_hash"
CURRENT_MEDIA_HASH="$(cat $LAST_MEDIA_HASH_FILE 2>/dev/null || echo none)"

# --- Rotation: hourly 24 DB only ---
cd "$HOURLY_DIR"
ls -t db_*.sql.gz 2>/dev/null | tail -n +25 | xargs -r rm

# --- Promotion: daily at 23:00 (or first run if daily empty) ---
NEED_DAILY=false
if [ "$HOUR" = "23" ]; then NEED_DAILY=true; fi
if [ -z "$(ls -A $DAILY_DIR 2>/dev/null | grep 'media_')" ]; then NEED_DAILY=true; fi

if [ "$NEED_DAILY" = true ]; then
    # DB: copy latest hourly to daily
    [ "$DB_CHANGED" = true ] && L=$(ls -t "$HOURLY_DIR"/db_*.sql.gz 2>/dev/null | head -1) && [ -n "$L" ] && cp "$L" "$DAILY_DIR/db_$(date +%Y%m%d).sql.gz"

    # Media: STREAM directly to USA VPS (no local file — dev disk is too small for 6+ GB tar)
    # PRE-CHECK: USA reachable? If not, skip media step (don't hang waiting for SSH timeout)
    if ping -c 1 -W 3 216.9.227.124 > /dev/null 2>&1; then
        HASH_NOW=$(docker run --rm -v "$VOLUME_FILES":/data:ro alpine \
            sh -c "find /data/public/media -type f -printf '%T@ %s %p\n' 2>/dev/null | sort | md5sum" | cut -d' ' -f1)
        if [ "$HASH_NOW" != "$CURRENT_MEDIA_HASH" ]; then
            echo "  Streaming media tar directly to USA (no local copy for dev)..."
            TARGET_FILENAME="media_$(date +%Y%m%d).tar.gz"
            if nice -n 19 ionice -c 3 docker run --rm -v "$VOLUME_FILES":/data:ro alpine \
                tar czf - -C /data public/media 2>/tmp/tarmedia.err | \
                ssh -i /root/.ssh/id_media_stream_to_usa \
                    -o BatchMode=yes -o StrictHostKeyChecking=yes \
                    -o ConnectTimeout=15 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
                    root@216.9.227.124; then
                echo "$HASH_NOW" > "$LAST_MEDIA_HASH_FILE"
                echo -e "${GREEN}  Media streamed to USA OK${NC}"
            else
                echo -e "${RED}! Media stream failed${NC}"
                send_telegram "🔴 dev_backup: media stream to USA failed"
            fi
            rm -f /tmp/tarmedia.err
        else
            echo "  Media unchanged — skip"
        fi
    else
        echo -e "${YELLOW}  USA unreachable — skip media backup (will retry next cycle)${NC}"
        send_telegram "🟡 dev_backup: media backup skipped — USA VPS unreachable"
    fi

    # Daily rotation: keep 7 DB, 3 media (heavy)
    cd "$DAILY_DIR"
    find . -name "db_*.sql.gz" -mtime +7 -delete
    ls -t media_*.tar.gz 2>/dev/null | tail -n +4 | xargs -r rm
fi

# --- Promotion: weekly (Sunday 23:00) ---
if [ "$DAY" = "7" ] && [ "$HOUR" = "23" ]; then
    L=$(ls -t "$DAILY_DIR"/db_*.sql.gz 2>/dev/null | head -1); [ -n "$L" ] && cp "$L" "$WEEKLY_DIR/db_week_$(date +%Y_W%V).sql.gz"
    L=$(ls -t "$DAILY_DIR"/media_*.tar.gz 2>/dev/null | head -1); [ -n "$L" ] && cp "$L" "$WEEKLY_DIR/media_week_$(date +%Y_W%V).tar.gz"
    cd "$WEEKLY_DIR"
    find . \( -name "db_*.sql.gz" -o -name "media_*.tar.gz" \) -mtime +28 -delete
fi

# --- Promotion: monthly (last day 23:00) ---
if [ "$DAY_OF_MONTH" = "$(date -d "$(date +%Y-%m-01) +1 month -1 day" +%d)" ] && [ "$HOUR" = "23" ]; then
    L=$(ls -t "$WEEKLY_DIR"/db_*.sql.gz 2>/dev/null | head -1); [ -n "$L" ] && cp "$L" "$MONTHLY_DIR/db_$(date +%Y_%m).sql.gz"
    L=$(ls -t "$WEEKLY_DIR"/media_*.tar.gz 2>/dev/null | head -1); [ -n "$L" ] && cp "$L" "$MONTHLY_DIR/media_$(date +%Y_%m).tar.gz"
fi

echo -e "${GREEN}+ Dev backup completed${NC}"
echo "Storage:"
echo "  Hourly:  DB=$(ls -1 $HOURLY_DIR/db_*.sql.gz 2>/dev/null | wc -l)"
echo "  Daily:   DB=$(ls -1 $DAILY_DIR/db_*.sql.gz 2>/dev/null | wc -l) Media=$(ls -1 $DAILY_DIR/media_*.tar.gz 2>/dev/null | wc -l)"
echo "  Weekly:  DB=$(ls -1 $WEEKLY_DIR/db_*.sql.gz 2>/dev/null | wc -l) Media=$(ls -1 $WEEKLY_DIR/media_*.tar.gz 2>/dev/null | wc -l)"
echo "  Monthly: DB=$(ls -1 $MONTHLY_DIR/db_*.sql.gz 2>/dev/null | wc -l) Media=$(ls -1 $MONTHLY_DIR/media_*.tar.gz 2>/dev/null | wc -l)"

# --- OFFSITE: rsync to biretos.ae USA (dev-specific subdir) ---
# Pre-check: skip gracefully if USA unreachable (don't hang)
if ping -c 1 -W 3 216.9.227.124 > /dev/null 2>&1; then
    RSYNC_ERR=$(mktemp)
    if nice -n 19 ionice -c 3 rsync -az --delete \
        -e "ssh -i /root/.ssh/id_backup_to_usa -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15" \
        "$BACKUP_ROOT/" root@216.9.227.124: 2>"$RSYNC_ERR"; then
        echo -e "${GREEN}+ Offsite rsync to biretos.ae OK${NC}"
    else
        echo -e "${RED}! Offsite rsync FAILED: $(cat $RSYNC_ERR)${NC}"
        send_telegram "🔴 dev_backup: offsite rsync to USA failed: $(cat $RSYNC_ERR | head -c 300)"
    fi
    rm -f "$RSYNC_ERR"
else
    echo -e "${YELLOW}- Offsite rsync skipped: USA unreachable${NC}"
fi

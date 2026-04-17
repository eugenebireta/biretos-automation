#!/bin/bash
# accept_media_stream.sh — runs on USA VPS as SSH forced command
# Accepts gzipped tar stream on stdin, validates, stores with date-stamped filename
#
# Called by dev.bireta.ru via ssh with an authorized_keys command= entry like:
#   command="/root/accept_media_stream.sh",restrict,from="77.233.222.214" ssh-ed25519 KEY
#
# Usage from caller: `tar ... | ssh root@USA` (no arguments needed)

set -e

TARGET_DIR=/root/backups_dev/daily
mkdir -p "$TARGET_DIR"

TMP="$TARGET_DIR/media_incoming_$$.tar.gz"
FINAL="$TARGET_DIR/media_$(date +%Y%m%d).tar.gz"

# Read from stdin, write to tmp
cat > "$TMP"

# Validate gzip integrity before promoting
if ! gzip -t "$TMP" 2>/dev/null; then
    echo "ERROR: received file failed gzip integrity check" >&2
    rm -f "$TMP"
    exit 1
fi

# Check non-trivial size (>1MB = real tar, not empty/error)
SIZE=$(stat -c%s "$TMP")
if [ "$SIZE" -lt 1048576 ]; then
    echo "ERROR: received file too small ($SIZE bytes)" >&2
    rm -f "$TMP"
    exit 1
fi

mv "$TMP" "$FINAL"
echo "OK: received $SIZE bytes into $FINAL"

# Rotation: keep last 3 daily media files
cd "$TARGET_DIR"
ls -t media_*.tar.gz 2>/dev/null | tail -n +4 | xargs -r rm

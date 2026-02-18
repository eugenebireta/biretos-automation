#!/bin/bash
set -euo pipefail

CONFIG_FILE="${1:-}"
TARGET_PATH="/usr/local/etc/xray/config.json"

if [[ -z "${CONFIG_FILE}" ]]; then
  echo "Usage: $0 /path/to/config.json"
  exit 1
fi

if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "ERROR: Config file not found: ${CONFIG_FILE}"
  exit 1
fi

umask 077
install -d "$(dirname "${TARGET_PATH}")"

TMP_FILE="$(mktemp /tmp/xray-config.XXXXXX.json)"
cp "${CONFIG_FILE}" "${TMP_FILE}"

mv "${TMP_FILE}" "${TARGET_PATH}"
chmod 640 "${TARGET_PATH}"
chown nobody:nogroup "${TARGET_PATH}"

systemctl enable xray >/dev/null 2>&1 || true
systemctl restart xray

sleep 2
systemctl status --no-pager xray


#!/bin/bash
# Deploy WireGuard configuration safely.
#
# Usage: deploy-wg-config.sh /tmp/wg0.conf

set -euo pipefail

CONFIG_FILE="${1:-}"
TARGET_PATH="/etc/wireguard/wg0.conf"

if [[ -z "${CONFIG_FILE}" ]]; then
  echo "Usage: $0 /path/to/wg0.conf"
  exit 1
fi

if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "ERROR: Config file not found: ${CONFIG_FILE}"
  exit 1
fi

# Normalize line endings and strip UTF-8 BOM if present.
perl -pi -e 's/\r$//' "${CONFIG_FILE}"
if [[ "$(head -c 3 "${CONFIG_FILE}")" == $'\xEF\xBB\xBF' ]]; then
  tail -c +4 "${CONFIG_FILE}" > "${CONFIG_FILE}.nobom"
  mv "${CONFIG_FILE}.nobom" "${CONFIG_FILE}"
fi

umask 077
mkdir -p /etc/wireguard

if [[ -f "${TARGET_PATH}" ]]; then
  cp "${TARGET_PATH}" "${TARGET_PATH}.backup.$(date +%s)"
fi

cp "${CONFIG_FILE}" "${TARGET_PATH}"
chmod 600 "${TARGET_PATH}"

systemctl enable wg-quick@wg0 >/dev/null 2>&1 || true
systemctl restart wg-quick@wg0

sleep 2
if ip addr show wg0 >/dev/null 2>&1; then
  echo "SUCCESS: WireGuard interface wg0 is UP"
  ip addr show wg0
  wg show
else
  echo "ERROR: WireGuard interface wg0 failed to start"
  exit 1
fi


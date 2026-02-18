#!/bin/bash
# WireGuard key generation script
# Safe for remote execution via Upload & Execute pattern
set -euo pipefail

SERVER_NAME="${1:-server}"
OUTPUT_FILE="/tmp/wg-keys-${SERVER_NAME}.json"
KEY_DIR="/etc/wireguard"

umask 077
mkdir -p "${KEY_DIR}"

PRIVATE_KEY=$(wg genkey)
PUBLIC_KEY=$(echo "${PRIVATE_KEY}" | wg pubkey)

echo "${PRIVATE_KEY}" > "${KEY_DIR}/${SERVER_NAME}-private.key"
echo "${PUBLIC_KEY}" > "${KEY_DIR}/${SERVER_NAME}-public.key"

cat > "${OUTPUT_FILE}" <<EOF
{
  "server": "${SERVER_NAME}",
  "private_key": "${PRIVATE_KEY}",
  "public_key": "${PUBLIC_KEY}",
  "private_key_path": "${KEY_DIR}/${SERVER_NAME}-private.key",
  "public_key_path": "${KEY_DIR}/${SERVER_NAME}-public.key",
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo "SUCCESS: Keys generated"
echo "Output: ${OUTPUT_FILE}"
cat "${OUTPUT_FILE}"










#!/bin/bash
# Ensure IP forwarding is enabled for WireGuard server.
set -euo pipefail

CONF_PATH="/etc/sysctl.d/99-wireguard-forward.conf"

cat <<'EOF' > "${CONF_PATH}"
net.ipv4.ip_forward=1
net.ipv6.conf.all.forwarding=1
EOF

sysctl -p "${CONF_PATH}"
echo "Updated ${CONF_PATH}"










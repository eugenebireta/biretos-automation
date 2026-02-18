#!/bin/bash
set -euo pipefail

CONF_PATH="/etc/sysctl.d/99-wireguard-forward.conf"

cat <<'EOF' > "${CONF_PATH}"
net.ipv4.ip_forward=1
net.ipv6.conf.all.forwarding=1
net.ipv4.conf.all.forwarding=1
net.ipv4.conf.eth0.forwarding=1
net.ipv4.conf.wg0.forwarding=1
net.ipv4.conf.all.rp_filter=0
net.ipv4.conf.eth0.rp_filter=0
net.ipv4.conf.wg0.rp_filter=0
EOF

sysctl -p "${CONF_PATH}"
echo "rp_filter disabled for wg0/eth0 (persisted)."


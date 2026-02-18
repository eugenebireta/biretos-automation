#!/bin/bash
set -euo pipefail

LOG_FILE="/tmp/install_wireguard_tools.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "=== Installing wireguard-tools ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y wireguard wireguard-tools

echo "Installation finished."
echo "wg version:"
if command -v wg >/dev/null 2>&1; then
  wg --version
else
  echo "wg not found even after installation."
fi










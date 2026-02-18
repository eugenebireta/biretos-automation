#!/bin/bash
set -euo pipefail

LOG_FILE="/tmp/install_xray.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "=== Installing Xray (or verifying existing install) ==="

if command -v xray >/dev/null 2>&1; then
  echo "Xray already installed:"
  xray --version
  exit 0
fi

TMP_SCRIPT="$(mktemp /tmp/xray-install.XXXXXX.sh)"
curl -fsSL https://github.com/XTLS/Xray-install/raw/main/install-release.sh -o "${TMP_SCRIPT}"
chmod +x "${TMP_SCRIPT}"

bash "${TMP_SCRIPT}" install
rm -f "${TMP_SCRIPT}"

echo "Installation finished."
xray --version || true










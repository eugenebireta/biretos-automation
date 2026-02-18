#!/bin/bash
# Run curl via Xray user to verify tunnel exit IP.
set -euo pipefail

LOG="/tmp/remote_curl_test.log"
TARGET_URL="https://ifconfig.me"
RUN_USER="root"

CMD=(curl --interface wg0 -4 -s -S -w "\nHTTP:%{http_code}" --max-time 10 "${TARGET_URL}")

{
  echo "=== remote_curl_test $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "User: ${RUN_USER}"
  echo "Target: ${TARGET_URL}"
  echo "Command: ${CMD[*]}"
  echo
  "${CMD[@]}"
} | tee "${LOG}"

echo "Log saved to ${LOG}"


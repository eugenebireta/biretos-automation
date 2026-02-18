#!/bin/bash
set -euo pipefail

ENV_FILE="/root/tbank-env"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/root/tbank-env
  set -a
  source "$ENV_FILE"
  set +a
fi

: "${TBANK_TOKEN:?TBANK_TOKEN is required}"

# Allows overriding base URL per run without editing /root/tbank-env
TBANK_API_URL="${TBANK_API_URL_OVERRIDE:-${TBANK_API_URL:-https://api.tbank.ru}}"

curl_args=(
  -sS
  -w "\nHTTP_CODE:%{http_code}\n"
  -H "Authorization: Bearer ${TBANK_TOKEN}"
  -H "Accept: application/json"
  --connect-timeout 5
  --max-time 20
)

fetch_endpoint() {
  local endpoint="$1"
  local url="${TBANK_API_URL%/}${endpoint}"
  echo ""
  echo ">>> GET ${url}"
  if ! response=$(curl "${curl_args[@]}" "$url"); then
    echo "[ERROR] curl failed for ${url}"
  else
    echo "${response}"
  fi
  echo "---"
}

fetch_endpoint "/v1/invoices?limit=3&status=paid"
fetch_endpoint "/v1/consignments?limit=3&status=paid"



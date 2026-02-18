#!/bin/bash
set -euo pipefail

ENV_FILE="/root/tbank-env"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/root/tbank-env
  set -a
  source "$ENV_FILE"
  set +a
fi

: "${TBANK_API_URL:?TBANK_API_URL is not set}"
: "${TBANK_TOKEN:?TBANK_TOKEN is not set}"

declare -a endpoints=(
  "/v1/company"
  "/v1/bank-statement"
  "/v1/statement"
  "/v1/invoices"
  "/v1/consignments"
)

curl_args=(
  -sS
  -w "\nHTTP_CODE:%{http_code}"
  -H "Authorization: Bearer ${TBANK_TOKEN}"
  -H "Accept: application/json"
  --connect-timeout 5
  --max-time 20
)

for ep in "${endpoints[@]}"; do
  url="${TBANK_API_URL}${ep}"
  echo ""
  echo "[TEST] GET ${url}"
  if ! response=$(curl "${curl_args[@]}" "$url"); then
    echo "[ERROR] curl failed for ${url}"
  else
    echo "$response"
  fi
  echo "---"
done














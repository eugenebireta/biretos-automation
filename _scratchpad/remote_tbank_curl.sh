#!/bin/bash
set -euo pipefail
set -a
source /root/tbank-env
endpoints=(
  /v1/company
  /v1/bank-statement
  /v1/statement
  /v1/invoices
  /v1/consignments
)
for ep in " \; do
 echo 
  echo [test] GET 
  curl -s -w \\nHTTP_STATUS:% -encodedCommand aAB0AHQAcABfAGMAbwBkAGUA \\n -H Authorization: Bearer  -H Accept: application/json  || true
  echo 
done
EOF -inputFormat xml -outputFormat text

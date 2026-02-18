#!/bin/bash
# Measure latency to critical Cursor endpoints via WireGuard tunnel.
set -euo pipefail

ENDPOINTS=(
  "https://ifconfig.me"
  "https://api2.cursor.sh"
  "https://metrics.cursor.sh"
)
ITERATIONS=5
LOG="/tmp/latency_benchmark.log"

{
  echo "=== Cursor Bridge Latency Benchmark ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="
  echo "Interface: wg0"
  echo "Iterations per endpoint: ${ITERATIONS}"
  echo

  for endpoint in "${ENDPOINTS[@]}"; do
    echo "Endpoint: ${endpoint}"
    total=0
    max=0
    min=999
    success=0
    for i in $(seq 1 "${ITERATIONS}"); do
      result=$(curl --interface wg0 -s -o /dev/null -w "%{http_code} %{time_total}" "${endpoint}" || echo "000 0")
      code=$(awk '{print $1}' <<< "${result}")
      time=$(awk '{print $2}' <<< "${result}")
      printf "  #%d -> code=%s time=%.3fs\n" "${i}" "${code}" "${time}"
      if [[ "${code}" =~ ^2|3|4 ]]; then
        success=$((success + 1))
        total=$(awk "BEGIN {print ${total} + ${time}}")
        if (( $(echo "${time} > ${max}" | bc -l) )); then
          max=${time}
        fi
        if (( $(echo "${time} < ${min}" | bc -l) )); then
          min=${time}
        fi
      fi
    done
    if [[ "${success}" -gt 0 ]]; then
      avg=$(awk "BEGIN {print ${total} / ${success}}")
      printf "  ==> success=%d/%d | avg=%.3fs | min=%.3fs | max=%.3fs\n" "${success}" "${ITERATIONS}" "${avg}" "${min}" "${max}"
    else
      echo "  ==> all attempts failed"
    fi
    echo
  done
} | tee "${LOG}"

echo "Results saved to ${LOG}"










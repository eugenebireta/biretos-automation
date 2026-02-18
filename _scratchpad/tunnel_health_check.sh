#!/bin/bash
set -euo pipefail

LOG="/tmp/tunnel_health_check.log"
{
  echo "=== Tunnel Health Check ($(date -u)) ==="
  echo "IP route:"
  ip route
  echo ""

  echo "WireGuard status:"
  if command -v wg >/dev/null 2>&1; then
    wg show
  else
    echo "wg command not found"
  fi
  echo ""

  echo "Ping USA endpoint (10.99.99.1):"
  ping -c 3 -W 1 10.99.99.1 || echo "Ping failed"

  echo ""
  WG_ADDR=$(ip -o -4 addr show dev wg0 2>/dev/null | awk '{print $4}')
  if [[ "${WG_ADDR}" == "10.99.99.1/24" ]]; then
    echo "Exit node detected (wg0=10.99.99.1) — skipping curl test."
  else
    if ip route get 216.58.209.14 2>/dev/null | grep -q 'dev wg0'; then
      echo "curl via wg0 (http://216.58.209.14):"
      if command -v curl >/dev/null 2>&1; then
        curl --interface wg0 -s --max-time 10 http://216.58.209.14 || echo "curl failed"
      else
        echo "curl command not found"
      fi
    else
      echo "No route for 216.58.209.14 via wg0 — skipping curl test."
    fi
  fi
} > "${LOG}" 2>&1

echo "${LOG}"


#!/bin/bash
set -euo pipefail
{
  echo "hostname: $(hostname)"
  echo -n "wg path: "
  if command -v wg >/dev/null 2>&1; then
    command -v wg
  else
    echo "NOT_FOUND"
  fi
} > /tmp/check_wg.out










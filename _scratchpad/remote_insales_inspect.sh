#!/usr/bin/env bash
set -euo pipefail

SHOP="${1:-biretos.myinsales.ru}"
API_KEY="${2:-}"
API_PASSWORD="${3:-}"

if [[ -z "$API_KEY" || -z "$API_PASSWORD" ]]; then
    echo "API credentials are required" >&2
    exit 1
fi

fetch() {
    local endpoint="$1"
    local url="https://${SHOP}/admin/${endpoint}"
    echo ""
    echo ">>> GET ${url}"
    curl -sS -u "${API_KEY}:${API_PASSWORD}" "$url"
}

fetch "products/count.json"
fetch "collections/count.json"
fetch "orders/count.json"
fetch "clients/count.json"
fetch "products.json?per_page=1&fields=id,title,variants,images,updated_at,created_at"













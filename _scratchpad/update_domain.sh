#!/usr/bin/env bash
set -euo pipefail

docker exec shopware bash -lc 'mysql -h 127.0.0.1 -u root -pshopware shopware -e "UPDATE sales_channel_domain SET url='\''https://dev.bireta.ru'\'' WHERE url LIKE '\''http%'\'';"'

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка product_media и product_listing_index через SQL на сервере"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from full_import import find_product_by_number

def check_listing_sql(product_number: str):
    """Проверка через SQL"""
    config_path = Path(__file__).parent.parent / "config.json"
    with config_path.open(encoding="utf-8") as f:
        config = json.load(f)
    
    sw = config["shopware"]
    client = ShopwareClient(ShopwareConfig(sw["url"], sw["access_key_id"], sw["secret_access_key"]))
    
    product_id = find_product_by_number(client, product_number)
    if not product_id:
        print(f"[ERROR] Товар {product_number} не найден")
        return
    
    # Получаем coverId
    response = client._request("GET", f"/api/product/{product_id}")
    if isinstance(response, dict):
        data = response.get("data", {})
        attributes = data.get("attributes", {})
        cover_id = attributes.get("coverId")
    
    print("=" * 80)
    print("ПРОВЕРКА ЧЕРЕЗ SQL")
    print("=" * 80)
    print(f"Product ID: {product_id}")
    print(f"Cover ID: {cover_id}")
    print()
    
    # Создаем Python скрипт для выполнения на сервере
    product_id_hex = product_id.replace("-", "")
    cover_id_hex = cover_id.replace("-", "") if cover_id else None
    
    script_content = f'''#!/usr/bin/env python3
import subprocess
import os

env_path = "/var/www/shopware/.env"
db_password = None
with open(env_path) as f:
    for line in f:
        if line.startswith("DATABASE_PASSWORD="):
            db_password = line.split("=", 1)[1].strip()
            break

product_id_hex = "{product_id_hex}"
cover_id_hex = "{cover_id_hex}" if "{cover_id_hex}" else None

print("=" * 80)
print("1. PRODUCT_MEDIA")
print("=" * 80)

sql1 = f"SELECT HEX(id), HEX(product_id), HEX(media_id), position FROM product_media WHERE product_id = UNHEX('{{product_id_hex}}') ORDER BY position LIMIT 10;"
result1 = subprocess.run(
    ["bash", "-c", f"export MYSQL_PWD={{db_password}} && mysql -u root shopware -N -e '{sql1}' 2>&1 | grep -v Warning:"],
    capture_output=True,
    text=True
)

if result1.returncode == 0 and result1.stdout.strip():
    print("Записи в product_media:")
    for line in result1.stdout.strip().split('\\n'):
        parts = line.split('\\t')
        if len(parts) >= 4:
            pm_id, p_id, m_id, pos = parts[0], parts[1], parts[2], parts[3]
            matches_cover = (m_id.upper() == cover_id_hex.upper()) if cover_id_hex else False
            print(f"  Product-Media ID: {{pm_id}}")
            print(f"    Media ID: {{m_id}}")
            print(f"    Position: {{pos}}")
            print(f"    Совпадает с coverId: {{matches_cover}}")
            if matches_cover:
                print(f"    *** ЭТО COVER МЕДИА ***")
            print()
else:
    print("[WARNING] Записи не найдены")

print("=" * 80)
print("2. PRODUCT_LISTING_INDEX")
print("=" * 80)

# Структура
desc_sql = "DESCRIBE product_listing_index;"
desc_result = subprocess.run(
    ["bash", "-c", f"export MYSQL_PWD={{db_password}} && mysql -u root shopware -e '{desc_sql}' 2>&1 | grep -v Warning:"],
    capture_output=True,
    text=True
)
if desc_result.returncode == 0:
    print("Структура product_listing_index:")
    for line in desc_result.stdout.strip().split('\\n'):
        if line.strip():
            print(f"  {{line}}")
    print()

# Запись для товара
sql2 = f"SELECT HEX(product_id), HEX(cover_id), HEX(media_id), visibility FROM product_listing_index WHERE product_id = UNHEX('{{product_id_hex}}') LIMIT 1;"
result2 = subprocess.run(
    ["bash", "-c", f"export MYSQL_PWD={{db_password}} && mysql -u root shopware -N -e '{sql2}' 2>&1 | grep -v Warning:"],
    capture_output=True,
    text=True
)

if result2.returncode == 0 and result2.stdout.strip():
    print("Запись в product_listing_index:")
    parts = result2.stdout.strip().split('\\t')
    if len(parts) >= 4:
        p_id, c_id, m_id, vis = parts[0], parts[1], parts[2], parts[3]
        print(f"  Product ID: {{p_id}}")
        print(f"  Cover ID: {{c_id}}")
        print(f"  Media ID: {{m_id}}")
        print(f"  Visibility: {{vis}}")
        if c_id.upper() == "NULL" or not c_id:
            print("  [ПРОБЛЕМА] cover_id = NULL!")
        elif cover_id_hex and c_id.upper() != cover_id_hex.upper():
            print(f"  [ПРОБЛЕМА] cover_id не совпадает!")
else:
    print("[ПРОБЛЕМА] Запись не найдена!")

print("=" * 80)
print("3. THUMBNAILS")
print("=" * 80)

if cover_id_hex:
    thumb_sql = f"SELECT HEX(id), width, height FROM media_thumbnail WHERE media_id = UNHEX('{{cover_id_hex}}') LIMIT 5;"
    thumb_result = subprocess.run(
        ["bash", "-c", f"export MYSQL_PWD={{db_password}} && mysql -u root shopware -N -e '{thumb_sql}' 2>&1 | grep -v Warning:"],
        capture_output=True,
        text=True
    )
    if thumb_result.returncode == 0 and thumb_result.stdout.strip():
        print("Thumbnails для cover медиа:")
        for line in thumb_result.stdout.strip().split('\\n'):
            parts = line.split('\\t')
            if len(parts) >= 3:
                print(f"  {{parts[1]}}x{{parts[2]}} (ID: {{parts[0]}})")
    else:
        print("[ПРОБЛЕМА] Thumbnails не найдены!")
'''
    
    # Сохраняем скрипт на сервере
    import subprocess
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "root@216.9.227.124", f"cat > /tmp/check_listing.py << 'EOFPYTHON'\n{script_content}\nEOFPYTHON"],
        capture_output=True,
        text=True,
        timeout=10
    )
    
    if result.returncode != 0:
        print(f"[ERROR] Не удалось создать скрипт на сервере: {result.stderr}")
        return
    
    # Выполняем скрипт
    exec_result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "root@216.9.227.124", "python3 /tmp/check_listing.py"],
        capture_output=True,
        text=True,
        timeout=30
    )
    
    if exec_result.returncode == 0:
        print(exec_result.stdout)
    else:
        print(f"[ERROR] Ошибка выполнения: {exec_result.stderr}")
        print(exec_result.stdout)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-number", default="500944170")
    args = parser.parse_args()
    check_listing_sql(args.product_number)



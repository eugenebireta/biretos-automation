#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка product_media и product_listing_index через SQL"""
import json
import subprocess
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
    
    # Получаем пароль БД
    env_path = "/var/www/shopware/.env"
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "root@216.9.227.124", f"grep DATABASE_PASSWORD {env_path} | head -1"],
        capture_output=True,
        text=True,
        timeout=10
    )
    
    if result.returncode != 0:
        print("[ERROR] Не удалось получить пароль БД")
        return
    
    line = result.stdout.strip()
    if "=" not in line:
        print("[ERROR] Неверный формат пароля")
        return
    
    db_password = line.split("=", 1)[1].strip()
    
    product_id_hex = product_id.replace("-", "")
    cover_id_hex = cover_id.replace("-", "") if cover_id else None
    
    # Проверка 1: product_media
    print("=" * 80)
    print("1. PRODUCT_MEDIA")
    print("=" * 80)
    
    sql1 = f"SELECT HEX(id), HEX(product_id), HEX(media_id), position FROM product_media WHERE product_id = UNHEX('{product_id_hex}') ORDER BY position LIMIT 10;"
    result1 = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "root@216.9.227.124", 
         f"export MYSQL_PWD={db_password} && mysql -u root shopware -N -e '{sql1}' 2>&1 | grep -v Warning:"],
        capture_output=True,
        text=True,
        timeout=10
    )
    
    if result1.returncode == 0 and result1.stdout.strip():
        print("Записи в product_media:")
        lines = result1.stdout.strip().split('\n')
        for line in lines:
            parts = line.split('\t')
            if len(parts) >= 4:
                pm_id, p_id, m_id, pos = parts[0], parts[1], parts[2], parts[3]
                matches_cover = (m_id.upper() == cover_id_hex.upper()) if cover_id_hex else False
                print(f"  Product-Media ID: {pm_id}")
                print(f"    Product ID: {p_id}")
                print(f"    Media ID: {m_id}")
                print(f"    Position: {pos}")
                print(f"    Совпадает с coverId: {matches_cover}")
                if matches_cover:
                    print(f"    *** ЭТО COVER МЕДИА ***")
                print()
    else:
        print("[WARNING] Записи в product_media не найдены")
        if result1.stderr:
            print(f"  stderr: {result1.stderr}")
    
    # Проверка 2: product_listing_index
    print("=" * 80)
    print("2. PRODUCT_LISTING_INDEX")
    print("=" * 80)
    
    # Сначала проверяем структуру
    desc_sql = "DESCRIBE product_listing_index;"
    desc_result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "root@216.9.227.124", 
         f"export MYSQL_PWD={db_password} && mysql -u root shopware -e '{desc_sql}' 2>&1 | grep -v Warning:"],
        capture_output=True,
        text=True,
        timeout=10
    )
    
    if desc_result.returncode == 0:
        print("Структура product_listing_index:")
        for line in desc_result.stdout.strip().split('\n'):
            if line.strip():
                print(f"  {line}")
        print()
    
    # Проверяем запись для товара
    sql2 = f"SELECT HEX(product_id), HEX(cover_id), HEX(media_id), visibility FROM product_listing_index WHERE product_id = UNHEX('{product_id_hex}') LIMIT 1;"
    result2 = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "root@216.9.227.124", 
         f"export MYSQL_PWD={db_password} && mysql -u root shopware -N -e '{sql2}' 2>&1 | grep -v Warning:"],
        capture_output=True,
        text=True,
        timeout=10
    )
    
    if result2.returncode == 0 and result2.stdout.strip():
        print("Запись в product_listing_index для товара:")
        parts = result2.stdout.strip().split('\t')
        if len(parts) >= 4:
            p_id, c_id, m_id, vis = parts[0], parts[1], parts[2], parts[3]
            print(f"  Product ID: {p_id}")
            print(f"  Cover ID: {c_id}")
            print(f"  Media ID: {m_id}")
            print(f"  Visibility: {vis}")
            print()
            
            if c_id.upper() == "NULL" or not c_id:
                print("  [ПРОБЛЕМА] cover_id = NULL в product_listing_index!")
            elif cover_id_hex and c_id.upper() != cover_id_hex.upper():
                print(f"  [ПРОБЛЕМА] cover_id не совпадает!")
                print(f"    Ожидается: {cover_id_hex.upper()}")
                print(f"    В индексе: {c_id.upper()}")
    else:
        print("[ПРОБЛЕМА] Запись в product_listing_index не найдена!")
        if result2.stderr:
            print(f"  stderr: {result2.stderr}")
        
        # Проверяем, есть ли вообще записи
        count_sql = "SELECT COUNT(*) FROM product_listing_index;"
        count_result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "root@216.9.227.124", 
             f"export MYSQL_PWD={db_password} && mysql -u root shopware -N -e '{count_sql}' 2>&1 | grep -v Warning:"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if count_result.returncode == 0:
            print(f"  Всего записей в product_listing_index: {count_result.stdout.strip()}")
    
    # Проверка 3: thumbnails
    print("=" * 80)
    print("3. THUMBNAILS")
    print("=" * 80)
    
    if cover_id_hex:
        thumb_sql = f"SELECT HEX(id), HEX(media_id), width, height FROM media_thumbnail WHERE media_id = UNHEX('{cover_id_hex}') LIMIT 5;"
        thumb_result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "root@216.9.227.124", 
             f"export MYSQL_PWD={db_password} && mysql -u root shopware -N -e '{thumb_sql}' 2>&1 | grep -v Warning:"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if thumb_result.returncode == 0 and thumb_result.stdout.strip():
            print("Thumbnails для cover медиа:")
            for line in thumb_result.stdout.strip().split('\n'):
                parts = line.split('\t')
                if len(parts) >= 4:
                    print(f"  {parts[2]}x{parts[3]} (ID: {parts[0]})")
        else:
            print("[ПРОБЛЕМА] Thumbnails не найдены для cover медиа!")
    
    # Выводы
    print("\n" + "=" * 80)
    print("ВЫВОДЫ")
    print("=" * 80)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-number", default="500944170")
    args = parser.parse_args()
    check_listing_sql(args.product_number)


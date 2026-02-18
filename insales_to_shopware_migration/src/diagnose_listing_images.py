#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Диагностика: почему изображения не отображаются в listing
ТОЛЬКО АНАЛИЗ, без изменений
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from full_import import find_product_by_number

def diagnose_listing_images(product_number: str):
    """Диагностика проблемы с изображениями в listing"""
    config_path = Path(__file__).parent.parent / "config.json"
    with config_path.open(encoding="utf-8") as f:
        config = json.load(f)
    
    sw = config["shopware"]
    client = ShopwareClient(ShopwareConfig(sw["url"], sw["access_key_id"], sw["secret_access_key"]))
    
    print("=" * 80)
    print("ДИАГНОСТИКА: ПОЧЕМУ ИЗОБРАЖЕНИЯ НЕ ОТОБРАЖАЮТСЯ В LISTING")
    print("=" * 80)
    print(f"Product Number: {product_number}\n")
    
    # Находим товар
    product_id = find_product_by_number(client, product_number)
    if not product_id:
        print(f"[ERROR] Товар {product_number} не найден")
        return
    
    print(f"[1] Product ID: {product_id}\n")
    
    # Шаг 1: Получаем product_media через API
    print("=" * 80)
    print("ШАГ 1: ПРОВЕРКА PRODUCT_MEDIA ЧЕРЕЗ API")
    print("=" * 80)
    
    try:
        # Пробуем получить через GET с associations
        response = client._request(
            "GET",
            f"/api/product/{product_id}",
            params={"associations[media]": "{}"}
        )
        
        if isinstance(response, dict):
            data = response.get("data", {})
            attributes = data.get("attributes", {})
            
            # Получаем coverId
            cover_id = attributes.get("coverId") or data.get("coverId")
            print(f"Cover ID из product: {cover_id}")
            
            # Пробуем получить медиа через relationships
            relationships = data.get("relationships", {})
            media_rel = relationships.get("media", {})
            print(f"Media relationships: {media_rel}")
            
            # Пробуем получить product_media через прямой endpoint с фильтром
            print(f"\nПопытка получить product_media через прямой endpoint:")
            try:
                # Используем search для фильтрации по product_id
                media_search_response = client._request(
                    "POST",
                    "/api/search/product-media",
                    json={
                        "filter": [
                            {"field": "productId", "type": "equals", "value": product_id}
                        ],
                        "includes": {"product_media": ["id", "mediaId", "position", "productId"]},
                        "limit": 10,
                        "sort": [{"field": "position", "order": "ASC"}]
                    }
                )
                if isinstance(media_search_response, dict):
                    media_data_list = media_search_response.get("data", [])
                    print(f"  Product-media записей для товара: {len(media_data_list)}")
                    for idx, pm in enumerate(media_data_list):
                        pm_attrs = pm.get("attributes", {})
                        media_id = pm_attrs.get("mediaId") or pm.get("mediaId")
                        position = pm_attrs.get("position") or pm.get("position")
                        print(f"    [{idx}] Product-Media ID: {pm.get('id')}")
                        print(f"        Media ID: {media_id}")
                        print(f"        Position: {position}")
                        print(f"        Совпадает с coverId: {media_id == cover_id}")
                        
                        if media_id == cover_id:
                            print(f"        *** ЭТО COVER МЕДИА ***")
            except Exception as e2:
                print(f"  [WARNING] Не удалось получить через search: {e2}")
                import traceback
                traceback.print_exc()
    
    except Exception as e:
        print(f"[ERROR] Ошибка получения product_media: {e}")
        import traceback
        traceback.print_exc()
    
    # Шаг 2: Проверяем product_media через прямой запрос к таблице (если возможно)
    print("\n" + "=" * 80)
    print("ШАГ 2: ПРОВЕРКА PRODUCT_MEDIA ЧЕРЕЗ SQL (если доступно)")
    print("=" * 80)
    
    try:
        # Пробуем получить через API product-media напрямую
        # Но сначала нужно найти product_media_id
        # В Shopware product_media - это связующая таблица
        
        # Альтернатива: проверим медиа через coverId
        if cover_id:
            print(f"\nПроверка cover медиа (ID: {cover_id}):")
            media_response = client._request("GET", f"/api/media/{cover_id}")
            if isinstance(media_response, dict):
                media_data = media_response.get("data", {})
                media_attrs = media_data.get("attributes", {})
                print(f"  Media ID: {cover_id}")
                print(f"  File name: {media_attrs.get('fileName')}")
                print(f"  MIME type: {media_attrs.get('mimeType')}")
                print(f"  File extension: {media_attrs.get('fileExtension')}")
                
                # Проверяем thumbnails
                thumbnails = media_data.get("thumbnails", [])
                if not thumbnails:
                    thumbnails_rel = media_data.get("relationships", {}).get("thumbnails", {})
                    print(f"  Thumbnails relationships: {thumbnails_rel}")
                    
                    # Пробуем получить через прямой endpoint
                    try:
                        thumb_endpoint = client._request("GET", f"/api/media/{cover_id}/thumbnails")
                        if isinstance(thumb_endpoint, dict):
                            thumb_data_list = thumb_endpoint.get("data", [])
                            print(f"  Thumbnails через endpoint: {len(thumb_data_list)}")
                            for thumb in thumb_data_list[:3]:
                                thumb_attrs = thumb.get("attributes", {})
                                print(f"    - {thumb_attrs.get('width')}x{thumb_attrs.get('height')}: {thumb.get('id')}")
                    except Exception as e3:
                        print(f"  [WARNING] Не удалось получить thumbnails: {e3}")
                else:
                    print(f"  Thumbnails count: {len(thumbnails)}")
                    for thumb in thumbnails[:3]:
                        print(f"    - {thumb.get('width')}x{thumb.get('height')}: {thumb.get('url')}")
    except Exception as e:
        print(f"[ERROR] Ошибка проверки медиа: {e}")
    
    # Шаг 3: Проверяем product_listing_index через SQL
    print("\n" + "=" * 80)
    print("ШАГ 3: ПРОВЕРКА PRODUCT_LISTING_INDEX (SQL)")
    print("=" * 80)
    
    try:
        import subprocess
        
        # Читаем пароль из .env на сервере
        env_path = "/var/www/shopware/.env"
        db_password = None
        
        # Пробуем получить через SSH
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "root@216.9.227.124", f"grep DATABASE_PASSWORD {env_path} | head -1"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            line = result.stdout.strip()
            if "=" in line:
                db_password = line.split("=", 1)[1].strip()
        
        if db_password:
            # Проверяем product_listing_index
            product_id_hex = product_id.replace("-", "")
            
            # Сначала проверяем структуру таблицы
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
                print(desc_result.stdout)
            
            # Проверяем запись для нашего товара
            sql = f"SELECT HEX(product_id) as product_id, HEX(cover_id) as cover_id, HEX(media_id) as media_id, listing_prices, visibility FROM product_listing_index WHERE product_id = UNHEX('{product_id_hex}') LIMIT 1;"
            
            result = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "root@216.9.227.124", 
                 f"export MYSQL_PWD={db_password} && mysql -u root shopware -N -e '{sql}' 2>&1 | grep -v Warning:"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and result.stdout.strip():
                print("\nДанные из product_listing_index для товара:")
                print(f"  {result.stdout.strip()}")
            else:
                print(f"\n[WARNING] Запись в product_listing_index не найдена")
                if result.stderr:
                    print(f"  stderr: {result.stderr}")
                
                # Проверяем, есть ли вообще записи в таблице
                check_sql = "SELECT COUNT(*) FROM product_listing_index LIMIT 1;"
                check_result = subprocess.run(
                    ["ssh", "-o", "BatchMode=yes", "root@216.9.227.124", 
                     f"export MYSQL_PWD={db_password} && mysql -u root shopware -N -e '{check_sql}' 2>&1 | grep -v Warning:"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if check_result.returncode == 0:
                    total = check_result.stdout.strip()
                    print(f"  Всего записей в product_listing_index: {total}")
                    
                    # Проверяем примеры записей с cover_id
                    sample_sql = "SELECT HEX(product_id), HEX(cover_id) FROM product_listing_index WHERE cover_id IS NOT NULL LIMIT 3;"
                    sample_result = subprocess.run(
                        ["ssh", "-o", "BatchMode=yes", "root@216.9.227.124", 
                         f"export MYSQL_PWD={db_password} && mysql -u root shopware -N -e '{sample_sql}' 2>&1 | grep -v Warning:"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if sample_result.returncode == 0 and sample_result.stdout.strip():
                        print(f"  Примеры записей с cover_id:")
                        for line in sample_result.stdout.strip().split('\n')[:3]:
                            print(f"    {line}")
        else:
            print("[INFO] Не удалось получить пароль БД, пропуск SQL проверки")
    
    except Exception as e:
        print(f"[WARNING] Ошибка SQL проверки: {e}")
    
    # Шаг 4: Проверяем структуру product через полный ответ API
    print("\n" + "=" * 80)
    print("ШАГ 4: ПОЛНАЯ СТРУКТУРА PRODUCT")
    print("=" * 80)
    
    try:
        full_response = client._request("GET", f"/api/product/{product_id}")
        if isinstance(full_response, dict):
            full_data = full_response.get("data", {})
            full_attrs = full_data.get("attributes", {})
            
            print("Ключевые поля product:")
            print(f"  id: {full_data.get('id')}")
            print(f"  productNumber: {full_attrs.get('productNumber')}")
            print(f"  name: {full_attrs.get('name')}")
            print(f"  coverId: {full_attrs.get('coverId')}")
            print(f"  active: {full_attrs.get('active')}")
            print(f"  available: {full_attrs.get('available')}")
            
            # Проверяем relationships
            relationships = full_data.get("relationships", {})
            print(f"\nRelationships:")
            for rel_name, rel_data in relationships.items():
                print(f"  {rel_name}: {type(rel_data)}")
                if isinstance(rel_data, dict):
                    rel_links = rel_data.get("links", {})
                    if rel_links:
                        related = rel_links.get("related")
                        if related:
                            print(f"    related: {related}")
    
    except Exception as e:
        print(f"[ERROR] Ошибка получения полной структуры: {e}")
    
    # Выводы
    print("\n" + "=" * 80)
    print("ВЫВОДЫ")
    print("=" * 80)
    print("""
Проверьте следующие моменты:
1. Есть ли запись в product_media с position=0 и mediaId=coverId?
2. Есть ли запись в product_listing_index с корректным cover_id?
3. Сгенерированы ли thumbnails для cover медиа?
4. Активен ли товар (active=true) и доступен (available=true)?
5. Настроен ли sales channel для listing?
    """)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Диагностика изображений в listing")
    parser.add_argument("--product-number", default="500944170", help="Product number")
    args = parser.parse_args()
    diagnose_listing_images(args.product_number)


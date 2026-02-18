#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Исправление фото у уже импортированных товаров.
Пересоздает media, product_media и cover через канонический pipeline.
"""

import sys
import json
import time
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from clients.shopware_client import ShopwareClient, ShopwareConfig
from full_import import load_json, find_product_by_number, download_and_upload_image


def get_product_from_snapshot(snapshot_path: Path, product_number: str) -> Optional[Dict[str, Any]]:
    """Находит товар в snapshot по productNumber."""
    with open(snapshot_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                variants = data.get("variants", [])
                if variants and len(variants) > 0:
                    sku = str(variants[0].get("sku", ""))
                    if sku == product_number:
                        return data
            except Exception:
                continue
    return None


def fix_product_media(
    client: ShopwareClient,
    product_id: str,
    product_number: str,
    images: List[Dict[str, Any]]
) -> bool:
    """
    Исправляет media для товара через канонический pipeline.
    
    Порядок:
    1. DELETE существующие product_media
    2. Загрузить изображения из snapshot
    3. CREATE product_media
    4. Установить cover через associations.cover
    
    Args:
        client: ShopwareClient
        product_id: ID товара в Shopware
        product_number: SKU товара
        images: Список изображений из snapshot
    
    Returns:
        True при успехе, False при ошибке
    """
    try:
        # ШАГ 1: DELETE существующие product_media
        print(f"  [STEP 1] Удаление старых product_media...")
        try:
            pm_search = client._request(
                "POST",
                "/api/search/product-media",
                json={
                    "filter": [{"field": "productId", "type": "equals", "value": product_id}],
                    "limit": 100
                }
            )
            if isinstance(pm_search, dict):
                pm_list = pm_search.get("data", [])
                deleted_count = 0
                for pm in pm_list:
                    pm_id = pm.get("id")
                    if pm_id:
                        try:
                            client._request("DELETE", f"/api/product-media/{pm_id}")
                            deleted_count += 1
                        except Exception:
                            pass
                print(f"    Удалено product_media: {deleted_count}")
        except Exception as e:
            print(f"    [WARNING] Ошибка удаления product_media: {e}")
        
        # ШАГ 2: Загрузить изображения из snapshot
        print(f"  [STEP 2] Загрузка изображений...")
        media_ids: List[str] = []
        for img in images:
            url = img.get("original_url")
            if not url:
                continue
            
            media_id = download_and_upload_image(client, url, product_number)
            if media_id:
                media_ids.append(media_id)
                print(f"    Загружено изображение: {media_id}")
        
        if not media_ids:
            print(f"  [WARNING] Не удалось загрузить изображения для товара {product_number}")
            return False
        
        print(f"    Всего загружено изображений: {len(media_ids)}")
        
        # ШАГ 3: CREATE product_media
        print(f"  [STEP 3] Создание product_media...")
        first_product_media_id = None
        for pos, media_id in enumerate(media_ids):
            product_media_id = client.create_product_media(
                product_id=product_id,
                media_id=media_id,
                position=pos
            )
            if product_media_id and pos == 0:
                first_product_media_id = product_media_id
            print(f"    Создан product_media[{pos}]: {product_media_id}")
        
        if not first_product_media_id:
            print(f"  [ERROR] Не удалось создать product_media для товара {product_number}")
            return False
        
        # ШАГ 4: Установить cover через associations.cover
        print(f"  [STEP 4] Установка cover через associations.cover...")
        time.sleep(0.2)  # Небольшая задержка для применения изменений
        cover_success = client.set_product_cover(
            product_id=product_id,
            product_media_id=first_product_media_id
        )
        
        if not cover_success:
            print(f"  [WARNING] Не удалось установить cover для товара {product_number}")
            return False
        
        print(f"    Cover установлен: {first_product_media_id}")
        
        # ШАГ 5: Проверка результата
        print(f"  [STEP 5] Проверка результата...")
        time.sleep(0.3)
        
        check_response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [{"field": "id", "type": "equals", "value": product_id}],
                "limit": 1
            }
        )
        
        media_count = 0
        cover_id = None
        
        if isinstance(check_response, dict):
            data_list = check_response.get("data", [])
            if data_list:
                attrs = data_list[0].get("attributes", {})
                cover_id = attrs.get("coverId")
                
                # Проверяем media count
                media_search = client._request(
                    "POST",
                    "/api/search/product-media",
                    json={
                        "filter": [{"field": "productId", "type": "equals", "value": product_id}],
                        "limit": 100
                    }
                )
                if isinstance(media_search, dict):
                    media_list = media_search.get("data", [])
                    media_count = len(media_list)
        
        print(f"    media_count: {media_count}")
        print(f"    coverId: {cover_id}")
        
        if media_count > 0 and cover_id:
            print(f"  [SUCCESS] Media исправлены для товара {product_number}")
            return True
        else:
            print(f"  [ERROR] Media не исправлены: media_count={media_count}, coverId={cover_id}")
            return False
            
    except Exception as e:
        print(f"  [ERROR] Ошибка исправления media для товара {product_number}: {e}")
        return False


def main() -> int:
    """Основная функция."""
    parser = argparse.ArgumentParser(description="Исправление фото у уже импортированных товаров")
    parser.add_argument("--limit", type=int, default=None, help="Ограничение количества товаров")
    parser.add_argument("--product-number", type=str, default=None, help="Исправить только указанный товар по SKU")
    args = parser.parse_args()
    
    # Пути
    project_root = Path(__file__).parent.parent
    snapshot_path = project_root / "insales_snapshot" / "products.ndjson"
    config_path = project_root / "config.json"
    
    if not snapshot_path.exists():
        print(f"[ERROR] Snapshot не найден: {snapshot_path}")
        return 1
    
    if not config_path.exists():
        print(f"[ERROR] Конфигурация не найдена: {config_path}")
        return 1
    
    # Загружаем конфигурацию
    config = load_json(config_path)
    
    # Создаем клиент
    shop_cfg = ShopwareConfig(
        url=config["shopware"]["url"],
        access_key_id=config["shopware"]["access_key_id"],
        secret_access_key=config["shopware"]["secret_access_key"],
    )
    client = ShopwareClient(shop_cfg, timeout=10)
    
    print("="*70)
    print("[FIX] Исправление фото у уже импортированных товаров")
    print("="*70)
    
    # Собираем список товаров для обработки
    products_to_fix: List[Dict[str, Any]] = []
    
    if args.product_number:
        # Обрабатываем только указанный товар
        product_data = get_product_from_snapshot(snapshot_path, args.product_number)
        if product_data:
            products_to_fix.append(product_data)
        else:
            print(f"[ERROR] Товар не найден в snapshot: {args.product_number}")
            return 1
    else:
        # Обрабатываем все товары из snapshot
        with open(snapshot_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    variants = data.get("variants", [])
                    if variants and len(variants) > 0:
                        sku = str(variants[0].get("sku", ""))
                        if sku:
                            products_to_fix.append(data)
                            if args.limit and len(products_to_fix) >= args.limit:
                                break
                except Exception:
                    continue
    
    print(f"[INFO] Найдено товаров для обработки: {len(products_to_fix)}")
    
    # Обрабатываем товары
    fixed = 0
    skipped = 0
    errors = 0
    
    for idx, product_data in enumerate(products_to_fix, 1):
        variants = product_data.get("variants", [])
        if not variants or len(variants) == 0:
            skipped += 1
            continue
        
        product_number = str(variants[0].get("sku", ""))
        if not product_number:
            skipped += 1
            continue
        
        images = product_data.get("images", [])
        if not images or len(images) == 0:
            print(f"[{idx}/{len(products_to_fix)}] {product_number}: [SKIP] Нет изображений")
            skipped += 1
            continue
        
        print(f"\n[{idx}/{len(products_to_fix)}] {product_number}")
        
        # Находим товар в Shopware
        product_id = find_product_by_number(client, product_number)
        if not product_id:
            print(f"  [SKIP] Товар не найден в Shopware")
            skipped += 1
            continue
        
        print(f"  Товар найден в Shopware: {product_id}")
        
        # Исправляем media
        success = fix_product_media(
            client=client,
            product_id=product_id,
            product_number=product_number,
            images=images
        )
        
        if success:
            fixed += 1
        else:
            errors += 1
    
    # Итоговый отчет
    print("\n" + "="*70)
    print("[RESULT]")
    print("="*70)
    print(f"Обработано: {len(products_to_fix)}")
    print(f"Исправлено: {fixed}")
    print(f"Пропущено: {skipped}")
    print(f"Ошибок: {errors}")
    print("="*70)
    
    if errors > 0:
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())





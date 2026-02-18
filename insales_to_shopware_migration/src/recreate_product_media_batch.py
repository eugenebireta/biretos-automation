#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Пересоздание медиа для существующих товаров без удаления товаров
"""
import json
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from full_import import download_and_upload_image, parse_ndjson, DEFAULT_SNAPSHOT_NDJSON, find_product_by_number

def get_media_usage(client: ShopwareClient, media_id: str) -> Set[str]:
    """
    Проверяет, какими товарами используется медиа.
    Возвращает множество product_id.
    """
    try:
        # Ищем товары, использующие это медиа
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [
                    {"field": "media.id", "type": "equals", "value": media_id}
                ],
                "includes": {"product": ["id"]},
                "limit": 100,
            },
        )
        
        product_ids = set()
        if isinstance(response, dict):
            data = response.get("data", [])
            for product in data:
                product_id = product.get("id")
                if product_id:
                    product_ids.add(product_id)
        
        # Также проверяем coverId
        response_cover = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [
                    {"field": "coverId", "type": "equals", "value": media_id}
                ],
                "includes": {"product": ["id"]},
                "limit": 100,
            },
        )
        
        if isinstance(response_cover, dict):
            data_cover = response_cover.get("data", [])
            for product in data_cover:
                product_id = product.get("id")
                if product_id:
                    product_ids.add(product_id)
        
        return product_ids
    except Exception as e:
        print(f"[WARNING] Ошибка проверки использования медиа {media_id}: {e}")
        return set()

def delete_product_media_safe(
    client: ShopwareClient,
    product_id: str,
    dry_run: bool = False
) -> List[str]:
    """
    Безопасно удаляет медиа товара.
    Удаляет только те медиа, которые не используются другими товарами.
    Возвращает список удаленных media_id.
    """
    deleted_media_ids = []
    
    try:
        # Получаем товар с медиа
        response = client._request(
            "GET",
            f"/api/product/{product_id}",
            params={"associations[media]": "{}"}
        )
        
        if isinstance(response, dict):
            data = response.get("data", {})
            media = data.get("media", [])
            
            if not media:
                print(f"[INFO] Товар {product_id} не имеет медиа")
                return []
            
            print(f"[INFO] Найдено {len(media)} медиа для проверки")
            
            # Собираем ID медиа
            media_ids = []
            for media_item in media:
                media_id = media_item.get("id")
                if media_id:
                    media_ids.append(media_id)
            
            # Проверяем использование каждого медиа
            for media_id in media_ids:
                usage = get_media_usage(client, media_id)
                if len(usage) > 1 or (len(usage) == 1 and product_id not in usage):
                    print(f"[SKIP] Медиа {media_id} используется другими товарами ({len(usage)}), пропуск")
                    continue
                
                # Медиа используется только этим товаром, можно удалить
                if not dry_run:
                    try:
                        # Сначала удаляем связь с товаром
                        client._request(
                            "PATCH",
                            f"/api/product/{product_id}",
                            json={"media": []}
                        )
                        # Затем удаляем само медиа
                        client._request("DELETE", f"/api/media/{media_id}")
                        deleted_media_ids.append(media_id)
                        print(f"[OK] Удалено медиа: {media_id}")
                    except Exception as e:
                        print(f"[ERROR] Ошибка удаления медиа {media_id}: {e}")
                else:
                    deleted_media_ids.append(media_id)
                    print(f"[DRY-RUN] Будет удалено медиа: {media_id}")
            
            # Убираем coverId
            if not dry_run:
                try:
                    client._request(
                        "PATCH",
                        f"/api/product/{product_id}",
                        json={"coverId": None}
                    )
                    print(f"[OK] Удален coverId")
                except Exception as e:
                    print(f"[WARNING] Ошибка удаления coverId: {e}")
            else:
                print(f"[DRY-RUN] Будет удален coverId")
        
    except Exception as e:
        print(f"[ERROR] Ошибка при удалении медиа: {e}")
        import traceback
        traceback.print_exc()
    
    return deleted_media_ids

def recreate_product_media(
    client: ShopwareClient,
    product_id: str,
    product_number: str,
    product_data: Optional[Dict[str, Any]],
    dry_run: bool = False
) -> bool:
    """
    Пересоздает медиа для товара.
    Возвращает True если успешно.
    """
    print(f"\n{'='*80}")
    print(f"ПЕРЕСОЗДАНИЕ МЕДИА ДЛЯ ТОВАРА")
    print(f"{'='*80}")
    print(f"Product ID: {product_id}")
    print(f"Product Number: {product_number}")
    print(f"Режим: {'DRY-RUN' if dry_run else 'REAL'}")
    print(f"{'='*80}\n")
    
    # Шаг 1: Удаляем старые медиа
    print(f"[STEP 1] Удаление старых медиа...")
    deleted_ids = delete_product_media_safe(client, product_id, dry_run=dry_run)
    print(f"[INFO] {'Будет удалено' if dry_run else 'Удалено'} медиа: {len(deleted_ids)}")
    
    # Шаг 2: Загружаем новые изображения
    if not product_data:
        print(f"[ERROR] Нет данных товара из snapshot")
        return False
    
    print(f"\n[STEP 2] Загрузка новых изображений...")
    images = product_data.get("images", [])
    if not images:
        print(f"[WARNING] Товар не имеет изображений в snapshot")
        return False
    
    media_ids = []
    for idx, img in enumerate(images, 1):
        url = img.get("original_url")
        if url:
            print(f"[{idx}/{len(images)}] Загрузка: {url}")
            if not dry_run:
                media_id = download_and_upload_image(client, url, product_number)
                if media_id:
                    media_ids.append(media_id)
                    print(f"[OK] Загружено медиа: {media_id}")
                else:
                    print(f"[ERROR] Не удалось загрузить изображение")
            else:
                # В dry-run просто добавляем фиктивный ID
                media_ids.append(f"dry-run-media-{idx}")
                print(f"[DRY-RUN] Будет загружено медиа для: {url}")
    
    if not media_ids:
        print(f"[ERROR] Не удалось загрузить ни одного изображения")
        return False
    
    # Шаг 3: Привязываем медиа к товару
    print(f"\n[STEP 3] Привязка медиа к товару...")
    if not dry_run:
        try:
            payload = {
                "media": [
                    {"mediaId": mid, "position": pos}
                    for pos, mid in enumerate(media_ids)
                ],
                "coverId": media_ids[0]  # Первое фото = cover
            }
            client._request("PATCH", f"/api/product/{product_id}", json=payload)
            print(f"[OK] Медиа привязаны к товару, coverId установлен")
        except Exception as e:
            print(f"[ERROR] Ошибка привязки медиа: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        print(f"[DRY-RUN] Будет привязано {len(media_ids)} медиа, coverId: {media_ids[0]}")
    
    print(f"\n{'='*80}")
    print(f"[SUCCESS] Медиа пересозданы для товара {product_number}")
    print(f"{'='*80}\n")
    
    return True

def main():
    parser = argparse.ArgumentParser(
        description="Пересоздание медиа для существующих товаров"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Режим проверки без реальных изменений"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Ограничение количества товаров (по умолчанию: 1)"
    )
    parser.add_argument(
        "--product-number",
        type=str,
        help="Конкретный product_number для обработки (опционально)"
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=DEFAULT_SNAPSHOT_NDJSON,
        help="Путь к snapshot файлу"
    )
    parser.add_argument(
        "--skip-shopware-commands",
        action="store_true",
        help="Пропустить выполнение команд Shopware после завершения"
    )
    
    args = parser.parse_args()
    
    # Загружаем конфигурацию
    config_path = Path(__file__).parent.parent / "config.json"
    with config_path.open(encoding="utf-8") as f:
        config = json.load(f)
    
    sw = config["shopware"]
    client = ShopwareClient(ShopwareConfig(sw["url"], sw["access_key_id"], sw["secret_access_key"]))
    
    # Загружаем snapshot
    print(f"Загрузка snapshot: {args.snapshot}")
    all_products = parse_ndjson(args.snapshot, limit=None)
    print(f"Загружено товаров из snapshot: {len(all_products)}")
    
    # Фильтруем товары
    products_to_process = []
    
    if args.product_number:
        # Обрабатываем конкретный товар
        product_data = None
        for p in all_products:
            variants = p.get("variants", [])
            if variants and variants[0].get("sku", "").strip() == args.product_number.strip():
                product_data = p
                break
        
        if not product_data:
            print(f"[ERROR] Товар {args.product_number} не найден в snapshot")
            return
        
        # Находим товар в Shopware
        product_id = find_product_by_number(client, args.product_number)
        if not product_id:
            print(f"[ERROR] Товар {args.product_number} не найден в Shopware")
            return
        
        products_to_process.append((product_id, args.product_number, product_data))
    else:
        # Обрабатываем товары с productNumber из Shopware
        print(f"\nПоиск товаров с productNumber в Shopware...")
        response = client._request("GET", "/api/product", params={"limit": args.limit * 2})
        
        if isinstance(response, dict):
            shopware_products = response.get("data", [])
            print(f"Найдено товаров в Shopware: {len(shopware_products)}")
            
            for sw_product in shopware_products[:args.limit]:
                product_id = sw_product.get("id")
                # Получаем полные данные товара
                try:
                    full_response = client._request("GET", f"/api/product/{product_id}")
                    if isinstance(full_response, dict):
                        full_data = full_response.get("data", {})
                        attributes = full_data.get("attributes", {})
                        product_number = attributes.get("productNumber") or full_data.get("productNumber")
                        
                        if not product_number:
                            print(f"[SKIP] Товар {product_id} не имеет productNumber")
                            continue
                        
                        # Ищем товар в snapshot
                        product_data = None
                        for p in all_products:
                            variants = p.get("variants", [])
                            if variants and variants[0].get("sku", "").strip() == product_number.strip():
                                product_data = p
                                break
                        
                        if not product_data:
                            print(f"[SKIP] Товар {product_number} не найден в snapshot")
                            continue
                        
                        products_to_process.append((product_id, product_number, product_data))
                except Exception as e:
                    print(f"[ERROR] Ошибка получения товара {product_id}: {e}")
                    continue
    
    if not products_to_process:
        print(f"[ERROR] Нет товаров для обработки")
        return
    
    print(f"\nТоваров к обработке: {len(products_to_process)}")
    
    # Обрабатываем товары
    success_count = 0
    for product_id, product_number, product_data in products_to_process:
        if recreate_product_media(client, product_id, product_number, product_data, dry_run=args.dry_run):
            success_count += 1
    
    print(f"\n{'='*80}")
    print(f"ИТОГО: {'Будет обработано' if args.dry_run else 'Обработано'} товаров: {success_count}/{len(products_to_process)}")
    print(f"{'='*80}\n")
    
    # Выполняем команды Shopware
    if not args.dry_run and not args.skip_shopware_commands and success_count > 0:
        print(f"\n[STEP 4] Выполнение команд Shopware...")
        import subprocess
        
        commands = [
            ("media:generate-media-types", "Генерация типов медиа"),
            ("media:generate-thumbnails", "Генерация thumbnails"),
            ("dal:refresh:index", "Обновление индексов DAL"),
            ("cache:clear", "Очистка кеша"),
        ]
        
        for cmd, description in commands:
            print(f"\n{description}...")
            try:
                result = subprocess.run(
                    ["ssh", "root@216.9.227.124", f"cd /var/www/shopware && HTTP_HOST=dev.bireta.ru php bin/console {cmd} --no-interaction"],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if result.returncode == 0:
                    print(f"[OK] {description} выполнено")
                    if result.stdout:
                        # Показываем последние строки вывода
                        lines = result.stdout.strip().split('\n')
                        for line in lines[-3:]:
                            if line.strip():
                                print(f"  {line}")
                else:
                    print(f"[ERROR] {description} завершилось с ошибкой")
                    if result.stderr:
                        print(f"  {result.stderr}")
            except Exception as e:
                print(f"[ERROR] Ошибка выполнения {cmd}: {e}")
    
    if args.dry_run:
        print("\n[INFO] Запуск в режиме DRY-RUN. Для реального выполнения запустите без --dry-run")
    else:
        print(f"\n[SUCCESS] Обработка завершена. Остановка для подтверждения.")

if __name__ == "__main__":
    main()





#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Массовое пересоздание медиа для товаров с productNumber
"""
import json
import sys
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from full_import import (
    download_and_upload_image,
    parse_ndjson,
    DEFAULT_SNAPSHOT_NDJSON,
    find_product_by_number
)

def check_media_usage(client: ShopwareClient, media_id: str) -> List[str]:
    """
    Проверяет, используется ли медиа другими товарами.
    Возвращает список product_id, которые используют это медиа.
    """
    try:
        # Ищем товары, которые используют это медиа
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [
                    {
                        "type": "equalsAny",
                        "field": "media.id",
                        "value": [media_id]
                    }
                ],
                "includes": {"product": ["id"]},
                "limit": 100
            }
        )
        
        if isinstance(response, dict):
            data = response.get("data", [])
            return [p.get("id") for p in data if p.get("id")]
    except Exception as e:
        print(f"[WARNING] Ошибка проверки использования медиа {media_id}: {e}")
    
    return []

def delete_product_media_safe(
    client: ShopwareClient,
    product_id: str,
    dry_run: bool = False
) -> List[str]:
    """
    Безопасно удаляет медиа товара (только если не используется другими товарами).
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
            # Проверяем data и data.attributes
            media = data.get("media", [])
            if not media and isinstance(data.get("attributes"), dict):
                media = data.get("attributes", {}).get("media", [])
            
            if not media:
                print(f"    [INFO] Товар не имеет медиа")
                return []
            
            print(f"    [INFO] Найдено {len(media)} медиа")
            
            # Собираем ID медиа
            media_ids = []
            for media_item in media:
                media_id = media_item.get("id")
                if media_id:
                    media_ids.append(media_id)
            
            # Проверяем использование каждого медиа
            for media_id in media_ids:
                used_by = check_media_usage(client, media_id)
                # Убираем текущий товар из списка
                used_by = [pid for pid in used_by if pid != product_id]
                
                if used_by:
                    print(f"    [SKIP] Медиа {media_id} используется другими товарами: {len(used_by)}")
                    continue
                
                if not dry_run:
                    try:
                        client._request("DELETE", f"/api/media/{media_id}")
                        deleted_media_ids.append(media_id)
                        print(f"    [OK] Удалено медиа: {media_id}")
                    except Exception as e:
                        print(f"    [ERROR] Ошибка удаления медиа {media_id}: {e}")
                else:
                    deleted_media_ids.append(media_id)
                    print(f"    [DRY-RUN] Будет удалено медиа: {media_id}")
            
            # Удаляем связи медиа с товаром
            if not dry_run:
                try:
                    client._request(
                        "PATCH",
                        f"/api/product/{product_id}",
                        json={"media": [], "coverId": None}
                    )
                    print(f"    [OK] Удалены связи медиа с товаром и coverId")
                except Exception as e:
                    print(f"    [WARNING] Ошибка удаления связей: {e}")
            else:
                print(f"    [DRY-RUN] Будут удалены связи медиа с товаром и coverId")
        
    except Exception as e:
        print(f"    [ERROR] Ошибка при удалении медиа: {e}")
        import traceback
        traceback.print_exc()
    
    return deleted_media_ids

def recreate_product_media(
    client: ShopwareClient,
    product_id: str,
    product_number: str,
    product_data: Dict[str, Any],
    dry_run: bool = False
) -> bool:
    """
    Пересоздает медиа для одного товара.
    Возвращает True при успехе.
    """
    print(f"\n{'='*80}")
    print(f"Товар: {product_number} (ID: {product_id})")
    print(f"{'='*80}")
    
    # Шаг 1: Удаляем старые медиа
    print(f"\n[STEP 1] Удаление старых медиа...")
    deleted_ids = delete_product_media_safe(client, product_id, dry_run=dry_run)
    print(f"    Удалено медиа: {len(deleted_ids)}")
    
    # Шаг 2: Загружаем новые изображения
    print(f"\n[STEP 2] Загрузка новых изображений...")
    images = product_data.get("images", [])
    if not images:
        print(f"    [SKIP] Товар не имеет изображений в snapshot")
        return False
    
    media_ids = []
    for idx, img in enumerate(images, 1):
        url = img.get("original_url")
        if not url:
            continue
        
        print(f"    [{idx}/{len(images)}] Загрузка: {url[:60]}...")
        
        if not dry_run:
            media_id = download_and_upload_image(client, url, product_number)
            if media_id:
                media_ids.append(media_id)
                print(f"        [OK] Загружено медиа: {media_id}")
            else:
                print(f"        [ERROR] Не удалось загрузить изображение")
        else:
            # В dry-run просто добавляем фиктивный ID
            media_ids.append(f"dry-run-{idx}")
            print(f"        [DRY-RUN] Будет загружено медиа")
    
    if not media_ids:
        print(f"    [ERROR] Не удалось загрузить ни одного изображения")
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
            print(f"    [OK] Медиа привязаны к товару, coverId установлен")
        except Exception as e:
            print(f"    [ERROR] Ошибка привязки медиа: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        print(f"    [DRY-RUN] Будут привязаны {len(media_ids)} медиа, coverId: {media_ids[0]}")
    
    print(f"\n[SUCCESS] Медиа пересозданы для товара {product_number}")
    print(f"    - Удалено старых медиа: {len(deleted_ids)}")
    print(f"    - Загружено новых медиа: {len(media_ids)}")
    
    return True

def run_shopware_commands(dry_run: bool = False):
    """Запускает команды Shopware для генерации thumbnails"""
    if dry_run:
        print(f"\n[DRY-RUN] Пропуск выполнения команд Shopware")
        return
    
    print(f"\n{'='*80}")
    print(f"ВЫПОЛНЕНИЕ КОМАНД SHOPWARE")
    print(f"{'='*80}")
    
    commands = [
        ("media:generate-media-types", "Генерация типов медиа"),
        ("media:generate-thumbnails", "Генерация thumbnails"),
        ("dal:refresh:index", "Обновление индексов DAL"),
        ("cache:clear", "Очистка кеша"),
    ]
    
    for cmd, description in commands:
        print(f"\n[{description}]...")
        try:
            result = subprocess.run(
                [
                    "ssh", "root@216.9.227.124",
                    f"cd /var/www/shopware && HTTP_HOST=dev.bireta.ru php bin/console {cmd} --no-interaction"
                ],
                capture_output=True,
                text=True,
                timeout=300
            )
            if result.returncode == 0:
                print(f"    [OK] Команда выполнена успешно")
                # Показываем последние строки вывода
                output_lines = result.stdout.strip().split('\n')
                if output_lines:
                    print(f"    Последние строки:")
                    for line in output_lines[-3:]:
                        if line.strip():
                            print(f"      {line}")
            else:
                print(f"    [ERROR] Команда завершилась с ошибкой: {result.returncode}")
                if result.stderr:
                    print(f"    Ошибка: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            print(f"    [ERROR] Команда превысила таймаут (5 минут)")
        except Exception as e:
            print(f"    [ERROR] Ошибка выполнения команды: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="Массовое пересоздание медиа для товаров с productNumber"
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
        help="Ограничение количества товаров для обработки (по умолчанию: 1)"
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=DEFAULT_SNAPSHOT_NDJSON,
        help="Путь к snapshot файлу"
    )
    parser.add_argument(
        "--skip-commands",
        action="store_true",
        help="Пропустить выполнение команд Shopware"
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
    
    # Находим товары с productNumber в Shopware
    print(f"\nПоиск товаров с productNumber в Shopware...")
    products_to_process = []
    
    for product_data in all_products:
        variants = product_data.get("variants", [])
        if not variants:
            continue
        
        sku = variants[0].get("sku", "").strip()
        if not sku:
            continue
        
        # Ищем товар в Shopware по productNumber
        product_id = find_product_by_number(client, sku)
        if product_id:
            products_to_process.append({
                "product_id": product_id,
                "product_number": sku,
                "product_data": product_data
            })
            if len(products_to_process) >= args.limit:
                break
    
    print(f"Найдено товаров с productNumber: {len(products_to_process)}")
    
    if not products_to_process:
        print("[ERROR] Не найдено товаров с productNumber для обработки")
        return
    
    # Обрабатываем товары
    print(f"\n{'='*80}")
    print(f"ОБРАБОТКА ТОВАРОВ")
    print(f"{'='*80}")
    print(f"Режим: {'DRY-RUN' if args.dry_run else 'REAL'}")
    print(f"Товаров к обработке: {len(products_to_process)}")
    print(f"{'='*80}\n")
    
    success_count = 0
    for idx, item in enumerate(products_to_process, 1):
        print(f"\n[{idx}/{len(products_to_process)}]")
        success = recreate_product_media(
            client,
            item["product_id"],
            item["product_number"],
            item["product_data"],
            dry_run=args.dry_run
        )
        if success:
            success_count += 1
    
    print(f"\n{'='*80}")
    print(f"ИТОГО")
    print(f"{'='*80}")
    print(f"Обработано товаров: {len(products_to_process)}")
    print(f"Успешно: {success_count}")
    print(f"Ошибок: {len(products_to_process) - success_count}")
    print(f"{'='*80}\n")
    
    # Запускаем команды Shopware
    if not args.skip_commands and success_count > 0:
        run_shopware_commands(dry_run=args.dry_run)
    
    if args.dry_run:
        print("\n[INFO] Запуск в режиме DRY-RUN. Для реального выполнения запустите без --dry-run")
    else:
        print(f"\n[SUCCESS] Обработка завершена. Успешно обработано товаров: {success_count}")

if __name__ == "__main__":
    main()


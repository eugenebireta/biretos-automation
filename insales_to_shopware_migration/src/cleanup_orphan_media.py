"""
Очистка Shopware от orphan media (медиа-файлов без связей)
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

BATCH_SIZE = 50


def get_all_media(client):
    """Получает все media из Shopware"""
    all_media = []
    page = 1
    per_page = 500
    
    print("Получение всех media из Shopware...")
    
    while True:
        try:
            response = client._request(
                "POST",
                "/api/search/media",
                json={
                    "limit": per_page,
                    "page": page,
                    "includes": {
                        "media": ["id", "fileName", "mimeType"]
                    }
                },
            )
            
            if isinstance(response, dict) and "data" in response:
                data = response.get("data", [])
                if not data:
                    break
                
                all_media.extend(data)
                
                if len(data) < per_page:
                    break
                
                page += 1
                print(f"  Загружено {len(all_media)} media...")
            else:
                break
        except Exception as e:
            print(f"Ошибка при получении media: {e}")
            break
    
    print(f"Всего найдено media: {len(all_media)}")
    return all_media


def check_media_usage(client, media_id):
    """Проверяет, используется ли media где-либо"""
    # Проверяем product_media
    try:
        response = client._request(
            "POST",
            "/api/search/product-media",
            json={
                "filter": [{"field": "mediaId", "type": "equals", "value": media_id}],
                "limit": 1
            },
        )
        if response.get("total", 0) > 0:
            return "product_media"
    except:
        pass
    
    # Проверяем categories
    try:
        response = client._request(
            "POST",
            "/api/search/category",
            json={
                "filter": [{"field": "mediaId", "type": "equals", "value": media_id}],
                "limit": 1
            },
        )
        if response.get("total", 0) > 0:
            return "category"
    except:
        pass
    
    # Проверяем cms pages
    try:
        response = client._request(
            "POST",
            "/api/search/cms-page",
            json={
                "filter": [{"field": "previewMediaId", "type": "equals", "value": media_id}],
                "limit": 1
            },
        )
        if response.get("total", 0) > 0:
            return "cms_page"
    except:
        pass
    
    # Проверяем manufacturers
    try:
        response = client._request(
            "POST",
            "/api/search/product-manufacturer",
            json={
                "filter": [{"field": "mediaId", "type": "equals", "value": media_id}],
                "limit": 1
            },
        )
        if response.get("total", 0) > 0:
            return "manufacturer"
    except:
        pass
    
    # Проверяем theme_media (через попытку удаления - Shopware сам скажет, используется ли)
    # Это делается в основном цикле удаления, здесь просто возвращаем None
    # и полагаемся на проверку Shopware при удалении
    
    return None


def main():
    parser = argparse.ArgumentParser(description="Очистка Shopware от orphan media")
    parser.add_argument("--auto", action="store_true", help="Автоматическое удаление без подтверждения")
    parser.add_argument("--dry-run", action="store_true", help="Только проверка, без удаления")
    args = parser.parse_args()
    
    print("=" * 80)
    print("ОЧИСТКА SHOPWARE ОТ ORPHAN MEDIA")
    print("=" * 80)
    if args.dry_run:
        print("РЕЖИМ: DRY-RUN (удаление не выполняется)")
    elif args.auto:
        print("РЕЖИМ: AUTO (автоматическое удаление)")
    print()
    
    # Загружаем конфигурацию
    if not CONFIG_PATH.exists():
        print(f"ERROR: Конфигурация не найдена: {CONFIG_PATH}")
        return 1
    
    with CONFIG_PATH.open() as f:
        config = json.load(f)
    
    sw_config = config["shopware"]
    client = ShopwareClient(
        ShopwareConfig(
            sw_config["url"],
            sw_config["access_key_id"],
            sw_config["secret_access_key"]
        )
    )
    
    # Получаем все media
    all_media = get_all_media(client)
    total_media = len(all_media)
    
    if total_media == 0:
        print("Media не найдено. Выход.")
        return 0
    
    print()
    print("Проверка связей media...")
    print()
    
    # Проверяем каждое media на наличие связей
    orphan_media = []
    used_media = []
    
    for idx, media in enumerate(all_media, 1):
        media_id = media.get("id")
        file_name = media.get("fileName", "N/A")
        
        if idx % 100 == 0:
            print(f"  Проверено {idx}/{total_media} media...")
        
        usage = check_media_usage(client, media_id)
        
        if usage:
            used_media.append({
                "id": media_id,
                "fileName": file_name,
                "usage": usage
            })
        else:
            orphan_media.append({
                "id": media_id,
                "fileName": file_name
            })
        
        # Небольшая задержка, чтобы не перегружать API
        if idx % 50 == 0:
            time.sleep(0.1)
    
    print()
    print(f"Проверка завершена:")
    print(f"  Всего media: {total_media}")
    print(f"  Используется: {len(used_media)}")
    print(f"  Orphan (не используется): {len(orphan_media)}")
    print()
    
    if len(orphan_media) == 0:
        print("Orphan media не найдено. Выход.")
        return 0
    
    # Подтверждение удаления
    print("=" * 80)
    print(f"НАЙДЕНО {len(orphan_media)} ORPHAN MEDIA ДЛЯ УДАЛЕНИЯ")
    print("=" * 80)
    print()
    print("Первые 10 orphan media:")
    for media in orphan_media[:10]:
        print(f"  - {media['fileName']} (ID: {media['id']})")
    if len(orphan_media) > 10:
        print(f"  ... и ещё {len(orphan_media) - 10} media")
    print()
    
    if args.dry_run:
        print("DRY-RUN: Удаление не выполняется")
        return 0
    
    if not args.auto:
        try:
            confirm = input("Удалить orphan media? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("Отменено.")
                return 0
        except (EOFError, KeyboardInterrupt):
            print("\nОтменено.")
            return 0
    
    print()
    print("=" * 80)
    print("УДАЛЕНИЕ ORPHAN MEDIA")
    print("=" * 80)
    print()
    
    deleted_count = 0
    skipped_count = 0
    errors = []
    
    # Удаляем batch-ами
    for batch_start in range(0, len(orphan_media), BATCH_SIZE):
        batch = orphan_media[batch_start:batch_start + BATCH_SIZE]
        batch_num = (batch_start // BATCH_SIZE) + 1
        total_batches = (len(orphan_media) + BATCH_SIZE - 1) // BATCH_SIZE
        
        print(f"Обработка batch {batch_num}/{total_batches} ({len(batch)} media)...")
        
        for media in batch:
            media_id = media["id"]
            file_name = media["fileName"]
            
            try:
                # Дополнительная проверка перед удалением
                usage = check_media_usage(client, media_id)
                if usage:
                    skipped_count += 1
                    errors.append(f"SKIP: {file_name} (ID: {media_id}) - используется в {usage}")
                    continue
                
                # Удаляем media
                client._request("DELETE", f"/api/media/{media_id}")
                deleted_count += 1
                
            except Exception as e:
                error_str = str(e)
                # Проверяем, является ли это ошибкой "DELETE_RESTRICTED" (media используется)
                if "DELETE_RESTRICTED" in error_str or "currently in use" in error_str:
                    # Извлекаем информацию об использовании из ошибки
                    usage_info = "unknown"
                    if "theme_media" in error_str:
                        usage_info = "theme_media"
                    elif "product_media" in error_str:
                        usage_info = "product_media"
                    elif "category" in error_str:
                        usage_info = "category"
                    
                    skipped_count += 1
                    errors.append(f"SKIP: {file_name} (ID: {media_id}) - используется в {usage_info} (защита Shopware)")
                else:
                    # Другая ошибка
                    error_msg = f"ERROR: {file_name} (ID: {media_id}) - {error_str}"
                    errors.append(error_msg)
                    print(f"  {error_msg}")
        
        # Пауза между batch-ами
        if batch_start + BATCH_SIZE < len(orphan_media):
            time.sleep(0.5)
    
    print()
    print("=" * 80)
    print("ОТЧЁТ ОБ ОЧИСТКЕ")
    print("=" * 80)
    print()
    print(f"Найдено media всего: {total_media}")
    print(f"Используется: {len(used_media)}")
    print(f"Orphan (не используется): {len(orphan_media)}")
    print()
    print(f"Удалено media: {deleted_count}")
    print(f"Пропущено (привязано): {skipped_count}")
    print(f"Ошибок: {len([e for e in errors if e.startswith('ERROR')])}")
    print()
    
    if errors and len(errors) <= 20:
        print("Ошибки и пропуски:")
        for error in errors:
            print(f"  - {error}")
    elif errors:
        print(f"Первые 10 ошибок и пропусков:")
        for error in errors[:10]:
            print(f"  - {error}")
        print(f"  ... и ещё {len(errors) - 10} записей")
    
    print()
    print("=" * 80)
    print("ОЧИСТКА ЗАВЕРШЕНА")
    print("=" * 80)
    print()
    
    if deleted_count > 0:
        print(f"OK: Удалено {deleted_count} orphan media")
        print("Media Library очищена. Можно безопасно импортировать товары.")
    elif skipped_count > 0:
        print(f"INFO: Все найденные media используются (связаны с товарами, категориями, темами и т.д.)")
        print("Удаление не требуется.")
    else:
        print("INFO: Orphan media не найдено.")
    
    print()
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

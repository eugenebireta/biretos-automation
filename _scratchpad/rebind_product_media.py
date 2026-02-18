"""
Перепривязка медиа к товарам для триггера генерации thumbnails

Скрипт переотправляет существующие медиа через PATCH API,
чтобы Shopware поставил их в очередь обработки для генерации thumbnails.
"""
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
import time

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json

ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
config = load_json(ROOT / "config.json")

shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

print("=" * 60)
print("ПЕРЕПРИВЯЗКА МЕДИА К ТОВАРАМ")
print("=" * 60)
print("Цель: триггернуть генерацию thumbnails через обновление медиа")
print("=" * 60)

# Параметры батчинга
BATCH_SIZE = 50
BATCH_DELAY = 1.0  # секунды между батчами

def get_product_media(product_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Получает список медиа для товара через product-media endpoint.
    Это наиболее надёжный способ, так как содержит position.
    
    Returns:
        Список словарей с mediaId и position, или None при ошибке
    """
    try:
        # Используем product-media endpoint - он содержит position
        pm_response = client._request("GET", "/api/product-media", params={
            "filter[productId]": product_id
        })
        pm_data = pm_response.get("data", []) if isinstance(pm_response, dict) else []
        
        if not pm_data:
            return None
        
        media_items = []
        for pm in pm_data:
            pm_attrs = pm.get("attributes", {})
            media_id = pm_attrs.get("mediaId")
            position = pm_attrs.get("position", 0)
            if media_id:
                media_items.append({
                    "mediaId": media_id,
                    "position": position
                })
        
        # Сортируем по position
        media_items.sort(key=lambda x: x.get("position", 0))
        return media_items if media_items else None
        
    except Exception as e:
        # Если product-media не работает, пробуем через relationships
        try:
            detail = client._request("GET", f"/api/product/{product_id}")
            detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
            relationships = detail_data.get("relationships", {})
            media_rel = relationships.get("media", {})
            media_data = media_rel.get("data", []) if isinstance(media_rel, dict) else []
            
            if media_data:
                media_items = []
                for idx, media_ref in enumerate(media_data):
                    media_id = media_ref.get("id")
                    if media_id:
                        media_items.append({
                            "mediaId": media_id,
                            "position": idx
                        })
                return media_items if media_items else None
        except Exception:
            pass
        
        return None

def rebind_product_media(product_id: str, product_number: str, media_items: List[Dict[str, Any]]) -> bool:
    """
    Перепривязывает медиа к товару через PATCH API.
    
    Args:
        product_id: ID товара в Shopware
        product_number: Номер товара (для логирования)
        media_items: Список медиа с mediaId и position
    
    Returns:
        True при успехе, False при ошибке
    """
    try:
        # Подготавливаем payload с теми же mediaId и position
        payload = {
            "id": product_id,
            "media": media_items
        }
        
        # НЕ меняем coverId - оставляем как есть
        # НЕ добавляем новых полей
        
        client._request("PATCH", f"/api/product/{product_id}", json=payload)
        return True
        
    except Exception as e:
        error_str = str(e)
        print(f"  [FAIL] {product_number} -> {error_str[:100]}")
        return False

# Получаем все товары
print("\n1. Получение всех товаров из Shopware...")
all_products = []
limit = 100
offset = 0

while True:
    response = client._request("GET", "/api/product", params={"limit": limit, "offset": offset})
    products = response.get("data", []) if isinstance(response, dict) else []
    if not products:
        break
    all_products.extend(products)
    offset += limit
    print(f"  Загружено: {len(all_products)} товаров...")
    if len(products) < limit:
        break

print(f"Всего товаров: {len(all_products)}")

# Обрабатываем товары батчами
print("\n" + "=" * 60)
print("НАЧАЛО ПЕРЕПРИВЯЗКИ МЕДИА")
print("=" * 60)

rebound = 0
skipped = 0
failed = 0
errors: List[Dict[str, str]] = []
start_time = time.time()

for idx, product in enumerate(all_products, 1):
    product_id = product.get("id")
    
    try:
        # Получаем детали товара
        detail = client._request("GET", f"/api/product/{product_id}")
        detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
        attrs = detail_data.get("attributes", {})
        
        product_number = attrs.get("productNumber")
        if not product_number:
            skipped += 1
            continue
        
        # Получаем медиа товара
        media_items = get_product_media(product_id)
        
        if not media_items:
            skipped += 1
            if idx % 100 == 0:
                print(f"[{idx}/{len(all_products)}] [SKIP] {product_number} -> нет медиа")
            continue
        
        # Перепривязываем медиа
        success = rebind_product_media(product_id, product_number, media_items)
        
        if success:
            rebound += 1
            if idx % 50 == 0:
                elapsed = time.time() - start_time
                rate = idx / elapsed if elapsed > 0 else 0
                remaining = (len(all_products) - idx) / rate if rate > 0 else 0
                print(f"[{idx}/{len(all_products)}] [OK] {product_number} -> media rebound ({len(media_items)} медиа) | "
                      f"Rebound: {rebound}, Skipped: {skipped}, Failed: {failed} | "
                      f"Скорость: {rate:.1f} товаров/сек | Осталось: {remaining:.0f} сек")
        else:
            failed += 1
            errors.append({
                "product_number": product_number,
                "product_id": product_id,
                "error": "Failed to rebind media"
            })
        
        # Батчинг: задержка между батчами
        if idx % BATCH_SIZE == 0:
            time.sleep(BATCH_DELAY)
    
    except Exception as e:
        failed += 1
        error_str = str(e)
        product_number = attrs.get("productNumber", "Unknown") if 'attrs' in locals() else "Unknown"
        errors.append({
            "product_number": product_number,
            "product_id": product_id,
            "error": error_str[:200]
        })
        if idx % 100 == 0:
            print(f"[{idx}/{len(all_products)}] [FAIL] {product_number} -> {error_str[:100]}")

elapsed = time.time() - start_time
print("\n" + "=" * 60)
print("ПЕРЕПРИВЯЗКА ЗАВЕРШЕНА")
print("=" * 60)
print(f"Всего обработано: {len(all_products)}")
print(f"Перепривязано: {rebound}")
print(f"Пропущено (нет медиа): {skipped}")
print(f"Ошибок: {failed}")
print(f"Время выполнения: {elapsed:.1f} сек")
print(f"Средняя скорость: {len(all_products)/elapsed:.1f} товаров/сек" if elapsed > 0 else "N/A")

if errors:
    print(f"\nПервые 10 ошибок:")
    for error in errors[:10]:
        print(f"  - {error.get('product_number', 'Unknown')}: {error.get('error', 'Unknown error')[:100]}")
    if len(errors) > 10:
        print(f"  ... и ещё {len(errors) - 10} ошибок")

print("\n" + "=" * 60)
print("СЛЕДУЮЩИЙ ШАГ")
print("=" * 60)
print("После выполнения скрипта запустите вручную:")
print("  docker exec shopware php bin/console media:generate-thumbnails")
print("=" * 60)


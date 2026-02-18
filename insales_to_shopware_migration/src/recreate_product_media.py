#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Пересоздание медиа для товара: удаление старых медиа и загрузка новых
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from full_import import download_and_upload_image, parse_ndjson, DEFAULT_SNAPSHOT_NDJSON

def delete_product_media(client: ShopwareClient, product_id: str) -> list[str]:
    """
    Удаляет все медиа, связанные с товаром.
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
            
            print(f"[INFO] Найдено {len(media)} медиа для удаления")
            
            # Удаляем связи медиа с товаром через PATCH (убираем media из товара)
            # Но сначала собираем ID медиа
            media_ids = []
            for media_item in media:
                media_id = media_item.get("id")
                if media_id:
                    media_ids.append(media_id)
            
            # Удаляем медиа из товара через PATCH с пустым массивом media
            try:
                client._request(
                    "PATCH",
                    f"/api/product/{product_id}",
                    json={"media": []}
                )
                print(f"[INFO] Удалены связи медиа с товаром")
            except Exception as e:
                print(f"[WARNING] Ошибка удаления связей медиа: {e}")
            
            # Удаляем сами медиа-сущности
            for media_id in media_ids:
                try:
                    client._request("DELETE", f"/api/media/{media_id}")
                    deleted_media_ids.append(media_id)
                    print(f"[INFO] Удалено медиа: {media_id}")
                except Exception as e:
                    print(f"[WARNING] Ошибка удаления медиа {media_id}: {e}")
            
            # Убираем coverId
            try:
                client._request(
                    "PATCH",
                    f"/api/product/{product_id}",
                    json={"coverId": None}
                )
                print(f"[INFO] Удален coverId")
            except Exception as e:
                print(f"[WARNING] Ошибка удаления coverId: {e}")
        
    except Exception as e:
        print(f"[ERROR] Ошибка при удалении медиа: {e}")
        import traceback
        traceback.print_exc()
    
    return deleted_media_ids

def recreate_product_media(product_id: str = None, product_number: str = None, limit: int = 1):
    """
    Пересоздает медиа для товара с указанным product_id или product_number.
    """
    # Загружаем конфигурацию
    config_path = Path(__file__).parent.parent / "config.json"
    with config_path.open() as f:
        config = json.load(f)
    
    sw = config["shopware"]
    client = ShopwareClient(ShopwareConfig(sw["url"], sw["access_key_id"], sw["secret_access_key"]))
    
    # Находим товар
    if not product_id:
        if not product_number:
            print(f"[ERROR] Необходимо указать product_id или product_number")
            return
        from full_import import find_product_by_number
        product_id = find_product_by_number(client, product_number)
        
        if not product_id:
            print(f"[ERROR] Товар с product_number={product_number} не найден")
            return
    
    print(f"[INFO] Найден товар: {product_id}")
    
    # Получаем данные товара из snapshot (если указан product_number)
    product_data = None
    if product_number:
        products = parse_ndjson(DEFAULT_SNAPSHOT_NDJSON, limit=1000)
        for p in products:
            if p.get("variants", [{}])[0].get("sku", "").strip() == product_number.strip():
                product_data = p
                break
        
        if not product_data:
            print(f"[WARNING] Товар {product_number} не найден в snapshot, используем данные из Shopware")
    
    # Если не нашли в snapshot, получаем из Shopware
    if not product_data:
        try:
            response = client._request("GET", f"/api/product/{product_id}")
            if isinstance(response, dict):
                shopware_data = response.get("data", {})
                product_number = shopware_data.get("productNumber")
                print(f"[INFO] Используем product_number из Shopware: {product_number}")
        except:
            pass
    
    # Удаляем старые медиа
    print(f"\n[STEP 1] Удаление старых медиа...")
    deleted_ids = delete_product_media(client, product_id)
    print(f"[INFO] Удалено медиа: {len(deleted_ids)}")
    
    # Загружаем новые изображения
    print(f"\n[STEP 2] Загрузка новых изображений...")
    images = []
    if product_data:
        images = product_data.get("images", [])
    else:
        print(f"[WARNING] Товар не найден в snapshot, пропускаем загрузку изображений")
        print(f"[INFO] Для пересоздания медиа необходимо наличие товара в snapshot с изображениями")
        return
    
    if not images:
        print(f"[WARNING] Товар не имеет изображений в snapshot")
        return
    
    media_ids = []
    for img in images:
        url = img.get("original_url")
        if url:
            print(f"[INFO] Загрузка изображения: {url}")
            media_id = download_and_upload_image(client, url, product_number)
            if media_id:
                media_ids.append(media_id)
                print(f"[INFO] Загружено медиа: {media_id}")
            else:
                print(f"[WARNING] Не удалось загрузить изображение: {url}")
    
    if not media_ids:
        print(f"[ERROR] Не удалось загрузить ни одного изображения")
        return
    
    # Привязываем медиа к товару
    print(f"\n[STEP 3] Привязка медиа к товару...")
    try:
        payload = {
            "media": [
                {"mediaId": mid, "position": pos}
                for pos, mid in enumerate(media_ids)
            ],
            "coverId": media_ids[0]  # Первое фото = cover
        }
        client._request("PATCH", f"/api/product/{product_id}", json=payload)
        print(f"[INFO] Медиа привязаны к товару, coverId установлен")
    except Exception as e:
        print(f"[ERROR] Ошибка привязки медиа: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print(f"\n[SUCCESS] Медиа пересозданы для товара {product_number}")
    print(f"  - Удалено старых медиа: {len(deleted_ids)}")
    print(f"  - Загружено новых медиа: {len(media_ids)}")
    print(f"  - Product ID: {product_id}")
    print(f"  - Media IDs: {', '.join(media_ids)}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Пересоздание медиа для товара")
    parser.add_argument("--product-id", help="Product ID")
    parser.add_argument("--product-number", help="Product number (SKU)")
    args = parser.parse_args()
    
    if not args.product_id and not args.product_number:
        parser.error("Необходимо указать --product-id или --product-number")
    
    recreate_product_media(product_id=args.product_id, product_number=args.product_number)

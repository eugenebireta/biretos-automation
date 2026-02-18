#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестовый скрипт для чистого UPDATE одного товара.
Проверяет логику UPDATE изображений и custom field для штрих-кода.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent))

from clients.shopware_client import ShopwareClient, ShopwareConfig, ShopwareClientError
from full_import import (
    load_json, parse_ndjson, process_characteristics,
    download_and_upload_image, find_product_by_number
)


def get_product_state(client: ShopwareClient, product_id: str) -> Dict[str, Any]:
    """Получает текущее состояние товара."""
    try:
        # Используем search API для более полных данных
        product_search = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [{"field": "id", "type": "equals", "value": product_id}],
                "limit": 1
            }
        )
        
        data = None
        if isinstance(product_search, dict):
            data_list = product_search.get("data", [])
            if data_list:
                data = data_list[0]
        
        # Fallback на GET если search не вернул данные
        if not data:
            product = client._request("GET", f"/api/product/{product_id}")
            if isinstance(product, dict):
                data = product.get("data", product)
            else:
                data = product
        
        # Получаем product_media
        media_count = 0
        cover_id = data.get("coverId") if data else None
        
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
                media_count = len(pm_search.get("data", []))
        except Exception:
            pass
        
        custom_fields = data.get("customFields", {}) if data else {}
        
        return {
            "id": product_id,
            "productNumber": data.get("productNumber") if data else None,
            "media_count": media_count,
            "coverId": cover_id,
            "customFields": custom_fields,
            "internal_barcode": custom_fields.get("internal_barcode")
        }
    except Exception as e:
        print(f"[ERROR] Ошибка получения состояния товара: {e}")
        import traceback
        traceback.print_exc()
        return {}


def check_duplicates(client: ShopwareClient, product_id: str) -> bool:
    """Проверяет наличие дубликатов product_media."""
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
            media_ids = [pm.get("mediaId") for pm in pm_list if pm.get("mediaId")]
            # Проверяем дубликаты mediaId
            return len(media_ids) != len(set(media_ids))
    except Exception:
        pass
    return False


def main() -> int:
    """Выполняет чистый UPDATE одного товара."""
    product_number = "500944170"
    
    # Загружаем конфигурацию
    config_path = Path(__file__).parent.parent / "config.json"
    if not config_path.exists():
        print(f"[ERROR] Конфигурация не найдена: {config_path}")
        return 1
    
    config = load_json(config_path)
    
    # Создаем клиент
    shop_cfg = ShopwareConfig(
        url=config["shopware"]["url"],
        access_key_id=config["shopware"]["access_key_id"],
        secret_access_key=config["shopware"]["secret_access_key"],
    )
    client = ShopwareClient(shop_cfg, timeout=10)
    
    # Создаем custom field, если не существует
    client.get_or_create_custom_field_barcode()
    
    # Находим товар
    print(f"[INFO] Поиск товара по productNumber: {product_number}")
    product_id = find_product_by_number(client, product_number)
    
    if not product_id:
        print(f"[ERROR] Product not found: {product_number}")
        return 1
    
    print(f"[OK] Товар найден: {product_id}")
    
    # Получаем состояние ДО UPDATE
    print("\n" + "="*60)
    print("[BEFORE UPDATE] Текущее состояние товара:")
    print("="*60)
    state_before = get_product_state(client, product_id)
    print(f"  product.id: {state_before.get('id')}")
    print(f"  product_media count: {state_before.get('media_count', 0)}")
    print(f"  coverId: {state_before.get('coverId')}")
    print(f"  customFields.internal_barcode: {state_before.get('internal_barcode')}")
    
    # Загружаем данные из snapshot
    snapshot_path = Path(__file__).parent.parent / "insales_snapshot" / "products.ndjson"
    if not snapshot_path.exists():
        print(f"[ERROR] Snapshot не найден: {snapshot_path}")
        return 1
    
    # Ищем товар в snapshot
    product_data = None
    with open(snapshot_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                variant = data.get("variants", [{}])[0] if data.get("variants") else {}
                if variant.get("sku") == product_number:
                    product_data = data
                    break
            except Exception:
                continue
    
    if not product_data:
        print(f"[ERROR] Товар не найден в snapshot: {product_number}")
        return 1
    
    print(f"\n[INFO] Данные из snapshot загружены")
    
    # Подготавливаем данные для UPDATE (используем логику из full_import.py)
    product_name = product_data.get("title", "Unknown")
    variant = product_data.get("variants", [{}])[0] if product_data.get("variants") else {}
    price_value = float(variant.get("price", 0) or 0)
    
    # Получаем валюту
    sales_channel_currency = client.get_sales_channel_currency_id()
    
    # Создаем payload
    payload = {
        "id": product_id,
        "productNumber": product_number,
        "name": product_name,
        "active": True,
        "taxId": client.get_default_tax_id(),
        "price": [{
            "currencyId": sales_channel_currency,
            "gross": price_value,
            "net": price_value / 1.19,
            "linked": True
        }],
        "stock": int(variant.get("quantity", 0) or 0),
    }
    
    # Добавляем штрих-код
    variant_barcode = variant.get("barcode")
    if variant_barcode:
        if "customFields" not in payload:
            payload["customFields"] = {}
        payload["customFields"]["internal_barcode"] = str(variant_barcode).strip()
        print(f"[INFO] Штрих-код добавлен в payload: {payload['customFields']['internal_barcode']}")
    else:
        print(f"[WARNING] Штрих-код не найден в варианте")
    
    # КРИТИЧНО: Загружаем изображения ДО PATCH
    print(f"\n[INFO] Загрузка изображений...")
    update_media_ids: List[str] = []
    images = product_data.get("images", [])
    for img in images:
        url = img.get("original_url")
        if url:
            print(f"  Загрузка: {url}")
            media_id = download_and_upload_image(client, url, product_number)
            if media_id:
                update_media_ids.append(media_id)
                print(f"  [OK] Загружено: {media_id}")
            else:
                print(f"  [FAILED] Не удалось загрузить")
    
    print(f"[INFO] Загружено изображений: {len(update_media_ids)}")
    
    # Выполняем PATCH (без customFields, они обновятся через Sync API)
    payload_without_custom = {k: v for k, v in payload.items() if k != "customFields"}
    print(f"\n[INFO] Выполнение PATCH product...")
    try:
        client._request("PATCH", f"/api/product/{product_id}", json=payload_without_custom)
        print(f"[OK] PATCH выполнен успешно")
    except ShopwareClientError as e:
        print(f"[ERROR] Ошибка PATCH: {e}")
        return 1
    
    # Обновляем customFields через Sync API (более надежно)
    if variant_barcode:
        print(f"[INFO] Обновление customFields через Sync API...")
        try:
            sync_payload = [{
                "entity": "product",
                "action": "upsert",
                "payload": [{
                    "id": product_id,
                    "customFields": {
                        "internal_barcode": str(variant_barcode).strip()
                    }
                }]
            }]
            client._request("POST", "/api/_action/sync", json=sync_payload)
            print(f"[OK] customFields обновлены через Sync API")
        except Exception as e:
            print(f"[WARNING] Ошибка обновления customFields: {e}")
    
    # Обрабатываем изображения
    if not update_media_ids:
        print(f"\n[IMAGE_UPDATE_SKIPPED] Не удалось загрузить новые изображения, старые сохранены")
    else:
        print(f"\n[INFO] Обновление product_media...")
        # Удаляем старые product_media
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
                print(f"  Удалено старых product_media: {deleted_count}")
        except Exception as e:
            print(f"  [WARNING] Ошибка удаления старых product_media: {e}")
        
        # Создаем новые product_media
        print(f"  Создание новых product_media...")
        cover_id_result = client.set_product_media_and_cover(
            product_id=product_id,
            media_ids=update_media_ids
        )
        print(f"  [OK] Новые product_media созданы, coverId установлен: {cover_id_result}")
        
        # Проверяем, что coverId действительно установлен
        import time
        time.sleep(0.5)
        try:
            pm_check = client._request(
                "POST",
                "/api/search/product-media",
                json={
                    "filter": [
                        {"field": "productId", "type": "equals", "value": product_id},
                        {"field": "position", "type": "equals", "value": 0}
                    ],
                    "limit": 1
                }
            )
            if isinstance(pm_check, dict):
                pm_data = pm_check.get("data", [])
                if pm_data:
                    actual_pm_id = pm_data[0].get("id")
                    print(f"  [DEBUG] Реальный product_media ID (position=0): {actual_pm_id}")
                    # Пробуем установить coverId через прямой PATCH
                    try:
                        client._request("PATCH", f"/api/product/{product_id}", json={"coverId": actual_pm_id})
                        print(f"  [DEBUG] coverId установлен через прямой PATCH: {actual_pm_id}")
                    except Exception as e:
                        print(f"  [WARNING] Ошибка установки coverId через PATCH: {e}")
        except Exception as e:
            print(f"  [WARNING] Ошибка проверки product_media: {e}")
    
    # Небольшая задержка для применения изменений
    import time
    print(f"\n[INFO] Ожидание применения изменений...")
    time.sleep(2.0)
    
    # Прямая проверка через GET для отладки
    print(f"[DEBUG] Прямая проверка через GET /api/product/{product_id}...")
    try:
        direct_check = client._request("GET", f"/api/product/{product_id}")
        if isinstance(direct_check, dict):
            direct_data = direct_check.get("data", direct_check)
            print(f"[DEBUG] coverId из GET: {direct_data.get('coverId')}")
            print(f"[DEBUG] customFields из GET: {direct_data.get('customFields')}")
    except Exception as e:
        print(f"[DEBUG] Ошибка прямой проверки: {e}")
    
    # Получаем состояние ПОСЛЕ UPDATE
    print("\n" + "="*60)
    print("[AFTER UPDATE] Состояние товара после обновления:")
    print("="*60)
    state_after = get_product_state(client, product_id)
    print(f"  product_media count: {state_after.get('media_count', 0)}")
    print(f"  coverId: {state_after.get('coverId')}")
    print(f"  customFields.internal_barcode: {state_after.get('internal_barcode')}")
    
    # Проверяем дубликаты
    has_duplicates = check_duplicates(client, product_id)
    
    # Финальный отчет
    print("\n" + "="*60)
    print("[CLEAN UPDATE RESULT]")
    print("="*60)
    media_before = state_before.get('media_count', 0)
    media_after = state_after.get('media_count', 0)
    cover_id_before = state_before.get('coverId')
    cover_id_after = state_after.get('coverId')
    barcode_before = state_before.get('internal_barcode')
    barcode_after = state_after.get('internal_barcode')
    
    coverId_ok = cover_id_after is not None and cover_id_after != ""
    barcode_ok = barcode_after is not None and barcode_after != ""
    
    print(f"media_before = {media_before}")
    print(f"media_after  = {media_after}")
    print(f"coverId_ok  = {coverId_ok} (coverId={cover_id_after})")
    print(f"barcode_ok  = {barcode_ok} (barcode={barcode_after})")
    print(f"duplicates  = {has_duplicates}")
    
    # Проверяем критерии успеха
    print("\n" + "="*60)
    print("[CRITERIA CHECK]")
    print("="*60)
    
    if has_duplicates:
        print("[FAIL] ЕСТЬ дубликаты изображений")
    else:
        print("[OK] НЕТ дубликатов изображений")
    
    if not coverId_ok:
        print("[FAIL] coverId NULL или пустой")
    else:
        # Проверяем, что coverId ссылается на product_media.id
        try:
            pm_search = client._request(
                "POST",
                "/api/search/product-media",
                json={
                    "filter": [
                        {"field": "productId", "type": "equals", "value": product_id},
                        {"field": "id", "type": "equals", "value": cover_id_after}
                    ],
                    "limit": 1
                }
            )
            if isinstance(pm_search, dict) and len(pm_search.get("data", [])) > 0:
                print("[OK] coverId ссылается на product_media.id")
            else:
                print("[FAIL] coverId НЕ ссылается на product_media.id")
        except Exception:
            print("[FAIL] Не удалось проверить coverId")
    
    if not barcode_ok:
        print("[FAIL] internal_barcode не заполнен")
    else:
        print("[OK] internal_barcode заполнен")
    
    if not update_media_ids and media_after == 0:
        print("[FAIL] Старые фото пропали, хотя новые не загрузились")
    elif not update_media_ids and media_after > 0:
        print("[OK] Старые фото сохранены, так как новые не загрузились")
    elif update_media_ids and media_after > 0:
        print("[OK] Новые фото загружены и привязаны")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Эксперимент: проверка влияния version context на UPDATE product.coverId и customFields.
Shopware 6.7.5.1 использует versioning для draft/live версий.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from clients.shopware_client import ShopwareClient, ShopwareConfig
from full_import import load_json, find_product_by_number


def get_default_version_id(client: ShopwareClient) -> str:
    """Получает default versionId через API."""
    try:
        # Пробуем через /api/version
        versions = client._request("GET", "/api/version")
        
        if isinstance(versions, dict):
            data = versions.get("data", [])
            if data:
                print(f"[DEBUG] Найдено версий: {len(data)}")
                # Ищем live версию
                for version in data:
                    name = version.get("name", "")
                    v_id = version.get("id")
                    print(f"[DEBUG] Version: name={name}, id={v_id}")
                    if name == "live" or v_id == "0fa91ce3e96a4bc2be4bd9ce85c3cf24":
                        return v_id
                # Если не нашли, берем первую
                return data[0].get("id")
        
        # Fallback: используем известный default versionId для Shopware 6.7
        # Обычно это "0fa91ce3e96a4bc2be4bd9ce85c3cf24" (live version)
        return "0fa91ce3e96a4bc2be4bd9ce85c3cf24"
    except Exception as e:
        print(f"[WARNING] Ошибка получения versionId: {e}")
        # Fallback на известный default
        return "0fa91ce3e96a4bc2be4bd9ce85c3cf24"


def get_product_media_first(client: ShopwareClient, product_id: str) -> str:
    """Получает ID первого product_media (position=0)."""
    try:
        pm_search = client._request(
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
        if isinstance(pm_search, dict):
            pm_list = pm_search.get("data", [])
            if pm_list:
                return pm_list[0].get("id")
    except Exception:
        pass
    return None


def read_product_via_search(client: ShopwareClient, product_id: str) -> dict:
    """Читает товар через Search API."""
    try:
        search_result = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [{"field": "id", "type": "equals", "value": product_id}],
                "limit": 1
            }
        )
        if isinstance(search_result, dict):
            data_list = search_result.get("data", [])
            if data_list:
                return data_list[0]
    except Exception:
        pass
    return {}


def main() -> int:
    """Проверяет влияние version context на UPDATE."""
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
    
    print("="*70)
    print("[EXPERIMENT] Проверка влияния version context на UPDATE")
    print("="*70)
    
    # Находим товар
    print(f"\n[INFO] Поиск товара: productNumber = {product_number}")
    product_id = find_product_by_number(client, product_number)
    if not product_id:
        print(f"[ERROR] Товар не найден: {product_number}")
        return 1
    
    print(f"[OK] Товар найден: {product_id}")
    
    # Получаем default versionId
    print(f"\n[INFO] Получение default versionId...")
    version_id = get_default_version_id(client)
    print(f"[OK] Default versionId: {version_id}")
    
    # Получаем первый product_media для coverId
    print(f"\n[INFO] Получение первого product_media...")
    cover_pm_id = get_product_media_first(client, product_id)
    if not cover_pm_id:
        print(f"[ERROR] product_media не найден")
        return 1
    
    print(f"[OK] product_media[position=0].id: {cover_pm_id}")
    
    # Читаем состояние ДО UPDATE
    print("\n" + "="*70)
    print("[BEFORE] Состояние ДО UPDATE:")
    print("="*70)
    state_before = read_product_via_search(client, product_id)
    print(f"coverId: {state_before.get('coverId')}")
    print(f"customFields: {state_before.get('customFields')}")
    
    # ЭКСПЕРИМЕНТ 1: UPDATE БЕЗ versionId
    print("\n" + "="*70)
    print("[EXPERIMENT 1] UPDATE БЕЗ versionId:")
    print("="*70)
    
    payload_without_version = {
        "id": product_id,
        "coverId": cover_pm_id,
        "customFields": {
            "internal_barcode": "9441705"
        }
    }
    
    try:
        print(f"[INFO] Выполнение PATCH без versionId...")
        client._request("PATCH", f"/api/product/{product_id}", json=payload_without_version)
        print(f"[OK] PATCH выполнен")
        
        time.sleep(1.0)
        
        state_after_1 = read_product_via_search(client, product_id)
        print(f"\n[RESULT] После UPDATE без versionId:")
        print(f"  coverId: {state_after_1.get('coverId')}")
        print(f"  customFields.internal_barcode: {state_after_1.get('customFields', {}).get('internal_barcode')}")
    except Exception as e:
        print(f"[ERROR] Ошибка UPDATE без versionId: {e}")
    
    # ЭКСПЕРИМЕНТ 2: UPDATE С versionId через header
    print("\n" + "="*70)
    print("[EXPERIMENT 2] UPDATE С versionId через header:")
    print("="*70)
    
    payload_with_version = {
        "id": product_id,
        "coverId": cover_pm_id,
        "customFields": {
            "internal_barcode": "9441705"
        }
    }
    
    state_after_2 = {}
    try:
        print(f"[INFO] Выполнение PATCH с versionId в header...")
        # Сохраняем текущие заголовки
        original_headers = client._session.headers.copy()
        # Добавляем versionId в header
        client._session.headers["sw-version-id"] = version_id
        
        client._request("PATCH", f"/api/product/{product_id}", json=payload_with_version)
        print(f"[OK] PATCH выполнен с versionId в header")
        
        # Восстанавливаем заголовки
        client._session.headers = original_headers
        
        time.sleep(1.0)
        
        state_after_2 = read_product_via_search(client, product_id)
        print(f"\n[RESULT] После UPDATE с versionId в header:")
        print(f"  coverId: {state_after_2.get('coverId')}")
        print(f"  customFields.internal_barcode: {state_after_2.get('customFields', {}).get('internal_barcode')}")
    except Exception as e:
        print(f"[ERROR] Ошибка UPDATE с versionId в header: {e}")
        # Восстанавливаем заголовки в случае ошибки
        if 'original_headers' in locals():
            client._session.headers = original_headers
        state_after_2 = read_product_via_search(client, product_id)
    
    # ЭКСПЕРИМЕНТ 3: UPDATE С versionId через Sync API (только customFields)
    print("\n" + "="*70)
    print("[EXPERIMENT 3] UPDATE customFields через Sync API с versionId:")
    print("="*70)
    
    state_after_3 = {}
    try:
        print(f"[INFO] Выполнение Sync API для customFields с versionId...")
        # Для Sync API нужны обязательные поля, поэтому обновляем только customFields
        # coverId обновим отдельно через PATCH
        sync_payload = [{
            "entity": "product",
            "action": "upsert",
            "payload": [{
                "id": product_id,
                "customFields": {
                    "internal_barcode": "9441705"
                }
            }]
        }]
        
        # Добавляем versionId в header для Sync API
        original_headers = client._session.headers.copy()
        client._session.headers["sw-version-id"] = version_id
        
        client._request("POST", "/api/_action/sync", json=sync_payload)
        print(f"[OK] Sync API для customFields выполнен с versionId")
        
        # Обновляем coverId отдельно через PATCH с versionId
        client._request("PATCH", f"/api/product/{product_id}", json={"coverId": cover_pm_id})
        print(f"[OK] PATCH для coverId выполнен с versionId")
        
        # Восстанавливаем заголовки
        client._session.headers = original_headers
        
        time.sleep(1.0)
        
        state_after_3 = read_product_via_search(client, product_id)
        print(f"\n[RESULT] После UPDATE через Sync API + PATCH с versionId:")
        print(f"  coverId: {state_after_3.get('coverId')}")
        print(f"  customFields.internal_barcode: {state_after_3.get('customFields', {}).get('internal_barcode')}")
    except Exception as e:
        print(f"[ERROR] Ошибка UPDATE через Sync API: {e}")
        if 'original_headers' in locals():
            client._session.headers = original_headers
        state_after_3 = read_product_via_search(client, product_id)
    
    # Финальное сравнение
    print("\n" + "="*70)
    print("[COMPARISON] Сравнение результатов:")
    print("="*70)
    
    print(f"\nДО UPDATE:")
    print(f"  coverId: {state_before.get('coverId')}")
    print(f"  customFields.internal_barcode: {state_before.get('customFields', {}).get('internal_barcode')}")
    
    print(f"\nПОСЛЕ UPDATE без versionId:")
    print(f"  coverId: {state_after_1.get('coverId')}")
    print(f"  customFields.internal_barcode: {state_after_1.get('customFields', {}).get('internal_barcode')}")
    
    print(f"\nПОСЛЕ UPDATE с versionId (header):")
    print(f"  coverId: {state_after_2.get('coverId')}")
    print(f"  customFields.internal_barcode: {state_after_2.get('customFields', {}).get('internal_barcode')}")
    
    print(f"\nПОСЛЕ UPDATE через Sync API с versionId:")
    print(f"  coverId: {state_after_3.get('coverId')}")
    print(f"  customFields.internal_barcode: {state_after_3.get('customFields', {}).get('internal_barcode')}")
    
    # Вывод
    print("\n" + "="*70)
    print("[CONCLUSION]")
    print("="*70)
    
    without_version_ok = (
        state_after_1.get('coverId') == cover_pm_id and
        state_after_1.get('customFields', {}).get('internal_barcode') == "9441705"
    )
    
    with_version_header_ok = (
        state_after_2.get('coverId') == cover_pm_id and
        state_after_2.get('customFields', {}).get('internal_barcode') == "9441705"
    )
    
    with_version_sync_ok = (
        state_after_3.get('coverId') == cover_pm_id and
        state_after_3.get('customFields', {}).get('internal_barcode') == "9441705"
    )
    
    print(f"\nБЕЗ versionId: {'OK' if without_version_ok else 'FAIL'}")
    print(f"С versionId (header): {'OK' if with_version_header_ok else 'FAIL'}")
    print(f"С versionId (Sync API): {'OK' if with_version_sync_ok else 'FAIL'}")
    
    if not without_version_ok and (with_version_header_ok or with_version_sync_ok):
        print("\n[CONFIRMED] Проблема была в version context!")
        print("UPDATE требует явного указания versionId для сохранения coverId и customFields.")
    elif without_version_ok:
        print("\n[NOT CONFIRMED] Version context не является причиной проблемы.")
        print("UPDATE работает без versionId.")
    else:
        print("\n[UNKNOWN] Ни один метод не сохранил данные.")
        print("Проблема может быть в другом месте.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


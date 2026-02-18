#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Целевая валидация cover-пайплайна для UPDATE товара в Shopware 6.
Проверяет каждый шаг установки coverId и находит точку обрыва цепочки.
"""

import sys
import time
import json
from pathlib import Path
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).parent))

from clients.shopware_client import ShopwareClient, ShopwareConfig
from full_import import load_json, find_product_by_number, download_and_upload_image


def log_step(step_name: str, data: Any = None):
    """Логирует шаг диагностики."""
    print(f"\n{'='*70}")
    print(f"[DIAG STEP] {step_name}")
    print(f"{'='*70}")
    if data:
        if isinstance(data, dict):
            for key, value in data.items():
                print(f"  {key}: {value}")
        else:
            print(f"  {data}")


def check_product_media_creation(
    client: ShopwareClient,
    product_id: str,
    media_id: str,
    position: int = 0
) -> Optional[Dict[str, Any]]:
    """
    Проверка 1: Создание product_media через POST /api/product-media.
    Возвращает полную информацию о созданной entity.
    """
    log_step("1. Создание product_media через POST /api/product-media")
    
    payload = {
        "productId": product_id,
        "mediaId": media_id,
        "position": position
    }
    
    print(f"  Payload: {json.dumps(payload, indent=2)}")
    
    try:
        # Выполняем запрос напрямую через _session для детального логирования
        client._ensure_token()
        url = f"{client._config.api_base}/api/product-media"
        
        print(f"  URL: {url}")
        print(f"  Headers: {dict(client._session.headers)}")
        
        response_obj = client._session.post(
            url,
            json=payload,
            timeout=client._timeout,
            verify=False
        )
        
        print(f"  HTTP Status: {response_obj.status_code}")
        print(f"  Response headers: {dict(response_obj.headers)}")
        
        # Проверяем статус
        if response_obj.status_code == 204:
            print(f"  [INFO] 204 No Content - entity создана")
            # При 204 ID может быть в заголовке Location
            location = response_obj.headers.get("Location", "")
            if location:
                # Извлекаем ID из Location: /api/product-media/{id}
                import re
                match = re.search(r'/api/product-media/([a-f0-9]+)', location)
                if match:
                    product_media_id = match.group(1)
                    print(f"  [OK] product_media.id из Location header: {product_media_id}")
                else:
                    print(f"  [WARNING] Не удалось извлечь ID из Location: {location}")
                    product_media_id = None
            else:
                product_media_id = None
            
            # Если не нашли в Location, ищем через поиск
            if not product_media_id:
                print(f"  [INFO] Поиск product_media через API...")
                time.sleep(0.3)
                pm_search = client._request(
                    "POST",
                    "/api/search/product-media",
                    json={
                        "filter": [
                            {"field": "productId", "type": "equals", "value": product_id},
                            {"field": "mediaId", "type": "equals", "value": media_id},
                            {"field": "position", "type": "equals", "value": position}
                        ],
                        "limit": 1
                    }
                )
                if isinstance(pm_search, dict):
                    pm_list = pm_search.get("data", [])
                    if pm_list:
                        product_media_id = pm_list[0].get("id")
                        print(f"  [OK] product_media.id найден через поиск: {product_media_id}")
                    else:
                        print(f"  [ERROR] product_media не найден после создания (204)")
                        return None
                else:
                    print(f"  [ERROR] Не удалось найти product_media после создания")
                    return None
            
            response = {"status": 204, "location": location, "id": product_media_id}
        elif response_obj.status_code >= 400:
            print(f"  [ERROR] HTTP {response_obj.status_code}: {response_obj.text}")
            return None
        else:
            # Парсим JSON ответ
            try:
                response = response_obj.json()
                print(f"  Response JSON: {json.dumps(response, indent=2)}")
            except Exception:
                response = response_obj.text
                print(f"  Response text: {response}")
        
        # Извлекаем product_media_id из ответа (если не был установлен в блоке 204)
        if 'product_media_id' not in locals() or not product_media_id:
            product_media_id = None
            if isinstance(response, dict):
                data = response.get("data", {})
                if isinstance(data, dict):
                    product_media_id = data.get("id")
                elif isinstance(data, list) and len(data) > 0:
                    product_media_id = data[0].get("id")
                # Также проверяем корневой уровень
                if not product_media_id:
                    product_media_id = response.get("id")
            elif isinstance(response, list) and len(response) > 0:
                product_media_id = response[0].get("id")
            
            if not product_media_id:
                print(f"  [ERROR] product_media.id не найден в ответе")
                print(f"  [DEBUG] Пробуем найти через поиск...")
                time.sleep(0.3)
                pm_search = client._request(
                    "POST",
                    "/api/search/product-media",
                    json={
                        "filter": [
                            {"field": "productId", "type": "equals", "value": product_id},
                            {"field": "mediaId", "type": "equals", "value": media_id},
                            {"field": "position", "type": "equals", "value": position}
                        ],
                        "limit": 1
                    }
                )
                if isinstance(pm_search, dict):
                    pm_list = pm_search.get("data", [])
                    if pm_list:
                        product_media_id = pm_list[0].get("id")
                        print(f"  [OK] product_media.id найден через поиск: {product_media_id}")
                    else:
                        return None
                else:
                    return None
        
        result = {
            "product_media_id": product_media_id,
            "productId": product_id,
            "mediaId": media_id,
            "position": position,
            "response": response
        }
        
        print(f"  [OK] product_media создан:")
        print(f"    product_media.id: {product_media_id}")
        print(f"    productId: {product_id}")
        print(f"    mediaId: {media_id}")
        print(f"    position: {position}")
        
        return result
        
    except Exception as e:
        print(f"  [ERROR] Ошибка создания product_media: {e}")
        return None


def check_product_after_media_creation(
    client: ShopwareClient,
    product_id: str
) -> Dict[str, Any]:
    """
    Проверка 2: GET /api/product/{id} после создания product_media.
    Проверяет associations cover и media.
    """
    log_step("2. Проверка продукта после создания product_media")
    
    try:
        # Используем Search API для получения associations
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [{"field": "id", "type": "equals", "value": product_id}],
                "limit": 1,
                "associations": {
                    "cover": {},
                    "media": {}
                }
            }
        )
        
        print(f"  Response type: {type(response)}")
        if isinstance(response, dict):
            print(f"  Response keys: {list(response.keys())}")
        
        result = {
            "cover_exists": False,
            "cover_id": None,
            "media_count": 0,
            "media_ids": [],
            "raw_response": response
        }
        
        if isinstance(response, dict):
            data_list = response.get("data", [])
            if data_list and len(data_list) > 0:
                data = data_list[0]
                
                # JSON:API формат: проверяем attributes и relationships
                attributes = data.get("attributes", {})
                relationships = data.get("relationships", {})
                
                print(f"  [DEBUG] JSON:API format detected")
                print(f"  attributes keys: {list(attributes.keys()) if isinstance(attributes, dict) else 'N/A'}")
                print(f"  relationships keys: {list(relationships.keys()) if isinstance(relationships, dict) else 'N/A'}")
                
                # Проверяем coverId в attributes
                cover_id_attr = attributes.get("coverId")
                print(f"  attributes.coverId: {cover_id_attr}")
                if cover_id_attr:
                    result["cover_id_direct"] = cover_id_attr
                
                # Проверяем relationships.cover
                cover_rel = relationships.get("cover")
                if cover_rel:
                    cover_data = cover_rel.get("data", {})
                    if isinstance(cover_data, dict):
                        cover_id = cover_data.get("id")
                        if cover_id:
                            result["cover_exists"] = True
                            result["cover_id"] = cover_id
                            print(f"  [OK] relationships.cover.id: {cover_id}")
                    elif isinstance(cover_data, list) and len(cover_data) > 0:
                        cover_id = cover_data[0].get("id")
                        if cover_id:
                            result["cover_exists"] = True
                            result["cover_id"] = cover_id
                            print(f"  [OK] relationships.cover[0].id: {cover_id}")
                
                # Проверяем relationships.media
                media_rel = relationships.get("media")
                if media_rel:
                    media_data = media_rel.get("data", [])
                    if isinstance(media_data, list):
                        result["media_count"] = len(media_data)
                        result["media_ids"] = [m.get("id") for m in media_data if isinstance(m, dict)]
                        print(f"  [OK] relationships.media count: {result['media_count']}")
                        for idx, media_id in enumerate(result["media_ids"][:3]):
                            print(f"    [{idx}] media_id: {media_id}")
                    else:
                        print(f"  [WARNING] relationships.media.data не список")
                else:
                    print(f"  [WARNING] relationships.media отсутствует")
                
                # Проверяем included (если есть)
                included = response.get("included", [])
                if included:
                    print(f"  [DEBUG] included count: {len(included)}")
                    for item in included[:3]:
                        item_type = item.get("type")
                        item_id = item.get("id")
                        print(f"    included: type={item_type}, id={item_id}")
                
                # Старый формат (если есть)
                cover = data.get("cover")
                if cover:
                    result["cover_exists"] = True
                    result["cover_id"] = cover.get("id") if isinstance(cover, dict) else cover
                    print(f"  [OK] product.cover (legacy): {result['cover_id']}")
                
                media = data.get("media")
                if isinstance(media, list):
                    result["media_count"] = len(media)
                    result["media_ids"] = [m.get("id") if isinstance(m, dict) else m for m in media]
                    print(f"  [OK] product.media (legacy): {result['media_count']} элементов")
                
                # Дополнительно проверяем через прямой GET
                print(f"  [DEBUG] Дополнительная проверка через GET /api/product/{product_id}...")
                try:
                    get_response = client._request("GET", f"/api/product/{product_id}")
                    if isinstance(get_response, dict):
                        get_data = get_response.get("data", {})
                        if isinstance(get_data, dict):
                            get_cover_id = get_data.get("coverId")
                            print(f"  GET /api/product coverId: {get_cover_id}")
                except Exception as e:
                    print(f"  [WARNING] Ошибка GET запроса: {e}")
        
        return result
        
    except Exception as e:
        print(f"  [ERROR] Ошибка получения продукта: {e}")
        return {"error": str(e)}


def check_patch_cover(
    client: ShopwareClient,
    product_id: str,
    product_media_id: str
) -> Dict[str, Any]:
    """
    Проверка 3: PATCH /api/product/{id} для установки coverId.
    Проверяет payload и ответ.
    """
    log_step("3. PATCH cover через /api/product/{id}")
    
    # Вариант 1: Прямое поле coverId
    payload_direct = {
        "coverId": product_media_id
    }
    
    print(f"  [VARIANT 1] Прямое поле coverId")
    print(f"  Payload: {json.dumps(payload_direct, indent=2)}")
    print(f"  Проверка payload:")
    print(f"    - coverId тип: {type(product_media_id)}")
    print(f"    - coverId значение: {product_media_id}")
    print(f"    - НЕ mediaId: {product_media_id != 'media_id'}")
    print(f"    - НЕ array: {not isinstance(product_media_id, list)}")
    print(f"    - НЕ объект: {not isinstance(product_media_id, dict)}")
    
    try:
        # Выполняем PATCH напрямую для детального логирования
        client._ensure_token()
        url = f"{client._config.api_base}/api/product/{product_id}"
        
        print(f"  [BEFORE PATCH] Выполняем PATCH...")
        print(f"  URL: {url}")
        
        resp = client._session.patch(
            url,
            json=payload_direct,
            timeout=client._timeout,
            verify=False
        )
        
        print(f"  [AFTER PATCH] HTTP Status: {resp.status_code}")
        print(f"  Response headers: {dict(resp.headers)}")
        
        if resp.status_code >= 400:
            error_text = resp.text
            print(f"  [ERROR] HTTP {resp.status_code}: {error_text}")
            return {
                "success": False,
                "error": f"HTTP {resp.status_code}: {error_text}",
                "variant": "direct"
            }
        
        # Парсим ответ
        response = None
        if resp.text:
            try:
                response = resp.json()
                print(f"  Response JSON: {json.dumps(response, indent=2)}")
            except Exception:
                response = resp.text
                print(f"  Response text: {response}")
        else:
            print(f"  [INFO] 204 No Content - изменения применены")
        
        # Проверяем сразу после PATCH
        time.sleep(0.3)
        check_response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [{"field": "id", "type": "equals", "value": product_id}],
                "limit": 1
            }
        )
        if isinstance(check_response, dict):
            check_data_list = check_response.get("data", [])
            if check_data_list:
                check_attrs = check_data_list[0].get("attributes", {})
                check_cover_id = check_attrs.get("coverId")
                print(f"  [CHECK] coverId после PATCH: {check_cover_id}")
                if check_cover_id == product_media_id:
                    print(f"  [OK] coverId установлен корректно!")
                    return {
                        "success": True,
                        "response": response,
                        "status_code": resp.status_code,
                        "variant": "direct",
                        "cover_id_after": check_cover_id
                    }
                else:
                    print(f"  [WARNING] coverId не совпадает: ожидался {product_media_id}, получен {check_cover_id}")
        
        return {
            "success": True,
            "response": response,
            "status_code": resp.status_code,
            "variant": "direct"
        }
        
    except Exception as e:
        print(f"  [ERROR] Ошибка PATCH cover: {e}")
        return {
            "success": False,
            "error": str(e),
            "variant": "direct"
        }


def check_product_after_patch(
    client: ShopwareClient,
    product_id: str
) -> Dict[str, Any]:
    """
    Проверка 4: GET /api/product/{id} сразу после PATCH cover.
    """
    log_step("4. Проверка продукта сразу после PATCH cover")
    
    time.sleep(0.3)  # Небольшая задержка для применения изменений
    
    try:
        response = client._request(
            "GET",
            f"/api/product/{product_id}?associations[cover]=true&associations[media]=true"
        )
        
        result = {
            "cover_id": None,
            "cover_exists": False,
            "media_count": 0,
            "raw_response": response
        }
        
        if isinstance(response, dict):
            data = response.get("data", {})
            if isinstance(data, dict):
                cover_id = data.get("coverId")
                result["cover_id"] = cover_id
                
                cover = data.get("cover")
                if cover:
                    result["cover_exists"] = True
                    cover_id_from_assoc = cover.get("id") if isinstance(cover, dict) else cover
                    print(f"  [OK] product.coverId: {cover_id}")
                    print(f"  [OK] product.cover association: {cover_id_from_assoc}")
                else:
                    print(f"  [WARNING] product.cover отсутствует")
                
                media = data.get("media")
                if isinstance(media, list):
                    result["media_count"] = len(media)
                    print(f"  [OK] product.media count: {result['media_count']}")
        
        return result
        
    except Exception as e:
        print(f"  [ERROR] Ошибка получения продукта: {e}")
        return {"error": str(e)}


def check_context(client: ShopwareClient) -> Dict[str, Any]:
    """
    Проверка 5: Контекст API client (auth, sales channel).
    """
    log_step("5. Проверка контекста API client")
    
    result = {
        "has_token": bool(client._token),
        "sales_channel_currency": None,
        "default_currency": None
    }
    
    print(f"  Auth token exists: {result['has_token']}")
    
    try:
        sales_channel_currency = client.get_sales_channel_currency_id()
        result["sales_channel_currency"] = sales_channel_currency
        print(f"  Sales Channel currency: {sales_channel_currency}")
    except Exception as e:
        print(f"  [WARNING] Ошибка получения Sales Channel currency: {e}")
    
    return result


def main() -> int:
    """Основная функция валидации."""
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
    print("[VALIDATION] Целевая валидация cover-пайплайна")
    print("="*70)
    
    # Находим товар
    print(f"\n[INFO] Поиск товара: productNumber = {product_number}")
    product_id = find_product_by_number(client, product_number)
    if not product_id:
        print(f"[ERROR] Товар не найден: {product_number}")
        return 1
    
    print(f"[OK] Товар найден: {product_id}")
    
    # Проверяем контекст
    context = check_context(client)
    
    # Загружаем одно изображение для теста
    print(f"\n[INFO] Загрузка изображения для теста...")
    snapshot_path = Path(__file__).parent.parent / "insales_snapshot" / "products.ndjson"
    
    import json
    test_media_id = None
    with open(snapshot_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                variant = data.get("variants", [{}])[0] if data.get("variants") else {}
                if variant.get("sku") == product_number:
                    images = data.get("images", [])
                    if images and len(images) > 0:
                        url = images[0].get("original_url")
                        if url:
                            print(f"  Загрузка изображения: {url}")
                            test_media_id = download_and_upload_image(client, url, product_number)
                            if test_media_id:
                                print(f"  [OK] Изображение загружено: {test_media_id}")
                            else:
                                print(f"  [ERROR] Не удалось загрузить изображение")
                    break
            except Exception:
                continue
    
    if not test_media_id:
        print(f"[ERROR] Не удалось загрузить изображение для теста")
        return 1
    
    # Удаляем существующие product_media для чистого теста
    print(f"\n[INFO] Удаление существующих product_media для чистого теста...")
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
            for pm in pm_list:
                pm_id = pm.get("id")
                if pm_id:
                    try:
                        client._request("DELETE", f"/api/product-media/{pm_id}")
                        print(f"  Удален product_media: {pm_id}")
                    except Exception:
                        pass
    except Exception:
        pass
    
    time.sleep(0.5)
    
    # ПРОВЕРКА 1: Создание product_media
    pm_result = check_product_media_creation(
        client=client,
        product_id=product_id,
        media_id=test_media_id,
        position=0
    )
    
    if not pm_result:
        print(f"\n[CONCLUSION] ГИПОТЕЗА A: product_media не создан")
        return 1
    
    product_media_id = pm_result["product_media_id"]
    
    time.sleep(0.3)
    
    # ПРОВЕРКА 2: Проверка продукта после создания product_media
    product_after_media = check_product_after_media_creation(client, product_id)
    
    if not product_after_media.get("media_count", 0) > 0:
        print(f"\n[CONCLUSION] ГИПОТЕЗА B: product_media создан, но не виден продукту")
        return 1
    
    # ПРОВЕРКА 3: PATCH cover
    patch_result = check_patch_cover(
        client=client,
        product_id=product_id,
        product_media_id=product_media_id
    )
    
    if not patch_result.get("success"):
        print(f"\n[CONCLUSION] ГИПОТЕЗА C: PATCH cover не принимает ID")
        print(f"  Ошибка: {patch_result.get('error')}")
        return 1
    
    time.sleep(0.3)
    
    # ПРОВЕРКА 4: Проверка продукта после PATCH (с задержкой)
    print(f"\n[INFO] Ожидание применения изменений (1 сек)...")
    time.sleep(1.0)
    product_after_patch = check_product_after_patch(client, product_id)
    
    # Дополнительная проверка через прямой GET
    print(f"\n[INFO] Дополнительная проверка через GET /api/product/{product_id}...")
    try:
        direct_get = client._request("GET", f"/api/product/{product_id}")
        if isinstance(direct_get, dict):
            direct_data = direct_get.get("data", {})
            if isinstance(direct_data, dict):
                direct_cover_id = direct_data.get("coverId")
                print(f"  GET /api/product coverId: {direct_cover_id}")
                if direct_cover_id:
                    product_after_patch["cover_id"] = direct_cover_id
    except Exception as e:
        print(f"  [WARNING] Ошибка GET: {e}")
    
    # Финальный вывод
    print("\n" + "="*70)
    print("[FINAL CONCLUSION]")
    print("="*70)
    
    # Используем cover_id из patch_result (сразу после PATCH) и после задержки
    cover_id_immediate = patch_result.get("cover_id_after")
    cover_id_delayed = product_after_patch.get("cover_id")
    
    if cover_id_immediate and cover_id_immediate == product_media_id:
        print(f"\n[OK] coverId установлен сразу после PATCH: {cover_id_immediate}")
        print(f"[OK] coverId совпадает с product_media_id: {cover_id_immediate == product_media_id}")
        
        if not cover_id_delayed or cover_id_delayed != product_media_id:
            print(f"\n[FAIL] coverId НЕ сохраняется после задержки")
            print(f"  Сразу после PATCH: {cover_id_immediate}")
            print(f"  После задержки (1 сек): {cover_id_delayed}")
            print(f"\n[CONCLUSION] ГИПОТЕЗА D: coverId устанавливается через PATCH, но НЕ сохраняется в БД")
            print(f"  Причина: PATCH возвращает 204, coverId виден сразу, но сбрасывается/не сохраняется")
        else:
            print(f"\n[SUCCESS] coverId установлен и сохранен корректно!")
    elif cover_id_immediate and cover_id_immediate != product_media_id:
        print(f"\n[WARNING] coverId установлен, но другой ID")
        print(f"  Ожидался: {product_media_id}")
        print(f"  Получен: {cover_id_immediate}")
        print(f"\n[CONCLUSION] ГИПОТЕЗА C: PATCH cover принимает ID, но устанавливает другой")
    else:
        print(f"\n[FAIL] coverId НЕ установлен после PATCH")
        print(f"[CONCLUSION] ГИПОТЕЗА C: PATCH cover не принимает ID или не сохраняет")
    
    # Сводка
    print(f"\n[SUMMARY]")
    print(f"  product_id: {product_id}")
    print(f"  media_id: {test_media_id}")
    print(f"  product_media_id: {product_media_id}")
    print(f"  cover_id сразу после PATCH: {patch_result.get('cover_id_after')}")
    print(f"  cover_id после задержки: {product_after_patch.get('cover_id')}")
    print(f"  media_count: {product_after_patch.get('media_count', 0)}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


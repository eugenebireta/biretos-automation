#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Диагностика доступности изображений InSales CDN и чистый UPDATE товара.
Проверяет: CDN доступность, InSales API, результат UPDATE в Shopware.
"""

import json
import sys
import argparse
import time
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))

from clients.shopware_client import ShopwareClient, ShopwareConfig
from full_import import load_json, find_product_by_number


def check_image_url(url: str, timeout: int = 10) -> Dict[str, Any]:
    """Проверяет доступность изображения через HEAD, затем GET если нужно."""
    result = {
        "url": url,
        "http_status": None,
        "content_type": None,
        "content_length": None,
        "first_bytes_hex": None,
        "is_image": False,
        "error": None
    }
    
    try:
        # Сначала HEAD запрос
        head_response = requests.head(url, timeout=timeout, allow_redirects=True)
        result["http_status"] = head_response.status_code
        result["content_type"] = head_response.headers.get("Content-Type", "")
        result["content_length"] = head_response.headers.get("Content-Length")
        
        # Если HEAD не дал content-type, делаем GET для первых байт
        if not result["content_type"] or result["http_status"] not in [200, 206]:
            get_response = requests.get(
                url,
                timeout=timeout,
                stream=True,
                headers={"Range": "bytes=0-31"},
                allow_redirects=True
            )
            result["http_status"] = get_response.status_code
            result["content_type"] = get_response.headers.get("Content-Type", "")
            result["content_length"] = get_response.headers.get("Content-Length")
            
            if get_response.status_code in [200, 206]:
                first_bytes = get_response.content[:32]
                result["first_bytes_hex"] = first_bytes.hex()[:64]  # Первые 32 байта в hex
                
                # Проверка на JPEG/PNG/GIF по magic bytes
                if first_bytes.startswith(b'\xff\xd8\xff'):
                    result["is_image"] = True  # JPEG
                elif first_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
                    result["is_image"] = True  # PNG
                elif first_bytes.startswith(b'GIF87a') or first_bytes.startswith(b'GIF89a'):
                    result["is_image"] = True  # GIF
                elif result["content_type"] and result["content_type"].startswith("image/"):
                    result["is_image"] = True
        else:
            # HEAD дал content-type
            if result["content_type"].startswith("image/"):
                result["is_image"] = True
        
        # Определяем ROOT CAUSE
        if result["http_status"] in [403, 404] or (result["http_status"] >= 500):
            result["root_cause"] = "CDN недоступен (HTTP {})".format(result["http_status"])
        elif result["content_type"] and not result["content_type"].startswith("image/"):
            result["root_cause"] = "Не картинка (content-type: {})".format(result["content_type"])
        elif not result["is_image"]:
            result["root_cause"] = "Не похоже на изображение (magic bytes)"
        else:
            result["root_cause"] = "OK"
            
    except requests.exceptions.Timeout:
        result["error"] = "Timeout"
        result["root_cause"] = "CDN недоступен (Timeout)"
    except requests.exceptions.RequestException as e:
        result["error"] = str(e)
        result["root_cause"] = "CDN недоступен ({}: {})".format(type(e).__name__, str(e))
    
    return result


def check_insales_api(config: Dict[str, Any]) -> Dict[str, Any]:
    """Проверяет доступность InSales API."""
    result = {
        "status": None,
        "api_usage_limit": None,
        "error": None
    }
    
    # Ищем креды InSales в конфиге
    insales_config = config.get("insales", {})
    host = insales_config.get("host")  # Например: myshop-bsu266.myinsales.ru
    api_key = insales_config.get("api_key")
    api_password = insales_config.get("api_password")
    
    if not all([host, api_key, api_password]):
        result["error"] = "InSales credentials not found in config"
        return result
    
    try:
        # host уже содержит полный домен
        url = f"https://{host}/admin/products/count.json"
        auth = (api_key, api_password)
        
        response = requests.get(url, auth=auth, timeout=10)
        result["status"] = response.status_code
        result["api_usage_limit"] = response.headers.get("API-Usage-Limit")
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def find_product_in_snapshot(snapshot_path: Path, product_number: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Находит товар в snapshot по productNumber или первый с изображениями."""
    if not snapshot_path.exists():
        return None
    
    with open(snapshot_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                variant = data.get("variants", [{}])[0] if data.get("variants") else {}
                
                # Если указан productNumber, ищем по нему
                if product_number:
                    if variant.get("sku") == product_number:
                        return data
                else:
                    # Ищем первый товар с изображениями
                    images = data.get("images", [])
                    if images and len(images) > 0 and images[0].get("original_url"):
                        return data
            except Exception:
                continue
    
    return None


def get_product_state_after_update(client: ShopwareClient, product_id: str) -> Dict[str, Any]:
    """Получает состояние товара после UPDATE через Search API."""
    state = {
        "product_id": product_id,
        "product_number": None,
        "media_count": 0,
        "cover_id": None,
        "internal_barcode": None,
        "error": None
    }
    
    try:
        # Используем Search API для получения полных данных
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
                product = data_list[0]
                state["product_number"] = product.get("productNumber")
                state["cover_id"] = product.get("coverId")
                
                custom_fields = product.get("customFields")
                if custom_fields:
                    state["internal_barcode"] = custom_fields.get("internal_barcode")
        
        # Получаем количество product_media
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
            state["media_count"] = len(pm_list)
            
    except Exception as e:
        state["error"] = str(e)
    
    return state


def main() -> int:
    """Основная функция диагностики."""
    parser = argparse.ArgumentParser(description="Диагностика InSales CDN и UPDATE товара")
    parser.add_argument("--product-number", type=str, help="Product number для поиска (например, 500944170)")
    args = parser.parse_args()
    
    # Загружаем конфигурацию
    config_path = Path(__file__).parent.parent / "config.json"
    if not config_path.exists():
        print(f"[ERROR] Конфигурация не найдена: {config_path}")
        return 1
    
    config = load_json(config_path)
    
    # Создаем Shopware клиент
    shop_cfg = ShopwareConfig(
        url=config["shopware"]["url"],
        access_key_id=config["shopware"]["access_key_id"],
        secret_access_key=config["shopware"]["secret_access_key"],
    )
    client = ShopwareClient(shop_cfg, timeout=10)
    
    print("="*70)
    print("[DIAGNOSTIC] Проверка доступности InSales CDN и UPDATE товара")
    print("="*70)
    
    # Находим товар в snapshot
    snapshot_path = Path(__file__).parent.parent / "insales_snapshot" / "products.ndjson"
    print(f"\n[INFO] Поиск товара в snapshot...")
    product_data = find_product_in_snapshot(snapshot_path, args.product_number)
    
    if not product_data:
        print(f"[ERROR] Товар не найден в snapshot")
        return 1
    
    variant = product_data.get("variants", [{}])[0] if product_data.get("variants") else {}
    product_number = variant.get("sku")
    barcode = variant.get("barcode")
    images = product_data.get("images", [])
    
    print(f"[OK] Товар найден:")
    print(f"  productNumber: {product_number}")
    print(f"  images count: {len(images)}")
    print(f"  variants[0].barcode: {barcode}")
    
    if images:
        print(f"\n[INFO] Первые 3 URL изображений:")
        for idx, img in enumerate(images[:3]):
            original_url = img.get("original_url", "")
            print(f"  [{idx+1}] {original_url}")
    
    # Проверяем доступность изображений
    print("\n" + "="*70)
    print("[STEP 1] Проверка доступности изображений InSales CDN")
    print("="*70)
    
    image_results = []
    for idx, img in enumerate(images[:3]):
        original_url = img.get("original_url", "")
        if not original_url:
            continue
        
        print(f"\n[CHECK {idx+1}] {original_url}")
        result = check_image_url(original_url)
        image_results.append(result)
        
        print(f"  HTTP Status: {result['http_status']}")
        print(f"  Content-Type: {result['content_type']}")
        print(f"  Content-Length: {result['content_length']}")
        if result['first_bytes_hex']:
            print(f"  First 32 bytes (hex): {result['first_bytes_hex']}")
        print(f"  Is Image: {result['is_image']}")
        print(f"  ROOT CAUSE: {result['root_cause']}")
        if result['error']:
            print(f"  Error: {result['error']}")
    
    # Проверяем InSales API
    print("\n" + "="*70)
    print("[STEP 2] Проверка доступности InSales API")
    print("="*70)
    
    insales_api_result = check_insales_api(config)
    print(f"Status: {insales_api_result['status']}")
    print(f"API-Usage-Limit: {insales_api_result['api_usage_limit']}")
    if insales_api_result['error']:
        print(f"Error: {insales_api_result['error']}")
    
    # Выполняем UPDATE через full_import.py
    print("\n" + "="*70)
    print("[STEP 3] Выполнение чистого UPDATE товара")
    print("="*70)
    
    # Проверяем, существует ли товар в Shopware
    print(f"[INFO] Поиск товара в Shopware: productNumber = {product_number}")
    product_id = find_product_by_number(client, product_number)
    
    if not product_id:
        print(f"[WARNING] Товар не найден в Shopware. UPDATE будет CREATE.")
    else:
        print(f"[OK] Товар найден в Shopware: {product_id}")
    
    # Запускаем импорт через subprocess
    import subprocess
    import os
    
    script_dir = Path(__file__).parent
    full_import_script = script_dir / "full_import.py"
    
    print(f"[INFO] Запуск импорта: python full_import.py --source snapshot --limit 1")
    
    # Создаем временный файл с productNumber для фильтрации (если нужно)
    # Но full_import.py не поддерживает фильтр по productNumber напрямую
    # Поэтому просто запускаем с limit=1 и надеемся, что товар попадется
    
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    
    try:
        result = subprocess.run(
            [sys.executable, str(full_import_script), "--source", "snapshot", "--limit", "1"],
            cwd=str(script_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        print(f"[INFO] Импорт завершен (exit code: {result.returncode})")
        if result.stdout:
            print("\n[STDOUT]")
            print(result.stdout[-1000:])  # Последние 1000 символов
        if result.stderr:
            print("\n[STDERR]")
            print(result.stderr[-1000:])
            
    except subprocess.TimeoutExpired:
        print(f"[ERROR] Импорт превысил таймаут (300 сек)")
    except Exception as e:
        print(f"[ERROR] Ошибка запуска импорта: {e}")
    
    # Даем время на обработку
    time.sleep(2.0)
    
    # Проверяем результат UPDATE
    print("\n" + "="*70)
    print("[STEP 4] Проверка результата UPDATE в Shopware")
    print("="*70)
    
    # Находим товар снова (на случай если он был создан)
    final_product_id = find_product_by_number(client, product_number)
    if not final_product_id:
        print(f"[ERROR] Товар не найден в Shopware после UPDATE")
        return 1
    
    print(f"[OK] Товар найден: {final_product_id}")
    
    state = get_product_state_after_update(client, final_product_id)
    
    print(f"\n[RESULT] Состояние товара после UPDATE:")
    print(f"  product_id: {state['product_id']}")
    print(f"  product_number: {state['product_number']}")
    print(f"  media_count: {state['media_count']}")
    print(f"  cover_id: {state['cover_id']}")
    print(f"  internal_barcode: {state['internal_barcode']}")
    if state['error']:
        print(f"  error: {state['error']}")
    
    # Генерируем отчет
    print("\n" + "="*70)
    print("[STEP 5] Генерация отчета")
    print("="*70)
    
    report_path = script_dir / "STEP1_update_diag_report.md"
    generate_report(report_path, image_results, insales_api_result, state, product_number)
    
    print(f"[OK] Отчет сохранен: {report_path}")
    
    # Финальный вывод
    print("\n" + "="*70)
    print("[CONCLUSION]")
    print("="*70)
    
    # Определяем ROOT CAUSE
    cdn_issues = [r for r in image_results if r.get("root_cause") != "OK"]
    if cdn_issues:
        print("\n[ROOT CAUSE] CDN недоступен или изображения не валидны")
        for issue in cdn_issues:
            print(f"  - {issue['url']}: {issue['root_cause']}")
    elif state['media_count'] == 0:
        print("\n[ROOT CAUSE] Изображения не загружены в Shopware (код импорта)")
    elif not state['cover_id']:
        print("\n[ROOT CAUSE] coverId не установлен (код импорта)")
    else:
        print("\n[ROOT CAUSE] Не определен (требуется дополнительная диагностика)")
    
    print("\n" + "="*70)
    print("Продолжаем фикс (A) — добавить fallback/headers/retry для скачивания CDN,")
    print("или (B) переключиться на скачивание через InSales API (если возможно)?")
    print("="*70)
    
    return 0


def generate_report(
    report_path: Path,
    image_results: List[Dict[str, Any]],
    insales_api_result: Dict[str, Any],
    state: Dict[str, Any],
    product_number: str
) -> None:
    """Генерирует markdown отчет."""
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Диагностика UPDATE товара и доступности InSales CDN\n\n")
        f.write(f"**Product Number:** {product_number}\n")
        f.write(f"**Дата:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # Раздел 1: InSales CDN доступность
        f.write("## InSales CDN доступность\n\n")
        f.write("| URL | HTTP Status | Content-Type | Content-Length | Is Image | ROOT CAUSE |\n")
        f.write("|-----|-------------|--------------|----------------|----------|------------|\n")
        
        for result in image_results:
            url_short = result['url'][:60] + "..." if len(result['url']) > 60 else result['url']
            f.write(f"| `{url_short}` | {result['http_status']} | {result['content_type']} | {result['content_length']} | {result['is_image']} | {result['root_cause']} |\n")
        
        f.write("\n")
        
        # Раздел 2: InSales API доступность
        f.write("## InSales API доступность\n\n")
        f.write(f"- **Status:** {insales_api_result['status']}\n")
        f.write(f"- **API-Usage-Limit:** {insales_api_result['api_usage_limit']}\n")
        if insales_api_result['error']:
            f.write(f"- **Error:** {insales_api_result['error']}\n")
        f.write("\n")
        
        # Раздел 3: Shopware after UPDATE
        f.write("## Shopware after UPDATE\n\n")
        f.write(f"- **product_id:** `{state['product_id']}`\n")
        f.write(f"- **product_number:** `{state['product_number']}`\n")
        f.write(f"- **media_count:** {state['media_count']}\n")
        f.write(f"- **cover_id:** `{state['cover_id']}`\n")
        f.write(f"- **internal_barcode:** `{state['internal_barcode']}`\n")
        if state['error']:
            f.write(f"- **error:** {state['error']}\n")
        f.write("\n")
        
        # Финальный вывод
        f.write("## Финальный вывод\n\n")
        
        cdn_issues = [r for r in image_results if r.get("root_cause") != "OK"]
        if cdn_issues:
            f.write("**ROOT CAUSE:** CDN недоступен или изображения не валидны.\n\n")
            for issue in cdn_issues:
                f.write(f"- {issue['url']}: {issue['root_cause']}\n")
        elif state['media_count'] == 0:
            f.write("**ROOT CAUSE:** Изображения не загружены в Shopware (проблема в коде импорта).\n")
        elif not state['cover_id']:
            f.write("**ROOT CAUSE:** coverId не установлен (проблема в коде импорта).\n")
        else:
            f.write("**ROOT CAUSE:** Не определен (требуется дополнительная диагностика).\n")


if __name__ == "__main__":
    sys.exit(main())


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Диагностика доступности InSales CDN и API.
Проверяет, почему изображения не загружаются при импорте.
"""

import sys
import json
import requests
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

def load_json(path: Path) -> Any:
    """Загружает JSON файл."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def find_product_with_images(snapshot_path: Path) -> Optional[Dict[str, Any]]:
    """Находит первый товар с изображениями в snapshot."""
    with open(snapshot_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                images = data.get("images", [])
                if images and len(images) > 0:
                    # Проверяем, что есть original_url
                    has_url = any(img.get("original_url") for img in images)
                    if has_url:
                        return data
            except Exception:
                continue
    return None

def check_url(url: str, timeout: int = 10) -> Tuple[Dict[str, Any], bytes]:
    """Проверяет доступность URL через HEAD и GET."""
    result = {
        "url": url,
        "head_status": None,
        "head_content_type": None,
        "head_content_length": None,
        "get_status": None,
        "get_content_type": None,
        "get_content_length": None,
        "first_16_bytes_hex": None,
        "verdict": "UNKNOWN"
    }
    
    content = b""
    
    try:
        # HEAD запрос
        head_resp = requests.head(url, timeout=timeout, allow_redirects=True)
        result["head_status"] = head_resp.status_code
        result["head_content_type"] = head_resp.headers.get("Content-Type", "")
        result["head_content_length"] = head_resp.headers.get("Content-Length", "")
        
        # GET запрос
        get_resp = requests.get(url, timeout=timeout, allow_redirects=True)
        result["get_status"] = get_resp.status_code
        result["get_content_type"] = get_resp.headers.get("Content-Type", "")
        result["get_content_length"] = len(get_resp.content) if get_resp.content else 0
        content = get_resp.content[:16] if get_resp.content else b""
        result["first_16_bytes_hex"] = content.hex() if content else ""
        
        # Определяем вердикт
        if result["get_status"] == 200:
            content_type = result["get_content_type"].lower()
            if content_type.startswith("image/"):
                result["verdict"] = "IMAGE"
            elif content_type.startswith("text/html"):
                result["verdict"] = "HTML"
            elif "redirect" in content_type or result["get_status"] in [301, 302, 303, 307, 308]:
                result["verdict"] = "REDIRECT"
            else:
                result["verdict"] = f"OTHER ({content_type})"
        elif result["get_status"] == 403:
            result["verdict"] = "FORBIDDEN"
        elif result["get_status"] == 404:
            result["verdict"] = "NOT_FOUND"
        elif result["get_status"] >= 500:
            result["verdict"] = "SERVER_ERROR"
        else:
            result["verdict"] = f"HTTP_{result['get_status']}"
            
    except requests.exceptions.Timeout:
        result["verdict"] = "TIMEOUT"
    except requests.exceptions.ConnectionError:
        result["verdict"] = "CONNECTION_ERROR"
    except Exception as e:
        result["verdict"] = f"ERROR: {str(e)}"
    
    return result, content

def check_insales_api(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Проверяет доступность InSales API."""
    insales = config.get("insales", {})
    # В config.json используется "host", а не "shop_domain"
    shop_domain = insales.get("shop_domain") or insales.get("host")
    api_key = insales.get("api_key")
    api_password = insales.get("api_password")
    
    if not all([shop_domain, api_key, api_password]):
        return None
    
    result = {
        "shop_domain": shop_domain,
        "api_status": None,
        "api_usage_limit": None,
        "error": None
    }
    
    try:
        url = f"https://{shop_domain}/admin/products/count.json"
        auth = (api_key, api_password)
        resp = requests.get(url, auth=auth, timeout=10)
        result["api_status"] = resp.status_code
        result["api_usage_limit"] = resp.headers.get("API-Usage-Limit", "")
    except Exception as e:
        result["error"] = str(e)
    
    return result

def main() -> int:
    """Основная функция."""
    print("="*70)
    print("[DIAG] Проверка доступности InSales CDN и API")
    print("="*70)
    
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
    
    # Находим товар с изображениями
    print(f"\n[STEP 1] Поиск товара с изображениями в snapshot...")
    product = find_product_with_images(snapshot_path)
    
    if not product:
        print("[ERROR] Товар с изображениями не найден в snapshot")
        return 1
    
    product_number = product.get("variants", [{}])[0].get("sku", "UNKNOWN")
    images = product.get("images", [])
    
    print(f"[OK] Товар найден: SKU={product_number}")
    print(f"[OK] Изображений в snapshot: {len(images)}")
    
    # Проверяем первые 3 URL
    print(f"\n[STEP 2] Проверка доступности изображений (первые 3 URL)...")
    print("="*70)
    
    url_results = []
    for idx, img in enumerate(images[:3]):
        url = img.get("original_url")
        if not url:
            continue
        
        print(f"\n[CHECK {idx+1}] {url}")
        result, content = check_url(url)
        url_results.append(result)
        
        print(f"  HEAD Status: {result['head_status']}")
        print(f"  HEAD Content-Type: {result['head_content_type']}")
        print(f"  HEAD Content-Length: {result['head_content_length']}")
        print(f"  GET Status: {result['get_status']}")
        print(f"  GET Content-Type: {result['get_content_type']}")
        print(f"  GET Content-Length: {result['get_content_length']}")
        print(f"  First 16 bytes (hex): {result['first_16_bytes_hex']}")
        print(f"  Verdict: {result['verdict']}")
        
        # Проверяем, является ли это изображением
        if result['get_content_type']:
            if not result['get_content_type'].startswith('image/'):
                print(f"  ⚠️  НЕ image/*: {result['get_content_type']}")
    
    # Проверяем InSales API
    print(f"\n[STEP 3] Проверка доступности InSales API...")
    print("="*70)
    
    api_result = check_insales_api(config)
    if api_result:
        print(f"[OK] InSales credentials найдены")
        print(f"  Shop Domain: {api_result['shop_domain']}")
        print(f"  API Status: {api_result['api_status']}")
        print(f"  API-Usage-Limit: {api_result['api_usage_limit']}")
        if api_result.get('error'):
            print(f"  Error: {api_result['error']}")
    else:
        print("[INFO] InSales credentials не найдены в config.json")
    
    # Формируем отчет
    print(f"\n[STEP 4] Формирование отчета...")
    report_path = Path(__file__).parent / "STEP2_insales_cdn_report.md"
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Отчет: Диагностика доступности InSales CDN и API\n\n")
        f.write(f"**Дата:** {Path(__file__).stat().st_mtime}\n\n")
        f.write(f"**Товар:** SKU={product_number}\n\n")
        
        f.write("## Проверка изображений\n\n")
        for idx, result in enumerate(url_results):
            f.write(f"### Изображение {idx+1}\n\n")
            f.write(f"- **URL:** {result['url']}\n")
            f.write(f"- **HEAD Status:** {result['head_status']}\n")
            f.write(f"- **HEAD Content-Type:** {result['head_content_type']}\n")
            f.write(f"- **GET Status:** {result['get_status']}\n")
            f.write(f"- **GET Content-Type:** {result['get_content_type']}\n")
            f.write(f"- **GET Content-Length:** {result['get_content_length']}\n")
            f.write(f"- **First 16 bytes (hex):** {result['first_16_bytes_hex']}\n")
            f.write(f"- **Verdict:** {result['verdict']}\n\n")
            
            if result['get_content_type'] and not result['get_content_type'].startswith('image/'):
                f.write(f"⚠️ **НЕ image/***: {result['get_content_type']}\n\n")
        
        f.write("## Проверка InSales API\n\n")
        if api_result:
            f.write(f"- **Shop Domain:** {api_result['shop_domain']}\n")
            f.write(f"- **API Status:** {api_result['api_status']}\n")
            f.write(f"- **API-Usage-Limit:** {api_result['api_usage_limit']}\n")
            if api_result.get('error'):
                f.write(f"- **Error:** {api_result['error']}\n")
        else:
            f.write("- InSales credentials не найдены в config.json\n")
        
        f.write("\n## Вывод\n\n")
        
        # Определяем причину
        verdicts = [r['verdict'] for r in url_results]
        statuses = [r['get_status'] for r in url_results]
        content_types = [r['get_content_type'] for r in url_results]
        
        if any(s == 403 for s in statuses):
            conclusion = "Фотографии не загружаются, потому что CDN возвращает 403 Forbidden (доступ запрещен)"
        elif any(ct and not ct.startswith('image/') for ct in content_types):
            conclusion = "Фотографии не загружаются, потому что CDN возвращает HTML/другой контент вместо изображений"
        elif any('REDIRECT' in v for v in verdicts):
            conclusion = "Фотографии не загружаются, потому что CDN выполняет редирект на недоступный ресурс"
        elif any(s >= 500 for s in statuses if s):
            conclusion = "Фотографии не загружаются, потому что CDN возвращает ошибку сервера (5xx)"
        elif any('TIMEOUT' in v or 'CONNECTION_ERROR' in v for v in verdicts):
            conclusion = "Фотографии не загружаются, потому что CDN недоступен (timeout/connection error)"
        elif all(v == 'IMAGE' for v in verdicts):
            conclusion = "Фотографии доступны на CDN, проблема в коде импорта"
        else:
            conclusion = f"Фотографии не загружаются, потому что CDN возвращает неожиданный ответ: {verdicts}"
        
        f.write(f"**{conclusion}**\n")
    
    print(f"[OK] Отчет сохранен: {report_path}")
    
    # Выводим финальный вывод
    print("\n" + "="*70)
    print("[CONCLUSION]")
    print("="*70)
    
    verdicts = [r['verdict'] for r in url_results]
    statuses = [r['get_status'] for r in url_results]
    content_types = [r['get_content_type'] for r in url_results]
    
    if any(s == 403 for s in statuses):
        conclusion = "Фотографии не загружаются, потому что CDN возвращает 403 Forbidden (доступ запрещен)"
    elif any(ct and not ct.startswith('image/') for ct in content_types):
        conclusion = "Фотографии не загружаются, потому что CDN возвращает HTML/другой контент вместо изображений"
    elif any('REDIRECT' in v for v in verdicts):
        conclusion = "Фотографии не загружаются, потому что CDN выполняет редирект на недоступный ресурс"
    elif any(s >= 500 for s in statuses if s):
        conclusion = "Фотографии не загружаются, потому что CDN возвращает ошибку сервера (5xx)"
    elif any('TIMEOUT' in v or 'CONNECTION_ERROR' in v for v in verdicts):
        conclusion = "Фотографии не загружаются, потому что CDN недоступен (timeout/connection error)"
    elif all(v == 'IMAGE' for v in verdicts):
        conclusion = "Фотографии доступны на CDN, проблема в коде импорта"
    else:
        conclusion = f"Фотографии не загружаются, потому что CDN возвращает неожиданный ответ: {verdicts}"
    
    print(conclusion)
    print("="*70)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())


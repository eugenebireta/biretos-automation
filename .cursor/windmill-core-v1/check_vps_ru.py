#!/usr/bin/env python3
"""Проверка VPS RU конфигурации"""
import urllib.request
import json

print("=== VPS RU CONFIGURATION CHECK ===\n")

# Из local_worker
RU_BASE_URL = "https://n8n.biretos.ae"
print(f"[1] RU_BASE_URL (из local_worker): {RU_BASE_URL}")

# Проверяем доступность
print(f"\n[2] Проверка доступности {RU_BASE_URL}:")
try:
    req = urllib.request.Request(f"{RU_BASE_URL}/health", method="GET")
    req.add_header("User-Agent", "Windmill-Check/1.0")
    resp = urllib.request.urlopen(req, timeout=5)
    print(f"   [OK] Сервер доступен (status: {resp.getcode()})")
except urllib.error.HTTPError as e:
    print(f"   [INFO] HTTP {e.code}: {e.reason}")
    print(f"   [INFO] Сервер отвечает, но /health может не существовать")
except urllib.error.URLError as e:
    print(f"   [WARN] Не удалось подключиться: {e}")
except Exception as e:
    print(f"   [ERROR] {e}")

# Проверяем webhook endpoint
print(f"\n[3] Проверка webhook endpoint {RU_BASE_URL}/webhook/telegram:")
try:
    req = urllib.request.Request(f"{RU_BASE_URL}/webhook/telegram", method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Windmill-Check/1.0")
    test_payload = json.dumps({"test": "check"}).encode()
    resp = urllib.request.urlopen(req, data=test_payload, timeout=5)
    print(f"   [OK] Endpoint доступен (status: {resp.getcode()})")
except urllib.error.HTTPError as e:
    if e.code == 200 or e.code == 400 or e.code == 422:
        print(f"   [OK] Endpoint доступен (HTTP {e.code} - ожидаемо для тестового запроса)")
    else:
        print(f"   [WARN] HTTP {e.code}: {e.reason}")
except urllib.error.URLError as e:
    print(f"   [WARN] Не удалось подключиться: {e}")
except Exception as e:
    print(f"   [ERROR] {e}")

print(f"\n[4] ВЫВОД:")
print(f"   - RU_BASE_URL указывает на: {RU_BASE_URL}")
print(f"   - Это может быть VPS RU, где должен работать webhook_service")
print(f"   - Текущий Telegram webhook: https://biretos.ae/webhook/telegram (VPS USA)")
print(f"   - Нужно проверить, работает ли webhook_service на {RU_BASE_URL}")

print(f"\n[5] РЕКОМЕНДАЦИЯ:")
print(f"   - Проверить логи webhook_service на сервере {RU_BASE_URL}")
print(f"   - Или настроить Telegram webhook на {RU_BASE_URL}/webhook/telegram")
















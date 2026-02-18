#!/usr/bin/env python3
"""Проверка доступности webhook_service на RU VPS"""
import urllib.request
import json
import sys

RU_VPS_IP = "77.233.222.214"
WEBHOOK_PORT = 8001

print("=== ПРОВЕРКА WEBHOOK_SERVICE НА RU VPS ===\n")

# 1. Проверка health endpoint
print(f"[1] Проверка health endpoint:")
health_url = f"http://{RU_VPS_IP}:{WEBHOOK_PORT}/health"
try:
    req = urllib.request.Request(health_url)
    resp = urllib.request.urlopen(req, timeout=5)
    data = json.loads(resp.read().decode())
    print(f"   [OK] webhook_service работает!")
    print(f"   Response: {data}")
except urllib.error.HTTPError as e:
    print(f"   [ERROR] HTTP {e.code}: {e.reason}")
    if e.code == 404:
        print(f"   [INFO] Endpoint /health не найден, но сервис может работать")
    elif e.code == 502:
        print(f"   [INFO] Bad Gateway - возможно, nginx не настроен")
except urllib.error.URLError as e:
    print(f"   [ERROR] Не удалось подключиться: {e}")
    print(f"   [INFO] Возможно:")
    print(f"   - webhook_service не запущен на RU VPS")
    print(f"   - Порт {WEBHOOK_PORT} закрыт в firewall")
    print(f"   - Неправильный IP адрес")
except Exception as e:
    print(f"   [ERROR] Ошибка: {e}")

# 2. Проверка webhook endpoint (без установки)
print(f"\n[2] Проверка webhook endpoint:")
webhook_url = f"http://{RU_VPS_IP}:{WEBHOOK_PORT}/webhook/telegram"
try:
    # Отправляем тестовый запрос
    test_payload = {
        "update_id": 999999,
        "message": {
            "message_id": 1,
            "from": {"id": 123456, "is_bot": False, "first_name": "Test"},
            "chat": {"id": 123456, "type": "private"},
            "date": 1234567890,
            "text": "/start"
        }
    }
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(test_payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    resp = urllib.request.urlopen(req, timeout=5)
    data = json.loads(resp.read().decode())
    print(f"   [OK] webhook endpoint отвечает!")
    print(f"   Response: {data}")
except urllib.error.HTTPError as e:
    if e.code == 200:
        print(f"   [OK] webhook endpoint работает (200 OK)")
    else:
        print(f"   [WARNING] HTTP {e.code}: {e.reason}")
        try:
            error_body = e.read().decode()
            print(f"   Response: {error_body[:200]}")
        except:
            pass
except urllib.error.URLError as e:
    print(f"   [ERROR] Не удалось подключиться: {e}")
except Exception as e:
    print(f"   [ERROR] Ошибка: {e}")

print(f"\n=== ВЫВОД ===")
print(f"Если webhook_service не отвечает:")
print(f"1. Подключитесь к RU VPS по SSH")
print(f"2. Проверьте: ps aux | grep webhook_service")
print(f"3. Если не запущен: запустите webhook_service")
print(f"4. Проверьте firewall: sudo ufw status (или iptables)")
















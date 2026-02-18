#!/usr/bin/env python3
"""РџСЂСЏРјР°СЏ РїСЂРѕРІРµСЂРєР° Рё СѓСЃС‚Р°РЅРѕРІРєР° webhook"""
import urllib.request
import json
import sys

TOKEN = "<REDACTED_TELEGRAM_TOKEN>"
RU_VPS_IP = "77.233.222.214"

print("=== РџР РЇРњРђРЇ РЈРЎРўРђРќРћР’РљРђ WEBHOOK ===\n")

# 1. РџСЂРѕРІРµСЂРєР° С‚РµРєСѓС‰РµРіРѕ webhook
print("[1] РўРµРєСѓС‰РёР№ webhook:")
try:
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read().decode())
    if data.get("ok"):
        result = data["result"]
        print(f"   URL: {result.get('url', 'РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ')}")
        print(f"   Pending: {result.get('pending_update_count', 0)}")
        if result.get('last_error_message'):
            print(f"   Last error: {result.get('last_error_message')}")
except Exception as e:
    print(f"   РћС€РёР±РєР°: {e}")

# 2. РџРѕРїС‹С‚РєР° СѓСЃС‚Р°РЅРѕРІРёС‚СЊ РЅР° HTTP (РјРѕР¶РµС‚ РЅРµ СЂР°Р±РѕС‚Р°С‚СЊ)
print(f"\n[2] РЈСЃС‚Р°РЅРѕРІРєР° webhook РЅР° HTTP (РјРѕР¶РµС‚ РЅРµ СЂР°Р±РѕС‚Р°С‚СЊ Р±РµР· SSL):")
webhook_url = f"http://{RU_VPS_IP}:8001/webhook/telegram"
print(f"   URL: {webhook_url}")

try:
    params = urllib.parse.urlencode({"url": webhook_url})
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/setWebhook?{params}",
        method="GET"
    )
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read().decode())
    
    if data.get("ok"):
        print(f"   [OK] Webhook СѓСЃС‚Р°РЅРѕРІР»РµРЅ!")
        print(f"   Description: {data.get('description', '')}")
    else:
        error = data.get('description', 'Unknown')
        print(f"   [FAIL] {error}")
        if "SSL" in error or "certificate" in error or "HTTPS" in error:
            print(f"\n   [INFO] Telegram С‚СЂРµР±СѓРµС‚ HTTPS!")
            print(f"   Р РµС€РµРЅРёРµ: РЅР°СЃС‚СЂРѕР№С‚Рµ SSL РЅР° nginx РёР»Рё РёСЃРїРѕР»СЊР·СѓР№С‚Рµ РґРѕРјРµРЅ СЃ SSL")
except urllib.error.HTTPError as e:
    if e.code == 429:
        print(f"   [ERROR] Rate limit! РџРѕРґРѕР¶РґРёС‚Рµ РјРёРЅСѓС‚Сѓ")
    else:
        print(f"   [ERROR] HTTP {e.code}: {e.reason}")
except Exception as e:
    print(f"   [ERROR] {e}")

print(f"\n=== Р’Р«Р’РћР” ===")
print(f"Р•СЃР»Рё webhook РЅРµ СѓСЃС‚Р°РЅРѕРІРёР»СЃСЏ РёР·-Р·Р° SSL:")
print(f"1. РќР°СЃС‚СЂРѕР№С‚Рµ nginx СЃ SSL РЅР° RU VPS")
print(f"2. РР»Рё РёСЃРїРѕР»СЊР·СѓР№С‚Рµ РґРѕРјРµРЅ СЃ SSL")
print(f"3. РЎРј. DEPLOY_WEBHOOK_RU_VPS.md")

















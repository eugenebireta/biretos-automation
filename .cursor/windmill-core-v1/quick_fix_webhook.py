#!/usr/bin/env python3
"""Р‘С‹СЃС‚СЂРѕРµ РёСЃРїСЂР°РІР»РµРЅРёРµ: СѓСЃС‚Р°РЅРѕРІРєР° webhook СЃ РѕР±С…РѕРґРѕРј rate limit"""
import time
import urllib.request
import urllib.parse
import json
import sys

TOKEN = "<REDACTED_TELEGRAM_TOKEN>"
RU_VPS_IP = "77.233.222.214"

print("=== Р‘Р«РЎРўР РћР• РРЎРџР РђР’Р›Р•РќРР• WEBHOOK ===\n")
print("Р’РђР–РќРћ: Telegram API С‚СЂРµР±СѓРµС‚ HTTPS РґР»СЏ webhook!")
print("Р•СЃР»Рё РёСЃРїРѕР»СЊР·СѓРµС‚Рµ IP Р±РµР· SSL, webhook РќР• Р±СѓРґРµС‚ СЂР°Р±РѕС‚Р°С‚СЊ.\n")

# Р’Р°СЂРёР°РЅС‚С‹ URL
WEBHOOK_URLS = [
    f"https://{RU_VPS_IP}/webhook/telegram",  # Р§РµСЂРµР· nginx СЃ SSL
    f"http://{RU_VPS_IP}:8001/webhook/telegram",  # РџСЂСЏРјРѕР№ РґРѕСЃС‚СѓРї (РЅРµ СЃСЂР°Р±РѕС‚Р°РµС‚, РЅРѕ РїСЂРѕРІРµСЂРёРј)
]

print("[1] РћР¶РёРґР°РЅРёРµ 60 СЃРµРєСѓРЅРґ РґР»СЏ РѕР±С…РѕРґР° rate limit...")
print("    (Telegram API РѕРіСЂР°РЅРёС‡РёРІР°РµС‚ С‡Р°СЃС‚С‹Рµ Р·Р°РїСЂРѕСЃС‹)")
for i in range(60, 0, -10):
    print(f"    РћСЃС‚Р°Р»РѕСЃСЊ: {i} СЃРµРєСѓРЅРґ...")
    time.sleep(10)

print("\n[2] РџРѕРїС‹С‚РєР° СѓСЃС‚Р°РЅРѕРІРёС‚СЊ webhook...")

for webhook_url in WEBHOOK_URLS:
    print(f"\n   РџСЂРѕР±СѓРµРј: {webhook_url}")
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
            
            # РџСЂРѕРІРµСЂРєР°
            print(f"\n[3] РџСЂРѕРІРµСЂРєР° webhook:")
            req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")
            resp = urllib.request.urlopen(req, timeout=10)
            info = json.loads(resp.read().decode())
            
            if info.get("ok"):
                result = info["result"]
                print(f"   URL: {result.get('url')}")
                print(f"   Pending: {result.get('pending_update_count', 0)}")
                if result.get('last_error_message'):
                    print(f"   [WARNING] Last error: {result.get('last_error_message')}")
                else:
                    print(f"   [OK] Webhook СЂР°Р±РѕС‚Р°РµС‚!")
            
            sys.exit(0)
        else:
            error = data.get('description', 'Unknown error')
            print(f"   [FAIL] {error}")
            if "SSL" in error or "certificate" in error.lower():
                print(f"   [INFO] РќСѓР¶РµРЅ SSL СЃРµСЂС‚РёС„РёРєР°С‚ РґР»СЏ HTTPS")
            continue
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f"   [ERROR] Rate limit! РџРѕРґРѕР¶РґРёС‚Рµ РµС‰Рµ РјРёРЅСѓС‚Сѓ")
        else:
            print(f"   [ERROR] HTTP {e.code}: {e.reason}")
        continue
    except Exception as e:
        print(f"   [ERROR] {e}")
        continue

print(f"\n[ERROR] РќРµ СѓРґР°Р»РѕСЃСЊ СѓСЃС‚Р°РЅРѕРІРёС‚СЊ webhook")
print(f"\nР Р•РЁР•РќРР•:")
print(f"1. РќР°СЃС‚СЂРѕР№С‚Рµ SSL РЅР° RU VPS (nginx СЃ Let's Encrypt РёР»Рё СЃР°РјРѕРїРѕРґРїРёСЃР°РЅРЅС‹Р№)")
print(f"2. РР»Рё РёСЃРїРѕР»СЊР·СѓР№С‚Рµ РґРѕРјРµРЅ СЃ SSL, СѓРєР°Р·С‹РІР°СЋС‰РёР№ РЅР° RU VPS")
print(f"3. РЎРј. РёРЅСЃС‚СЂСѓРєС†РёСЋ: DEPLOY_WEBHOOK_RU_VPS.md")

















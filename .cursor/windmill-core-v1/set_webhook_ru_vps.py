#!/usr/bin/env python3
"""РЈСЃС‚Р°РЅРѕРІРєР° Telegram webhook РЅР° RU VPS"""
import urllib.request
import urllib.parse
import json
import sys

TOKEN = "<REDACTED_TELEGRAM_TOKEN>"
RU_VPS_IP = "77.233.222.214"

# Р’Р°СЂРёР°РЅС‚С‹ URL (РїСЂРѕРІРµСЂРёРј РѕР±Р°)
WEBHOOK_URLS = [
    f"http://{RU_VPS_IP}:8001/webhook/telegram",  # РџСЂСЏРјРѕР№ РґРѕСЃС‚СѓРї Рє webhook_service
    f"https://{RU_VPS_IP}/webhook/telegram",      # Р§РµСЂРµР· nginx (РµСЃР»Рё РЅР°СЃС‚СЂРѕРµРЅ HTTPS)
    f"http://{RU_VPS_IP}/webhook/telegram",      # Р§РµСЂРµР· nginx (HTTP)
]

print("=== РЈРЎРўРђРќРћР’РљРђ WEBHOOK РќРђ RU VPS ===\n")

# 1. РџСЂРѕРІРµСЂРєР° С‚РµРєСѓС‰РµРіРѕ webhook
print("[1] РџСЂРѕРІРµСЂРєР° С‚РµРєСѓС‰РµРіРѕ webhook:")
try:
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read().decode())
    
    if data.get("ok"):
        result = data["result"]
        current_url = result.get("url", "")
        print(f"   РўРµРєСѓС‰РёР№ URL: {current_url}")
        
        if current_url and RU_VPS_IP in current_url:
            print(f"   [OK] Webhook СѓР¶Рµ РЅР°СЃС‚СЂРѕРµРЅ РЅР° RU VPS!")
            sys.exit(0)
        elif current_url:
            print(f"   [INFO] Webhook РЅР°СЃС‚СЂРѕРµРЅ РЅР° РґСЂСѓРіРѕР№ URL, Р±СѓРґРµС‚ РёР·РјРµРЅРµРЅ")
    else:
        print(f"   [ERROR] API РІРµСЂРЅСѓР» РѕС€РёР±РєСѓ: {data.get('description')}")
except Exception as e:
    print(f"   [ERROR] РћС€РёР±РєР° РїСЂРѕРІРµСЂРєРё: {e}")

# 2. РџРѕРїС‹С‚РєР° СѓСЃС‚Р°РЅРѕРІРёС‚СЊ webhook РЅР° РєР°Р¶РґС‹Р№ URL РїРѕ РѕС‡РµСЂРµРґРё
print(f"\n[2] РџРѕРїС‹С‚РєР° СѓСЃС‚Р°РЅРѕРІРёС‚СЊ webhook РЅР° RU VPS:")
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
            print(f"   [OK] Webhook СѓСЃС‚Р°РЅРѕРІР»РµРЅ СѓСЃРїРµС€РЅРѕ!")
            print(f"   Description: {data.get('description', '')}")
            
            # РџСЂРѕРІРµСЂСЏРµРј, С‡С‚Рѕ webhook СЂР°Р±РѕС‚Р°РµС‚
            print(f"\n[3] РџСЂРѕРІРµСЂРєР° СѓСЃС‚Р°РЅРѕРІР»РµРЅРЅРѕРіРѕ webhook:")
            req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read().decode())
            
            if data.get("ok"):
                result = data["result"]
                print(f"   URL: {result.get('url')}")
                print(f"   Pending updates: {result.get('pending_update_count', 0)}")
                if result.get('last_error_message'):
                    print(f"   [WARNING] Last error: {result.get('last_error_message')}")
                else:
                    print(f"   [OK] Webhook СЂР°Р±РѕС‚Р°РµС‚ Р±РµР· РѕС€РёР±РѕРє!")
            
            sys.exit(0)
        else:
            error_desc = data.get('description', 'Unknown error')
            print(f"   [FAIL] РќРµ СѓРґР°Р»РѕСЃСЊ СѓСЃС‚Р°РЅРѕРІРёС‚СЊ: {error_desc}")
            if "502" in error_desc or "Bad Gateway" in error_desc:
                print(f"   [INFO] Р’РѕР·РјРѕР¶РЅРѕ, webhook_service РЅРµ Р·Р°РїСѓС‰РµРЅ РЅР° RU VPS")
            elif "SSL" in error_desc or "certificate" in error_desc.lower():
                print(f"   [INFO] РџСЂРѕР±Р»РµРјР° СЃ SSL СЃРµСЂС‚РёС„РёРєР°С‚РѕРј, РїСЂРѕР±СѓРµРј HTTP")
            continue
    except Exception as e:
        print(f"   [ERROR] РћС€РёР±РєР° РїСЂРё СѓСЃС‚Р°РЅРѕРІРєРµ: {e}")
        continue

print(f"\n[ERROR] РќРµ СѓРґР°Р»РѕСЃСЊ СѓСЃС‚Р°РЅРѕРІРёС‚СЊ webhook РЅРё РЅР° РѕРґРёРЅ РёР· URL")
print(f"\nРџСЂРѕРІРµСЂСЊС‚Рµ:")
print(f"1. Р—Р°РїСѓС‰РµРЅ Р»Рё webhook_service РЅР° RU VPS (РїРѕСЂС‚ 8001)")
print(f"2. РћС‚РєСЂС‹С‚ Р»Рё РїРѕСЂС‚ 8001 РІ firewall")
print(f"3. РќР°СЃС‚СЂРѕРµРЅ Р»Рё nginx РґР»СЏ РїСЂРѕРєСЃРёСЂРѕРІР°РЅРёСЏ (РµСЃР»Рё РёСЃРїРѕР»СЊР·СѓРµС‚Рµ nginx)")
sys.exit(1)

















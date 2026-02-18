#!/usr/bin/env python3
"""РџСЂРѕРІРµСЂРєР° РјР°СЂС€СЂСѓС‚РёР·Р°С†РёРё webhook"""
import urllib.request
import json

TOKEN = "<REDACTED_TELEGRAM_TOKEN>"

print("=== WEBHOOK ROUTING CHECK ===\n")

# РџСЂРѕРІРµСЂСЏРµРј С‚РµРєСѓС‰РёР№ webhook
print("[1] РўРµРєСѓС‰РёР№ Telegram webhook:")
try:
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read().decode())
    
    if data.get("ok"):
        result = data["result"]
        current_url = result.get("url", "")
        print(f"   URL: {current_url}")
        print(f"   Pending updates: {result.get('pending_update_count', 0)}")
        
        if "biretos.ae" in current_url:
            print("\n[WARNING] Webhook РЅР°СЃС‚СЂРѕРµРЅ РЅР° biretos.ae (VPS USA)")
            print("   РќРѕ webhook_service РґРѕР»Р¶РµРЅ СЂР°Р±РѕС‚Р°С‚СЊ РЅР° VPS RU!")
            print("   РќСѓР¶РЅРѕ СѓР·РЅР°С‚СЊ РїСЂР°РІРёР»СЊРЅС‹Р№ URL РґР»СЏ VPS RU")
        else:
            print(f"\n[INFO] Webhook РЅР°СЃС‚СЂРѕРµРЅ РЅР°: {current_url}")
    else:
        print(f"   [ERROR] {data.get('description')}")
except Exception as e:
    print(f"   [ERROR] {e}")

print("\n[2] РџСЂРѕР±Р»РµРјР°:")
print("   - Telegram webhook: https://biretos.ae/webhook/telegram (VPS USA)")
print("   - webhook_service РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ: VPS RU (РЅРµРёР·РІРµСЃС‚РЅС‹Р№ URL)")
print("   - Р—Р°РїСЂРѕСЃС‹ РёРґСѓС‚ РЅРµ С‚СѓРґР°, РєСѓРґР° РЅСѓР¶РЅРѕ!")

print("\n[3] Р РµС€РµРЅРёРµ:")
print("   - РќСѓР¶РЅРѕ СѓР·РЅР°С‚СЊ РґРѕРјРµРЅ/IP VPS RU")
print("   - РќР°СЃС‚СЂРѕРёС‚СЊ webhook РЅР° РїСЂР°РІРёР»СЊРЅС‹Р№ URL")
print("   - РР»Рё РїСЂРѕРІРµСЂРёС‚СЊ Р»РѕРіРё webhook_service РЅР° VPS RU")

















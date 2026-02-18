#!/usr/bin/env python3
"""РџСЂРѕРІРµСЂРєР° СЃС‚Р°С‚СѓСЃР° Telegram webhook"""
import urllib.request
import urllib.parse
import json
import sys

TOKEN = "<REDACTED_TELEGRAM_TOKEN>"

print("=== РџР РћР’Р•Р РљРђ TELEGRAM WEBHOOK ===\n")

# 1. РџСЂРѕРІРµСЂРєР° С‚РµРєСѓС‰РµРіРѕ webhook
print("[1] РџСЂРѕРІРµСЂРєР° С‚РµРєСѓС‰РµРіРѕ webhook:")
try:
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read().decode())
    
    if data.get("ok"):
        result = data["result"]
        current_url = result.get("url", "")
        pending_count = result.get("pending_update_count", 0)
        last_error_date = result.get("last_error_date")
        last_error_message = result.get("last_error_message")
        max_connections = result.get("max_connections")
        
        print(f"   URL: {current_url}")
        print(f"   Pending updates: {pending_count}")
        print(f"   Max connections: {max_connections}")
        
        if last_error_date:
            print(f"   Last error date: {last_error_date}")
            print(f"   Last error: {last_error_message}")
        
        if pending_count > 0:
            print(f"   [WARNING] Р•СЃС‚СЊ {pending_count} РЅРµРѕР±СЂР°Р±РѕС‚Р°РЅРЅС‹С… РѕР±РЅРѕРІР»РµРЅРёР№!")
        
        if not current_url:
            print(f"   [ERROR] Webhook РЅРµ РЅР°СЃС‚СЂРѕРµРЅ!")
        elif "biretos.ae" in current_url:
            print(f"   [WARNING] Webhook РЅР°СЃС‚СЂРѕРµРЅ РЅР° biretos.ae (USA VPS), Р° РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ РЅР° RU VPS!")
        elif "77.233.222.214" in current_url or "ru" in current_url.lower():
            print(f"   [OK] Webhook РЅР°СЃС‚СЂРѕРµРЅ РЅР° RU VPS")
        else:
            print(f"   [INFO] Webhook URL: {current_url}")
    else:
        print(f"   [ERROR] API РІРµСЂРЅСѓР» РѕС€РёР±РєСѓ: {data.get('description')}")
        sys.exit(1)
except Exception as e:
    print(f"   [ERROR] РћС€РёР±РєР° РїСЂРѕРІРµСЂРєРё webhook: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n=== Р’Р«Р’РћР” ===")
print("Р•СЃР»Рё webhook РЅРµ РЅР°СЃС‚СЂРѕРµРЅ РёР»Рё РЅР°СЃС‚СЂРѕРµРЅ РЅРµРїСЂР°РІРёР»СЊРЅРѕ в†’ РѕР±РЅРѕРІР»РµРЅРёСЏ РЅРµ РїСЂРёС…РѕРґСЏС‚")
print("Р•СЃР»Рё РµСЃС‚СЊ pending updates в†’ РЅСѓР¶РЅРѕ РёС… РѕР±СЂР°Р±РѕС‚Р°С‚СЊ")


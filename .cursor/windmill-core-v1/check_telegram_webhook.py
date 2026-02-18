#!/usr/bin/env python3
"""Check and set Telegram webhook"""
import urllib.request
import urllib.parse
import json
import sys

TOKEN = "<REDACTED_TELEGRAM_TOKEN>"
WEBHOOK_URL = "https://biretos.ae/webhook/telegram"  # РџСЂРµРґРїРѕР»Р°РіР°РµРјС‹Р№ РїСѓР±Р»РёС‡РЅС‹Р№ URL

# 1. РџСЂРѕРІРµСЂРёС‚СЊ С‚РµРєСѓС‰РёР№ webhook
print("[1] Checking current webhook...")
try:
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read().decode())
    
    if data.get("ok"):
        result = data["result"]
        current_url = result.get("url", "")
        print(f"    Current webhook URL: {current_url}")
        print(f"    Pending updates: {result.get('pending_update_count', 0)}")
        
        if current_url and "/webhook/telegram" in current_url:
            print(f"    [OK] Webhook is set correctly")
            sys.exit(0)
        else:
            print(f"    [WARN] Webhook URL doesn't match expected pattern")
            if not current_url:
                print(f"    [INFO] Webhook is not set, will set it now...")
    else:
        print(f"    [ERROR] API returned error: {data.get('description')}")
        sys.exit(1)
except Exception as e:
    print(f"    [ERROR] Failed to check webhook: {e}")
    sys.exit(1)

# 2. РЈСЃС‚Р°РЅРѕРІРёС‚СЊ webhook
print(f"\n[2] Setting webhook to: {WEBHOOK_URL}")
try:
    params = urllib.parse.urlencode({"url": WEBHOOK_URL})
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/setWebhook?{params}",
        method="GET"
    )
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read().decode())
    
    if data.get("ok"):
        print(f"    [OK] Webhook set successfully")
        print(f"    Description: {data.get('description', '')}")
    else:
        print(f"    [ERROR] Failed to set webhook: {data.get('description')}")
        sys.exit(1)
except Exception as e:
    print(f"    [ERROR] Failed to set webhook: {e}")
    sys.exit(1)
























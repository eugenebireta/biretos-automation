#!/usr/bin/env python3
"""РџСЂРѕРІРµСЂРєР° РЅР°СЃС‚СЂРѕР№РєРё Telegram Р±РѕС‚Р°"""
from pathlib import Path

from config import get_config

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)
except ImportError:
    pass

_CONFIG = get_config()
TELEGRAM_BOT_TOKEN = _CONFIG.telegram_bot_token

print("=== VERIFY: Telegram Bot Setup ===\n")

if TELEGRAM_BOT_TOKEN:
    print(f"[OK] TELEGRAM_BOT_TOKEN СѓСЃС‚Р°РЅРѕРІР»РµРЅ: {TELEGRAM_BOT_TOKEN[:20]}...")
else:
    print("[WARNING] TELEGRAM_BOT_TOKEN РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ")
    print("РЈСЃС‚Р°РЅРѕРІРёС‚Рµ С‚РѕРєРµРЅ РІ .env С„Р°Р№Р»Рµ:")
    print("TELEGRAM_BOT_TOKEN=<REDACTED_TELEGRAM_TOKEN>")

print("\n=== CHANGES MADE ===")
print("1. РЈРїСЂРѕС‰РµРЅ _handle_start_command - РѕС‚РїСЂР°РІР»СЏРµС‚ С‚РѕР»СЊРєРѕ 'OK'")
print("2. РЈР»СѓС‡С€РµРЅР° РѕР±СЂР°Р±РѕС‚РєР° РѕС€РёР±РѕРє РІ _send_telegram_message")
print("3. chat_id СѓР¶Рµ РёР·РІР»РµРєР°РµС‚СЃСЏ РІ ru_worker РїСЂРё РѕР±СЂР°Р±РѕС‚РєРµ telegram_update")
print("4. telegram_command СЃРѕР·РґР°РµС‚СЃСЏ СЃ РїСЂР°РІРёР»СЊРЅС‹Рј chat_id")

print("\n=== READY FOR TEST ===")
print("1. РЈР±РµРґРёС‚РµСЃСЊ, С‡С‚Рѕ TELEGRAM_BOT_TOKEN СѓСЃС‚Р°РЅРѕРІР»РµРЅ")
print("2. Р—Р°РїСѓСЃС‚РёС‚Рµ ru_worker")
print("3. РћС‚РїСЂР°РІСЊС‚Рµ /start Р±РѕС‚Сѓ РІ Telegram")
print("4. Р‘РѕС‚ РґРѕР»Р¶РµРЅ РѕС‚РІРµС‚РёС‚СЊ 'OK'")

















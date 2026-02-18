#!/usr/bin/env python3
"""РўРµСЃС‚ РѕС‚РїСЂР°РІРєРё СЃРѕРѕР±С‰РµРЅРёСЏ РІ Telegram"""
import sys
import httpx
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
if not TELEGRAM_BOT_TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN not set")
    print("Token from TOKEN_INSTALLED_RESULT.txt: <REDACTED_TELEGRAM_TOKEN>")
    sys.exit(1)

# Hardcode РґР»СЏ С‚РµСЃС‚Р° (Р·Р°РјРµРЅРёС‚Рµ РЅР° СЂРµР°Р»СЊРЅС‹Р№ chat_id)
TEST_CHAT_ID = 123456789  # Р—Р°РјРµРЅРёС‚Рµ РЅР° СЂРµР°Р»СЊРЅС‹Р№ chat_id

url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
payload = {
    "chat_id": TEST_CHAT_ID,
    "text": "OK"
}

try:
    response = httpx.post(url, json=payload, timeout=10.0)
    response.raise_for_status()
    result = response.json()
    print(f"SUCCESS: {result}")
except Exception as e:
    print(f"ERROR: {e}")

















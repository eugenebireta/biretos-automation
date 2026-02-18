#!/usr/bin/env python3
"""Проверка сырых данных Telegram Update в БД"""
import sys
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path

from config import get_config

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)
except ImportError:
    pass

_CONFIG = get_config()
POSTGRES_HOST = _CONFIG.postgres_host or "localhost"
POSTGRES_PORT = _CONFIG.postgres_port or 5432
POSTGRES_DB = _CONFIG.postgres_db or "biretos_automation"
POSTGRES_USER = _CONFIG.postgres_user or "biretos_user"
POSTGRES_PASSWORD = _CONFIG.postgres_password

print("=== ПРОВЕРКА TELEGRAM UPDATE В БД ===\n")

conn = None
try:
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Последний telegram_update
    print("[1] Последний telegram_update (полный payload):")
    cursor.execute("""
        SELECT id, status, payload, created_at
        FROM job_queue
        WHERE job_type = 'telegram_update'
        ORDER BY created_at DESC
        LIMIT 1
    """)
    update = cursor.fetchone()
    
    if update:
        print(f"ID: {update['id']}")
        print(f"Status: {update['status']}")
        print(f"Created: {update['created_at']}")
        print(f"\nPayload (полный):")
        payload = json.loads(update['payload']) if isinstance(update['payload'], str) else update['payload']
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        
        # Проверяем структуру
        telegram_payload = payload.get("payload", {})
        print(f"\n[2] Структура telegram_payload:")
        print(f"   Keys: {list(telegram_payload.keys()) if isinstance(telegram_payload, dict) else 'not_dict'}")
        
        if "message" in telegram_payload:
            message = telegram_payload["message"]
            print(f"   message type: {type(message)}")
            if isinstance(message, dict):
                print(f"   message keys: {list(message.keys())}")
                if "chat" in message:
                    chat = message["chat"]
                    print(f"   chat type: {type(chat)}")
                    if isinstance(chat, dict):
                        print(f"   chat keys: {list(chat.keys())}")
                        print(f"   chat.id: {chat.get('id')}")
                        print(f"   chat.id type: {type(chat.get('id'))}")
                    else:
                        print(f"   chat is not dict: {chat}")
                else:
                    print(f"   [ERROR] 'chat' not in message")
                if "text" in message:
                    print(f"   text: {message.get('text')}")
                else:
                    print(f"   [ERROR] 'text' not in message")
            else:
                print(f"   [ERROR] message is not dict: {message}")
        else:
            print(f"   [ERROR] 'message' not in telegram_payload")
    else:
        print("   [WARNING] Нет telegram_update jobs в БД!")
        print("   Это значит, что webhook_service НЕ получает обновления от Telegram!")
    
    # Проверяем последние 3 telegram_update
    print(f"\n[3] Последние 3 telegram_update (только статусы и время):")
    cursor.execute("""
        SELECT id, status, created_at, updated_at
        FROM job_queue
        WHERE job_type = 'telegram_update'
        ORDER BY created_at DESC
        LIMIT 3
    """)
    updates = cursor.fetchall()
    if updates:
        for u in updates:
            print(f"   {u['id']}: {u['status']} (created: {u['created_at']}, updated: {u['updated_at']})")
    else:
        print("   Нет telegram_update jobs")
    
    conn.close()
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n=== ВЫВОД ===")
print("Если нет telegram_update jobs → webhook_service не получает обновления")
print("Если есть telegram_update, но нет telegram_command → проблема в ru_worker")
















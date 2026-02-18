#!/usr/bin/env python3
"""Проверка последнего telegram_update из job_queue"""
import psycopg2
import json
from pathlib import Path

from config import get_config

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)
except ImportError:
    pass

_CONFIG = get_config()
POSTGRES_HOST = _CONFIG.postgres_host or "localhost"
POSTGRES_PORT = _CONFIG.postgres_port or 5432
POSTGRES_DB = _CONFIG.postgres_db or "biretos_automation"
POSTGRES_USER = _CONFIG.postgres_user or "biretos_user"
POSTGRES_PASSWORD = _CONFIG.postgres_password

conn = psycopg2.connect(
    host=POSTGRES_HOST,
    port=POSTGRES_PORT,
    dbname=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD
)
cur = conn.cursor()

# Получаем последний telegram_update
cur.execute("""
    SELECT id, payload, created_at
    FROM job_queue 
    WHERE job_type = 'telegram_update'
    ORDER BY created_at DESC 
    LIMIT 1;
""")

result = cur.fetchone()
if result:
    job_id, payload, created_at = result
    print(f"Job ID: {job_id}")
    print(f"Created: {created_at}\n")
    
    if payload:
        if isinstance(payload, str):
            payload_dict = json.loads(payload)
        else:
            payload_dict = payload
        
        print("=== PAYLOAD STRUCTURE ===")
        print(f"Keys: {list(payload_dict.keys())}\n")
        
        # Проверяем наличие message.chat.id
        telegram_payload = payload_dict.get("payload", {})
        print("=== TELEGRAM PAYLOAD ===")
        print(f"Keys: {list(telegram_payload.keys()) if isinstance(telegram_payload, dict) else 'not_dict'}\n")
        
        if "message" in telegram_payload:
            message = telegram_payload["message"]
            print("=== MESSAGE ===")
            print(f"Keys: {list(message.keys()) if isinstance(message, dict) else 'not_dict'}\n")
            
            if "chat" in message:
                chat = message["chat"]
                print("=== CHAT ===")
                print(f"Keys: {list(chat.keys()) if isinstance(chat, dict) else 'not_dict'}")
                print(f"Chat ID: {chat.get('id')}\n")
            else:
                print("=== CHAT ===")
                print("MISSING: 'chat' key not found in message\n")
        else:
            print("=== MESSAGE ===")
            print("MISSING: 'message' key not found in telegram_payload\n")
        
        print("=== FULL PAYLOAD ===")
        print(json.dumps(payload_dict, indent=2, ensure_ascii=False))
else:
    print("Нет telegram_update задач")

conn.close()
















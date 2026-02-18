#!/usr/bin/env python3
"""Проверка payload telegram_update"""
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

# Получаем completed telegram_update (которая создала telegram_command)
cur.execute("""
    SELECT id, payload
    FROM job_queue 
    WHERE job_type = 'telegram_update' AND status = 'completed'
    ORDER BY created_at DESC 
    LIMIT 1;
""")

result = cur.fetchone()
if result:
    job_id, payload = result
    print(f"Telegram Update Job ID: {job_id}\n")
    
    if payload:
        if isinstance(payload, str):
            payload_dict = json.loads(payload)
        else:
            payload_dict = payload
        
        print("Payload structure:")
        print(f"  Keys: {list(payload_dict.keys())}\n")
        
        # Проверяем структуру
        if "payload" in payload_dict:
            telegram_payload = payload_dict["payload"]
            print("Telegram payload (payload.payload):")
            print(f"  Type: {type(telegram_payload)}")
            if isinstance(telegram_payload, dict):
                print(f"  Keys: {list(telegram_payload.keys())}")
                
                if "message" in telegram_payload:
                    message = telegram_payload["message"]
                    print(f"\n  Message keys: {list(message.keys())}")
                    if "chat" in message:
                        chat = message["chat"]
                        print(f"  Chat keys: {list(chat.keys())}")
                        print(f"  Chat ID: {chat.get('id')}")
                    if "from" in message:
                        from_user = message["from"]
                        print(f"  From keys: {list(from_user.keys())}")
                        print(f"  User ID: {from_user.get('id')}")
                    if "text" in message:
                        print(f"  Text: {message.get('text')}")
        else:
            print("WARNING: 'payload' key not found in payload_dict")
            print(f"Full payload: {json.dumps(payload_dict, indent=2, ensure_ascii=False)[:500]}")
else:
    print("Нет completed telegram_update задач")

conn.close()
















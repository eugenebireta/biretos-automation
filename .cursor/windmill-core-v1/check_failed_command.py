#!/usr/bin/env python3
"""Проверка failed telegram_command"""
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

# Получаем failed telegram_command
cur.execute("""
    SELECT id, payload, error
    FROM job_queue 
    WHERE job_type = 'telegram_command' AND status = 'failed'
    ORDER BY created_at DESC 
    LIMIT 1;
""")

result = cur.fetchone()
if result:
    job_id, payload, error = result
    print(f"Job ID: {job_id}")
    print(f"Error: {error}\n")
    
    if payload:
        if isinstance(payload, str):
            payload_dict = json.loads(payload)
        else:
            payload_dict = payload
        
        print("Payload:")
        print(json.dumps(payload_dict, indent=2, ensure_ascii=False))
        
        print(f"\nChat ID: {payload_dict.get('chat_id')}")
        print(f"Command: {payload_dict.get('command')}")
else:
    print("Нет failed telegram_command задач")

conn.close()
















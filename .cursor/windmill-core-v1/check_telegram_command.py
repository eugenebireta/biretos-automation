#!/usr/bin/env python3
"""Проверка обработки telegram_command"""
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

print("=== CHECK: telegram_command jobs ===\n")

# Последние telegram_command задачи
cur.execute("""
    SELECT id, status, created_at, updated_at, payload, result, error
    FROM job_queue 
    WHERE job_type = 'telegram_command'
    ORDER BY created_at DESC 
    LIMIT 5;
""")

jobs = cur.fetchall()

if not jobs:
    print("Нет telegram_command задач")
else:
    print(f"Найдено {len(jobs)} telegram_command задач:\n")
    for job in jobs:
        job_id, status, created_at, updated_at, payload, result, error = job
        print(f"ID: {job_id}")
        print(f"  Status: {status}")
        print(f"  Created: {created_at}")
        print(f"  Updated: {updated_at}")
        
        if payload:
            if isinstance(payload, str):
                payload_dict = json.loads(payload)
            else:
                payload_dict = payload
            print(f"  Command: {payload_dict.get('command')}")
            print(f"  Chat ID: {payload_dict.get('chat_id')}")
        
        if error:
            print(f"  ERROR: {error[:200]}")
        
        if result:
            if isinstance(result, str):
                result_dict = json.loads(result)
            else:
                result_dict = result
            print(f"  Result: {json.dumps(result_dict, indent=2, ensure_ascii=False)[:200]}")
        
        print()

# Статистика по статусам
cur.execute("""
    SELECT status, COUNT(*) 
    FROM job_queue 
    WHERE job_type = 'telegram_command'
    GROUP BY status;
""")
print("Статистика по статусам:")
for status, count in cur.fetchall():
    print(f"  {status}: {count}")

conn.close()
















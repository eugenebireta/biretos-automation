#!/usr/bin/env python3
"""Проверка статуса последней записи в job_queue"""
import psycopg2
from pathlib import Path

from config import get_config

# Загрузка переменных окружения
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)
except ImportError:
    pass

# Параметры подключения
_CONFIG = get_config()
POSTGRES_HOST = _CONFIG.postgres_host or "localhost"
POSTGRES_PORT = _CONFIG.postgres_port or 5432
POSTGRES_DB = _CONFIG.postgres_db or "biretos_automation"
POSTGRES_USER = _CONFIG.postgres_user or "biretos_user"
POSTGRES_PASSWORD = _CONFIG.postgres_password

try:
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )
    cur = conn.cursor()
    
    # Проверка статуса последней записи
    cur.execute("""
        SELECT status FROM job_queue ORDER BY created_at DESC LIMIT 1;
    """)
    result = cur.fetchone()
    
    if result:
        print(f"Статус последней записи: {result[0]}")
    else:
        print("Записей в job_queue не найдено")
    
    # Дополнительная информация о последней записи
    cur.execute("""
        SELECT id, job_type, status, created_at, updated_at
        FROM job_queue 
        ORDER BY created_at DESC 
        LIMIT 1;
    """)
    row = cur.fetchone()
    if row:
        print(f"\nДетали последней записи:")
        print(f"  ID: {row[0]}")
        print(f"  Job Type: {row[1]}")
        print(f"  Status: {row[2]}")
        print(f"  Created: {row[3]}")
        print(f"  Updated: {row[4]}")
    
    conn.close()
    
except psycopg2.OperationalError as e:
    print(f"[ERROR] Ошибка подключения к БД: {e}")
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
















#!/usr/bin/env python3
"""Проверка количества telegram_update записей в job_queue"""
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
    
    # Проверка количества telegram_update
    cur.execute("""
        SELECT count(*) 
        FROM job_queue 
        WHERE job_type = 'telegram_update';
    """)
    count = cur.fetchone()[0]
    
    print(f"Количество записей telegram_update: {count}")
    
    # Дополнительная информация
    if count > 0:
        cur.execute("""
            SELECT status, COUNT(*) 
            FROM job_queue 
            WHERE job_type = 'telegram_update'
            GROUP BY status;
        """)
        print("\nРаспределение по статусам:")
        for status, cnt in cur.fetchall():
            print(f"  {status}: {cnt}")
        
        cur.execute("""
            SELECT id, status, created_at, payload->>'source' as source
            FROM job_queue 
            WHERE job_type = 'telegram_update'
            ORDER BY created_at DESC 
            LIMIT 5;
        """)
        print("\nПоследние 5 записей:")
        for row in cur.fetchall():
            print(f"  {row[0]} | {row[1]} | {row[2]} | source={row[3]}")
    else:
        print("\n[WARNING] Записей не найдено. Проверьте:")
        print("  1. Запущен ли webhook_service?")
        print("  2. Настроен ли Telegram webhook на правильный URL?")
        print("  3. Есть ли ошибки в логах webhook_service?")
    
    conn.close()
    
except psycopg2.OperationalError as e:
    print(f"[ERROR] Ошибка подключения к БД: {e}")
    print(f"   Host: {POSTGRES_HOST}:{POSTGRES_PORT}")
    print(f"   DB: {POSTGRES_DB}, User: {POSTGRES_USER}")
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")


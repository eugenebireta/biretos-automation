#!/usr/bin/env python3
import psycopg2
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

# Критерий готовности
cur.execute("SELECT status FROM job_queue ORDER BY created_at DESC LIMIT 1;")
result = cur.fetchone()
if result:
    print(f"КРИТЕРИЙ: Статус последней записи: {result[0]}")
    if result[0] != 'pending':
        print("[OK] Критерий выполнен: статус НЕ pending")
    else:
        print("[FAIL] Критерий не выполнен: статус все еще pending")

# Все записи
cur.execute("""
    SELECT id, job_type, status, created_at 
    FROM job_queue 
    ORDER BY created_at DESC 
    LIMIT 5;
""")
print("\nПоследние 5 записей:")
for row in cur.fetchall():
    print(f"  {row[0]} | {row[1]} | {row[2]} | {row[3]}")

conn.close()
















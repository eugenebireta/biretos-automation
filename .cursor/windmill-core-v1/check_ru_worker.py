#!/usr/bin/env python3
"""Проверка ru_worker: процесс, подключение, polling"""
import sys
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

_CONFIG = get_config()
POSTGRES_HOST = _CONFIG.postgres_host or "localhost"
POSTGRES_PORT = _CONFIG.postgres_port or 5432
POSTGRES_DB = _CONFIG.postgres_db or "biretos_automation"
POSTGRES_USER = _CONFIG.postgres_user or "biretos_user"
POSTGRES_PASSWORD = _CONFIG.postgres_password

print("=== DIAGNOSTIC: ru_worker ===\n")

# 1. Проверка процесса
print("[1] Проверка процесса ru_worker...")
if sys.platform == "win32":
    import subprocess
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        python_processes = result.stdout.count("python.exe")
        print(f"   Найдено процессов python.exe: {python_processes}")
        if python_processes > 0:
            print("   [INFO] Процесс может быть запущен (нужна ручная проверка)")
        else:
            print("   [WARNING] Процесс python.exe не найден")
    except Exception as e:
        print(f"   [ERROR] Не удалось проверить процессы: {e}")
else:
    import subprocess
    try:
        result = subprocess.run(
            ["pgrep", "-f", "ru_worker.py"],
            capture_output=True
        )
        if result.returncode == 0:
            print(f"   [OK] Процесс ru_worker.py найден (PID: {result.stdout.decode().strip()})")
        else:
            print("   [WARNING] Процесс ru_worker.py не найден")
    except Exception as e:
        print(f"   [ERROR] Не удалось проверить процессы: {e}")

# 2. Проверка подключения к PostgreSQL
print("\n[2] Проверка подключения к PostgreSQL...")
try:
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()[0]
    print(f"   [OK] Подключение успешно")
    print(f"   PostgreSQL: {version[:50]}...")
    conn.close()
except psycopg2.OperationalError as e:
    print(f"   [ERROR] Не удалось подключиться: {e}")
    sys.exit(1)
except Exception as e:
    print(f"   [ERROR] Ошибка: {e}")
    sys.exit(1)

# 3. Проверка pending задач
print("\n[3] Проверка pending задач в job_queue...")
try:
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )
    cur = conn.cursor()
    
    # Проверка всех pending
    cur.execute("""
        SELECT COUNT(*) FROM job_queue WHERE status = 'pending';
    """)
    pending_count = cur.fetchone()[0]
    print(f"   Всего pending задач: {pending_count}")
    
    # Проверка telegram_update pending
    cur.execute("""
        SELECT COUNT(*) FROM job_queue 
        WHERE status = 'pending' AND job_type = 'telegram_update';
    """)
    telegram_pending = cur.fetchone()[0]
    print(f"   telegram_update pending: {telegram_pending}")
    
    # Проверка, какие job_type есть в pending
    cur.execute("""
        SELECT job_type, COUNT(*) 
        FROM job_queue 
        WHERE status = 'pending'
        GROUP BY job_type;
    """)
    print("   Распределение по job_type:")
    for job_type, cnt in cur.fetchall():
        print(f"     {job_type}: {cnt}")
    
    # Проверка последней записи
    cur.execute("""
        SELECT id, job_type, status, created_at, updated_at
        FROM job_queue 
        ORDER BY created_at DESC 
        LIMIT 1;
    """)
    last = cur.fetchone()
    if last:
        print(f"\n   Последняя запись:")
        print(f"     ID: {last[0]}")
        print(f"     Job Type: {last[1]}")
        print(f"     Status: {last[2]}")
        print(f"     Created: {last[3]}")
        print(f"     Updated: {last[4]}")
    
    # Проверка, обрабатывается ли задача (processing)
    cur.execute("""
        SELECT COUNT(*) FROM job_queue WHERE status = 'processing';
    """)
    processing_count = cur.fetchone()[0]
    print(f"\n   Задач в статусе processing: {processing_count}")
    
    conn.close()
except Exception as e:
    print(f"   [ERROR] Ошибка: {e}")

# 4. Проверка SQL запроса ru_worker
print("\n[4] Проверка SQL запроса ru_worker...")
try:
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )
    cur = conn.cursor()
    
    # Имитация запроса из ru_worker
    cur.execute("""
        SELECT * FROM job_queue 
        WHERE status = 'pending' 
          AND job_type IN ('test_job', 'rfq_v1_from_ocr', 'tbank_invoice_paid', 'telegram_update', 'telegram_command', 'cdek_shipment', 'cdek_shipment_status', 'insales_paid_sync', 'invoice_create', 'order_event')
        ORDER BY created_at ASC 
        LIMIT 1 
        FOR UPDATE SKIP LOCKED
    """)
    
    job = cur.fetchone()
    if job:
        print(f"   [OK] Запрос находит задачу: {job[1]} (ID: {job[0]})")
    else:
        print("   [WARNING] Запрос не находит задач (возможно, все обработаны или заблокированы)")
    
    conn.rollback()  # Откатываем FOR UPDATE
    conn.close()
except Exception as e:
    print(f"   [ERROR] Ошибка SQL запроса: {e}")

print("\n=== КРИТЕРИЙ ГОТОВНОСТИ ===")
try:
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )
    cur = conn.cursor()
    cur.execute("SELECT status FROM job_queue ORDER BY created_at DESC LIMIT 1;")
    result = cur.fetchone()
    if result:
        status = result[0]
        print(f"Статус последней записи: {status}")
        if status != 'pending':
            print("[OK] Критерий выполнен: статус НЕ pending")
        else:
            print("[FAIL] Критерий не выполнен: статус все еще pending")
    else:
        print("[WARNING] Записей в job_queue нет")
    conn.close()
except Exception as e:
    print(f"[ERROR] {e}")
















#!/usr/bin/env python3
"""Диагностика Telegram MVP: почему бот не отвечает"""
import sys
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
from datetime import datetime, timedelta

from config import get_config

# Загрузка переменных окружения
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

print("=== ДИАГНОСТИКА TELEGRAM MVP ===\n")

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
    
    # 1. Проверка последних telegram_update
    print("[1] Последние telegram_update (последние 5):")
    cursor.execute("""
        SELECT id, status, created_at, updated_at, error
        FROM job_queue
        WHERE job_type = 'telegram_update'
        ORDER BY created_at DESC
        LIMIT 5
    """)
    updates = cursor.fetchall()
    if updates:
        for u in updates:
            print(f"   ID: {u['id']}")
            print(f"   Status: {u['status']}")
            print(f"   Created: {u['created_at']}")
            print(f"   Updated: {u['updated_at']}")
            if u['error']:
                print(f"   ERROR: {u['error'][:200]}")
            print()
    else:
        print("   [WARNING] Нет telegram_update jobs")
    
    # 2. Проверка последних telegram_command
    print("[2] Последние telegram_command (последние 5):")
    cursor.execute("""
        SELECT id, status, created_at, updated_at, error, payload
        FROM job_queue
        WHERE job_type = 'telegram_command'
        ORDER BY created_at DESC
        LIMIT 5
    """)
    commands = cursor.fetchall()
    if commands:
        for c in commands:
            print(f"   ID: {c['id']}")
            print(f"   Status: {c['status']}")
            print(f"   Created: {c['created_at']}")
            print(f"   Updated: {c['updated_at']}")
            if c['error']:
                print(f"   ERROR: {c['error'][:200]}")
            if c['payload']:
                payload = json.loads(c['payload']) if isinstance(c['payload'], str) else c['payload']
                print(f"   Command: {payload.get('command')}")
                print(f"   Chat ID: {payload.get('chat_id')}")
            print()
    else:
        print("   [WARNING] Нет telegram_command jobs")
    
    # 3. Проверка pending задач
    print("[3] Pending задачи:")
    cursor.execute("""
        SELECT job_type, COUNT(*) as cnt
        FROM job_queue
        WHERE status = 'pending'
        GROUP BY job_type
    """)
    pending = cursor.fetchall()
    if pending:
        for p in pending:
            print(f"   {p['job_type']}: {p['cnt']}")
    else:
        print("   [OK] Нет pending задач")
    
    # 4. Проверка failed задач (последние 3)
    print("\n[4] Failed задачи (последние 3):")
    cursor.execute("""
        SELECT id, job_type, error, created_at
        FROM job_queue
        WHERE status = 'failed'
        ORDER BY created_at DESC
        LIMIT 3
    """)
    failed = cursor.fetchall()
    if failed:
        for f in failed:
            print(f"   {f['job_type']} (ID: {f['id']})")
            print(f"   Error: {f['error'][:300] if f['error'] else 'N/A'}")
            print(f"   Created: {f['created_at']}")
            print()
    else:
        print("   [OK] Нет failed задач")
    
    # 5. Проверка цепочки: telegram_update → telegram_command
    print("[5] Проверка цепочки обработки:")
    cursor.execute("""
        SELECT 
            tu.id as update_id,
            tu.status as update_status,
            tu.created_at as update_created,
            tc.id as command_id,
            tc.status as command_status,
            tc.created_at as command_created
        FROM job_queue tu
        LEFT JOIN job_queue tc ON (
            tc.job_type = 'telegram_command' 
            AND tc.payload::jsonb->>'command' = '/start'
            AND tc.created_at > tu.created_at
            AND tc.created_at < tu.created_at + INTERVAL '1 minute'
        )
        WHERE tu.job_type = 'telegram_update'
        ORDER BY tu.created_at DESC
        LIMIT 3
    """)
    chain = cursor.fetchall()
    if chain:
        for c in chain:
            print(f"   Update {c['update_id']} ({c['update_status']})")
            if c['command_id']:
                print(f"   → Command {c['command_id']} ({c['command_status']})")
            else:
                print(f"   → [WARNING] Command не создан!")
            print()
    else:
        print("   [WARNING] Нет данных для проверки цепочки")
    
    # 6. Проверка последнего /start
    print("[6] Последний /start command:")
    cursor.execute("""
        SELECT id, status, payload, error, created_at, updated_at
        FROM job_queue
        WHERE job_type = 'telegram_command'
          AND payload::jsonb->>'command' = '/start'
        ORDER BY created_at DESC
        LIMIT 1
    """)
    start_cmd = cursor.fetchone()
    if start_cmd:
        payload = json.loads(start_cmd['payload']) if isinstance(start_cmd['payload'], str) else start_cmd['payload']
        print(f"   ID: {start_cmd['id']}")
        print(f"   Status: {start_cmd['status']}")
        print(f"   Chat ID: {payload.get('chat_id')}")
        print(f"   Created: {start_cmd['created_at']}")
        print(f"   Updated: {start_cmd['updated_at']}")
        if start_cmd['error']:
            print(f"   ERROR: {start_cmd['error'][:300]}")
        if start_cmd['status'] == 'completed':
            # Проверяем result
            cursor.execute("""
                SELECT result FROM job_queue WHERE id = %s
            """, (start_cmd['id'],))
            result_row = cursor.fetchone()
            if result_row and result_row['result']:
                result = json.loads(result_row['result']) if isinstance(result_row['result'], str) else result_row['result']
                print(f"   Result: {json.dumps(result, indent=2)}")
    else:
        print("   [WARNING] Нет /start команд")
    
    conn.close()
    
except Exception as e:
    print(f"[ERROR] Ошибка диагностики: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n=== РЕКОМЕНДАЦИИ ===")
print("Если бот не отвечает, проверьте:")
print("1. Запущен ли webhook_service на RU VPS (порт 8001)")
print("2. Запущен ли ru_worker на RU VPS")
print("3. Настроен ли Telegram webhook на правильный URL")
print("4. Есть ли ошибки в failed задачах выше")


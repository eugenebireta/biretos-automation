"""
E2E DRY-RUN Test Script

Скрипт для симуляции входящих событий и проверки DRY-RUN режима.

Использование:
1. Установите DRY_RUN_EXTERNAL_APIS=true в .env
2. Убедитесь, что БД запущена и таблицы созданы
3. Запустите ru_worker в одном терминале: python ru_worker/ru_worker.py
4. Запустите этот скрипт в другом терминале: python test_dry_run_e2e.py

Скрипт:
- Создает тестовые события в job_queue
- Наблюдает за изменениями в job_queue и order_ledger
- Формирует отчет о выполнении
"""

import json
import time
from datetime import datetime
from uuid import uuid4

import psycopg2
from psycopg2.extras import RealDictCursor

from config import get_config

def get_db_connection():
    """Получает подключение к БД"""
    config = get_config()
    postgres_host = config.postgres_host or "localhost"
    postgres_port = config.postgres_port or 5432
    postgres_db = config.postgres_db or "biretos_automation"
    postgres_user = config.postgres_user or "biretos_user"
    postgres_password = config.postgres_password
    return psycopg2.connect(
        host=postgres_host,
        port=postgres_port,
        database=postgres_db,
        user=postgres_user,
        password=postgres_password
    )

def create_test_order_in_ledger(cursor, order_id=None):
    """Создает тестовый заказ в order_ledger для тестирования"""
    if order_id is None:
        order_id = uuid4()
    
    # Проверяем, существует ли уже заказ
    cursor.execute(
        """
        SELECT order_id FROM order_ledger WHERE order_id = %s
        """,
        (order_id,)
    )
    if cursor.fetchone():
        print(f"[INFO] Order {order_id} already exists in ledger")
        return order_id
    
    # Создаем тестовый заказ
    invoice_request_key = f"test-invoice-{str(order_id)[:8]}"
    cursor.execute(
        """
        INSERT INTO order_ledger (
            order_id,
            insales_order_id,
            invoice_request_key,
            state,
            state_history,
            customer_data,
            delivery_data,
            metadata,
            created_at,
            updated_at
        ) VALUES (
            %s,
            %s,
            %s,
            %s,
            %s::jsonb,
            %s::jsonb,
            %s::jsonb,
            %s::jsonb,
            NOW(),
            NOW()
        )
        RETURNING order_id
        """,
        (
            order_id,
            f"insales-{str(order_id)[:8]}",
            invoice_request_key,
            "paid",
            json.dumps([{"state": "paid", "timestamp": datetime.utcnow().isoformat() + "Z"}]),
            json.dumps({
                "name": "Тестовый Клиент",
                "phone": "+79001234567",
                "email": "test@example.com",
                "companyName": "Тестовая Компания",
                "inn": "1234567890"
            }),
            json.dumps({
                "city": "Москва",
                "address": "Тестовый адрес, 1"
            }),
            json.dumps({
                "invoiceNumber": f"INV-{str(order_id)[:8]}",
                "packageWeight": 1000
            })
        )
    )
    result = cursor.fetchone()
    print(f"[INFO] Created test order in ledger: {result[0]}")
    return result[0]

def insert_telegram_update_job(cursor, command_type, order_id=None):
    """Вставляет telegram_update job в job_queue"""
    job_id = uuid4()
    
    if command_type == "/start":
        payload = {
            "payload": {
                "message": {
                    "message_id": 1,
                    "from": {"id": 123456789, "username": "test_user"},
                    "chat": {"id": 123456789, "type": "private"},
                    "text": "/start",
                    "date": int(time.time())
                }
            }
        }
        idempotency_key = f"telegram_update:/start:{123456789}"
    
    elif command_type == "check":
        if not order_id:
            raise ValueError("order_id required for check command")
        payload = {
            "payload": {
                "callback_query": {
                    "id": str(uuid4()),
                    "from": {"id": 123456789, "username": "test_user"},
                    "message": {
                        "message_id": 2,
                        "chat": {"id": 123456789, "type": "private"}
                    },
                    "data": f"check:{order_id}"
                }
            }
        }
        idempotency_key = f"telegram_update:check:{order_id}:{payload['payload']['callback_query']['id']}"
    
    elif command_type == "ship":
        if not order_id:
            raise ValueError("order_id required for ship command")
        payload = {
            "payload": {
                "callback_query": {
                    "id": str(uuid4()),
                    "from": {"id": 123456789, "username": "test_user"},
                    "message": {
                        "message_id": 3,
                        "chat": {"id": 123456789, "type": "private"}
                    },
                    "data": f"ship:{order_id}"
                }
            }
        }
        idempotency_key = f"telegram_update:ship:{order_id}:{payload['payload']['callback_query']['id']}"
    
    else:
        raise ValueError(f"Unknown command_type: {command_type}")
    
    cursor.execute(
        """
        INSERT INTO job_queue (id, job_type, payload, status, idempotency_key, created_at)
        VALUES (%s, %s, %s::jsonb, 'pending', %s, NOW())
        RETURNING id
        """,
        (job_id, "telegram_update", json.dumps(payload), idempotency_key)
    )
    result = cursor.fetchone()
    print(f"[INFO] Inserted telegram_update job: {result[0]} (command: {command_type})")
    return result[0]

def observe_job_queue(cursor, timeout=30):
    """Наблюдает за job_queue в течение timeout секунд"""
    start_time = time.time()
    observed_jobs = []
    
    print(f"[OBSERVE] Watching job_queue for {timeout} seconds...")
    
    while time.time() - start_time < timeout:
        cursor.execute(
            """
            SELECT id, job_type, status, error, created_at, updated_at
            FROM job_queue
            WHERE created_at > NOW() - INTERVAL '1 minute'
            ORDER BY created_at DESC
            LIMIT 50
            """
        )
        jobs = cursor.fetchall()
        
        for job in jobs:
            job_id = str(job["id"])
            if job_id not in [j["id"] for j in observed_jobs]:
                observed_jobs.append({
                    "id": job_id,
                    "job_type": job["job_type"],
                    "status": job["status"],
                    "error": job.get("error"),
                    "created_at": job["created_at"].isoformat() if job["created_at"] else None,
                    "updated_at": job["updated_at"].isoformat() if job["updated_at"] else None
                })
                status_icon = "✅" if job["status"] == "completed" else "❌" if job["status"] == "failed" else "⏳"
                print(f"[OBSERVE] {status_icon} Job {job_id[:8]}... | {job['job_type']} | {job['status']}")
                if job.get("error"):
                    print(f"        ERROR: {job['error']}")
        
        time.sleep(2)
    
    return observed_jobs

def observe_order_ledger(cursor, order_id):
    """Наблюдает за изменениями в order_ledger для конкретного заказа"""
    cursor.execute(
        """
        SELECT order_id, state, metadata, updated_at
        FROM order_ledger
        WHERE order_id = %s
        """,
        (order_id,)
    )
    record = cursor.fetchone()
    
    if record:
        metadata = record["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        print(f"[LEDGER] Order {order_id}")
        print(f"        State: {record['state']}")
        print(f"        Updated: {record['updated_at']}")
        if metadata:
            print(f"        Metadata keys: {list(metadata.keys())[:10]}")
            if "cdek_uuid" in metadata:
                print(f"        CDEK UUID: {metadata.get('cdek_uuid')}")
            if "tbank_invoice_id" in metadata:
                print(f"        T-Bank Invoice ID: {metadata.get('tbank_invoice_id')}")
    
    return record

def main():
    """Основная функция теста"""
    config = get_config()
    print("=" * 60)
    print("E2E DRY-RUN Test Script")
    print("=" * 60)
    print()
    
    # Проверка DRY_RUN режима
    dry_run = bool(config.dry_run_external_apis)
    if not dry_run:
        print("[WARNING] DRY_RUN_EXTERNAL_APIS is not set to 'true'")
        print("[WARNING] External API calls will fail without tokens")
        print()
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # 1. Создаем тестовый заказ
        print("[STEP 1] Creating test order in ledger...")
        test_order_id = create_test_order_in_ledger(cursor)
        conn.commit()
        print()
        
        # 2. Тест /start команды
        print("[STEP 2] Testing /start command...")
        start_job_id = insert_telegram_update_job(cursor, "/start")
        conn.commit()
        print(f"[INFO] Waiting for /start job to be processed...")
        time.sleep(5)
        print()
        
        # 3. Тест check:<order_id> команды
        print("[STEP 3] Testing check:<order_id> command...")
        check_job_id = insert_telegram_update_job(cursor, "check", test_order_id)
        conn.commit()
        print(f"[INFO] Waiting for check job to be processed...")
        time.sleep(5)
        print()
        
        # 4. Тест ship:<order_id> команды
        print("[STEP 4] Testing ship:<order_id> command...")
        ship_job_id = insert_telegram_update_job(cursor, "ship", test_order_id)
        conn.commit()
        print(f"[INFO] Waiting for ship job to be processed...")
        time.sleep(10)
        print()
        
        # 5. Наблюдение за job_queue
        print("[STEP 5] Observing job_queue...")
        observed_jobs = observe_job_queue(cursor, timeout=20)
        print()
        
        # 6. Наблюдение за order_ledger
        print("[STEP 6] Observing order_ledger changes...")
        ledger_record = observe_order_ledger(cursor, test_order_id)
        print()
        
        # 7. Формирование отчета
        print("=" * 60)
        print("TEST REPORT")
        print("=" * 60)
        print()
        print(f"Test Order ID: {test_order_id}")
        print(f"DRY_RUN Mode: {dry_run}")
        print()
        print(f"Total Jobs Observed: {len(observed_jobs)}")
        print()
        
        # Группировка по типам
        job_types = {}
        for job in observed_jobs:
            job_type = job["job_type"]
            if job_type not in job_types:
                job_types[job_type] = {"total": 0, "completed": 0, "failed": 0}
            job_types[job_type]["total"] += 1
            if job["status"] == "completed":
                job_types[job_type]["completed"] += 1
            elif job["status"] == "failed":
                job_types[job_type]["failed"] += 1
        
        print("Jobs by Type:")
        for job_type, stats in job_types.items():
            print(f"  {job_type}:")
            print(f"    Total: {stats['total']}")
            print(f"    Completed: {stats['completed']} ✅")
            print(f"    Failed: {stats['failed']} ❌")
        print()
        
        # Проверка сценариев
        print("Scenario Check:")
        scenarios = {
            "/start": any(j["job_type"] == "telegram_command" and j["status"] == "completed" for j in observed_jobs),
            "check": any(j["job_type"] == "telegram_command" and j["status"] == "completed" for j in observed_jobs),
            "ship": any(j["job_type"] == "cdek_shipment" and j["status"] == "completed" for j in observed_jobs),
            "fsm_event": any(j["job_type"] == "order_event" and j["status"] == "completed" for j in observed_jobs)
        }
        
        for scenario, passed in scenarios.items():
            icon = "✅" if passed else "❌"
            print(f"  {icon} {scenario}: {'PASSED' if passed else 'FAILED/MISSING'}")
        print()
        
        if ledger_record:
            print("Order Ledger State:")
            print(f"  State: {ledger_record['state']}")
            metadata = ledger_record["metadata"]
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            if metadata.get("cdek_uuid"):
                print(f"  CDEK UUID: {metadata['cdek_uuid']} {'(MOCK)' if dry_run else ''}")
        
    except Exception as e:
        print(f"[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()


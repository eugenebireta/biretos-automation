"""
Windmill Execution Core v1 - Job Processor
Windmill script для чтения и выполнения задач из PostgreSQL job_queue

ВАЖНО: Этот скрипт должен быть импортирован в Windmill как Python script
Windmill НЕ принимает HTTP запросы - только опрашивает PostgreSQL
"""

import json
import time
from typing import Dict, Any, Optional
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor

from config import get_config
from domain.availability_service import release_reservations_for_order_atomic

# Конфигурация PostgreSQL (должна совпадать с webhook_service)
_CONFIG = get_config()
POSTGRES_HOST = _CONFIG.postgres_host or "localhost"
POSTGRES_PORT = _CONFIG.postgres_port or 5432
POSTGRES_DB = _CONFIG.postgres_db or "biretos_automation"
POSTGRES_USER = _CONFIG.postgres_user or "biretos_user"
POSTGRES_PASSWORD = _CONFIG.postgres_password


def get_db_connection():
    """Создает подключение к PostgreSQL"""
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )


def process_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Выполняет задачу
    
    Минимальная реализация:
    - Если payload содержит 'echo' → выводит значение
    - Иначе → sleep 1-2 секунды (фиктивная задача)
    """
    payload = job.get("payload", {})
    job_type = job.get("job_type", "unknown")
    
    # Фиктивное выполнение
    if "echo" in payload:
        result = {"echoed": payload["echo"], "job_type": job_type}
        print(f"Echo: {payload['echo']}")
    else:
        # Просто задержка 1-2 секунды
        time.sleep(1)
        result = {"processed": True, "job_type": job_type, "message": "Job completed"}
    
    return result


def _extract_order_id(payload: Any) -> Optional[UUID]:
    payload_dict: Dict[str, Any]
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
            payload_dict = parsed if isinstance(parsed, dict) else {}
        except Exception:
            payload_dict = {}
    elif isinstance(payload, dict):
        payload_dict = payload
    else:
        payload_dict = {}

    raw_order_id = payload_dict.get("order_id")
    if not raw_order_id:
        return None
    try:
        return UUID(str(raw_order_id))
    except Exception:
        return None


def main():
    """
    Главная функция Windmill script
    
    Логика:
    1. SELECT * FROM job_queue WHERE status='pending' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED
    2. UPDATE status='processing'
    3. Выполнить задачу
    4. UPDATE status='completed'
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Блокируем и получаем следующую задачу
        cursor.execute(
            """
            SELECT * FROM job_queue 
            WHERE status = 'pending' 
            ORDER BY created_at ASC 
            LIMIT 1 
            FOR UPDATE SKIP LOCKED
            """
        )
        
        job = cursor.fetchone()
        
        if not job:
            return {
                "status": "no_jobs",
                "message": "No pending jobs found"
            }
        
        job_id = job["id"]
        
        # Помечаем как processing
        cursor.execute(
            """
            UPDATE job_queue 
            SET status = 'processing', updated_at = NOW() 
            WHERE id = %s
            """,
            (job_id,)
        )
        conn.commit()
        
        # Выполняем задачу
        cleanup_order_id = _extract_order_id(job.get("payload"))
        job_failed = False
        try:
            result = process_job(dict(job))
            
            # Обновляем статус на completed
            cursor.execute(
                """
                UPDATE job_queue 
                SET status = 'completed', updated_at = NOW() 
                WHERE id = %s
                """,
                (job_id,)
            )
            conn.commit()
            
            return {
                "status": "completed",
                "job_id": str(job_id),
                "job_type": job["job_type"],
                "result": result
            }
            
        except Exception as e:
            job_failed = True
            # В случае ошибки помечаем как failed
            cursor.execute(
                """
                UPDATE job_queue 
                SET status = 'failed', error = %s, updated_at = NOW() 
                WHERE id = %s
                """,
                (str(e), job_id)
            )
            conn.commit()
            raise
        finally:
            if job_failed and cleanup_order_id is not None:
                try:
                    release_reservations_for_order_atomic(
                        conn,
                        order_id=cleanup_order_id,
                        trace_id=None,
                        reason="windmill_job_processor_failure",
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
            
    except Exception as e:
        if conn:
            conn.rollback()
        return {
            "status": "error",
            "message": str(e)
        }
    finally:
        if conn:
            cursor.close()
            conn.close()


if __name__ == "__main__":
    # Для локального тестирования
    result = main()
    print(json.dumps(result, indent=2))























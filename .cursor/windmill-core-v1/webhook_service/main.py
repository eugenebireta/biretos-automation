"""
Webhook / Queue Service
Минимальный HTTP сервис для приема запросов и записи в PostgreSQL job_queue

ВАЖНО: Windmill НЕ используется. Pipeline: nginx → webhook_service → PostgreSQL → ru_worker → Telegram API
Все задачи выполняются ТОЛЬКО на RU VPS (77.233.222.214) через ru_worker.
"""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import uuid4

import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from config import get_config

_CONFIG = get_config()

# Debug logging path (platform-safe, configurable)
DEBUG_LOG_PATH = Path(
    os.getenv(
        "DEBUG_LOG_PATH",
        str(Path(__file__).resolve().parents[1] / "logs" / "debug.log"),
    )
)

def debug_log(hypothesis_id: str, location: str, message: str, data: dict):
    """Компактная функция для записи debug логов"""
    try:
        import time
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        log_entry = {
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000)
        }
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Игнорируем ошибки логирования

# Конфигурация PostgreSQL
POSTGRES_HOST = _CONFIG.postgres_host or "localhost"
POSTGRES_PORT = _CONFIG.postgres_port or 5432
POSTGRES_DB = _CONFIG.postgres_db or "biretos_automation"
POSTGRES_USER = _CONFIG.postgres_user or "biretos_user"
POSTGRES_PASSWORD = _CONFIG.postgres_password

app = FastAPI(title="Webhook Service", version="1.0.0")  # Windmill НЕ используется


class JobRequest(BaseModel):
    job_type: str = "test_job"  # default для обратной совместимости
    payload: Dict[str, Any]

# Разрешенные job_type для Phase 1 boundary freeze
CORE_PIPELINES_V1 = [
    "test_job",
    "heavy_compute_test",
    "ocr_test",
    "rfq_v1_from_ocr",
]
LEGACY_BETA_FEATURES = [
    "tbank_invoice_paid",
    "telegram_update",
    "cdek_shipment_status",
]
ALLOWED_JOB_TYPES = CORE_PIPELINES_V1 + LEGACY_BETA_FEATURES


class JobCallback(BaseModel):
    job_token: str
    result: Optional[Dict[str, Any]] = None
    success: bool
    error: Optional[str] = None


_DB_POOL: Optional[ThreadedConnectionPool] = None
_DB_POOL_MIN = max(1, int(os.getenv("WEBHOOK_DB_POOL_MIN", "1")))
_DB_POOL_MAX = max(_DB_POOL_MIN, int(os.getenv("WEBHOOK_DB_POOL_MAX", "10")))
_JOB_QUEUE_HAS_TRACE_ID: Optional[bool] = None


def get_db_pool() -> ThreadedConnectionPool:
    """Lazy-init shared PostgreSQL connection pool."""
    global _DB_POOL
    if _DB_POOL is None:
        _DB_POOL = ThreadedConnectionPool(
            minconn=_DB_POOL_MIN,
            maxconn=_DB_POOL_MAX,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
        )
    return _DB_POOL


def get_db_connection():
    """Берет подключение из общего пула."""
    return get_db_pool().getconn()


def return_db_connection(conn) -> None:
    """Возвращает подключение в пул без утечек."""
    if conn is None:
        return
    pool = _DB_POOL or get_db_pool()
    try:
        conn.rollback()
        pool.putconn(conn)
    except Exception:
        try:
            pool.putconn(conn, close=True)
        except Exception:
            pass


def _job_queue_has_trace_id(conn) -> bool:
    global _JOB_QUEUE_HAS_TRACE_ID
    if _JOB_QUEUE_HAS_TRACE_ID is not None:
        return _JOB_QUEUE_HAS_TRACE_ID
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'job_queue'
                  AND column_name = 'trace_id'
            )
            """
        )
        _JOB_QUEUE_HAS_TRACE_ID = bool(cursor.fetchone()[0])
        return _JOB_QUEUE_HAS_TRACE_ID
    finally:
        cursor.close()


def _insert_job_with_idempotency(
    conn,
    job_type: str,
    payload: Dict[str, Any],
    idempotency_key: str,
    trace_id: str,
) -> Dict[str, Any]:
    """Вставляет job c idempotency и trace_id (fallback для старой схемы)."""
    cursor = conn.cursor()
    has_trace = _job_queue_has_trace_id(conn)
    payload_json = json.dumps(payload, ensure_ascii=False)
    try:
        try:
            if has_trace:
                cursor.execute(
                    """
                    INSERT INTO job_queue (id, job_type, payload, status, idempotency_key, trace_id)
                    VALUES (gen_random_uuid(), %s, %s, 'pending', %s, %s::uuid)
                    RETURNING id, status, trace_id
                    """,
                    (job_type, payload_json, idempotency_key, trace_id),
                )
                job_id, job_status, stored_trace_id = cursor.fetchone()
            else:
                cursor.execute(
                    """
                    INSERT INTO job_queue (id, job_type, payload, status, idempotency_key)
                    VALUES (gen_random_uuid(), %s, %s, 'pending', %s)
                    RETURNING id, status
                    """,
                    (job_type, payload_json, idempotency_key),
                )
                job_id, job_status = cursor.fetchone()
                stored_trace_id = None
            conn.commit()
            return {
                "created": True,
                "job_id": str(job_id),
                "status": job_status,
                "trace_id": str(stored_trace_id) if stored_trace_id else (trace_id if has_trace else None),
            }
        except psycopg2.IntegrityError:
            conn.rollback()
            if has_trace:
                cursor.execute(
                    """
                    SELECT id, status, trace_id
                    FROM job_queue
                    WHERE idempotency_key = %s
                    """,
                    (idempotency_key,),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, status, NULL::uuid AS trace_id
                    FROM job_queue
                    WHERE idempotency_key = %s
                    """,
                    (idempotency_key,),
                )
            existing = cursor.fetchone()
            if not existing:
                raise HTTPException(status_code=500, detail="Idempotency conflict but job not found")
            existing_job_id, existing_status, existing_trace_id = existing
            return {
                "created": False,
                "job_id": str(existing_job_id),
                "status": existing_status,
                "trace_id": str(existing_trace_id) if existing_trace_id else None,
            }
    finally:
        cursor.close()


def _extract_bearer_token(auth_header: Optional[str]) -> Optional[str]:
    if not auth_header:
        return None
    parts = auth_header.strip().split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None


def _is_valid_telegram_secret(request: Request) -> bool:
    expected_secret = (_CONFIG.telegram_webhook_secret or "").strip()
    if not expected_secret:
        return False
    received_secret = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
    return bool(received_secret) and received_secret == expected_secret


def _is_valid_tbank_token(request: Request) -> bool:
    expected_token = (_CONFIG.tbank_api_token or "").strip()
    if not expected_token:
        return False
    header_token = (request.headers.get("X-Api-Token") or "").strip()
    bearer_token = _extract_bearer_token(request.headers.get("Authorization"))
    return any(
        bool(candidate) and candidate == expected_token
        for candidate in (header_token, bearer_token)
    )


@app.on_event("startup")
async def startup_event() -> None:
    get_db_pool()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    global _DB_POOL
    if _DB_POOL is not None:
        _DB_POOL.closeall()
        _DB_POOL = None


def generate_idempotency_key(job_type: str, payload: Dict[str, Any]) -> str:
    """Генерирует idempotency key на основе job_type и payload"""
    payload_str = json.dumps(payload, sort_keys=True)
    combined = f"{job_type}:{payload_str}"
    return hashlib.sha256(combined.encode()).hexdigest()


@app.post("/webhook/test-job")
async def create_test_job(request: JobRequest):
    """
    Создает тестовую задачу в очереди
    
    - Принимает JSON payload
    - job_type (optional, default="test_job"): разрешены ["test_job", "heavy_compute_test"]
    - Генерирует idempotency_key
    - INSERT в job_queue со статусом 'pending'
    - Если idempotency_key уже есть → вернуть 200 OK (без дубля)
    """
    # Валидация job_type
    if request.job_type not in ALLOWED_JOB_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid job_type. Allowed: {ALLOWED_JOB_TYPES}"
        )
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        # Генерируем idempotency key
        idempotency_key = generate_idempotency_key(request.job_type, request.payload)
        trace_id = str(uuid4())
        insert_result = _insert_job_with_idempotency(
            conn=conn,
            job_type=request.job_type,
            payload=request.payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )
        response_status = 201 if insert_result["created"] else 200
        response_body = {
            "job_id": insert_result["job_id"],
            "status": "created" if insert_result["created"] else "already_exists",
            "existing_status": None if insert_result["created"] else insert_result["status"],
            "idempotency_key": idempotency_key,
            "trace_id": insert_result["trace_id"],
        }
        return JSONResponse(status_code=response_status, content=response_body)
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)


@app.get("/api/jobs/poll")
async def poll_job(worker_id: Optional[str] = Query(None)):
    """
    Polling endpoint для Local PC worker
    
    - SELECT одну задачу со статусом 'pending'
    - UPDATE на 'dispatched' с job_token
    - Возвращает job_id, job_type, payload, job_token
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # SELECT с блокировкой
        cursor.execute(
            """
            SELECT id, job_type, payload 
            FROM job_queue 
            WHERE status = 'pending' 
            ORDER BY created_at ASC 
            LIMIT 1 
            FOR UPDATE SKIP LOCKED
            """
        )
        
        job = cursor.fetchone()
        
        if not job:
            return Response(status_code=204)  # No Content
        
        job_id, job_type, payload = job
        job_token = uuid4()
        
        # UPDATE на dispatched
        cursor.execute(
            """
            UPDATE job_queue 
            SET status = 'dispatched', 
                job_token = %s, 
                dispatched_at = NOW(), 
                updated_at = NOW() 
            WHERE id = %s
            """,
            (job_token, job_id)
        )
        conn.commit()
        
        # Возвращаем задачу
        return JSONResponse(
            status_code=200,
            content={
                "job_id": str(job_id),
                "job_type": job_type,
                "payload": json.loads(payload) if isinstance(payload, str) else payload,
                "job_token": str(job_token)
            }
        )
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)


@app.post("/api/jobs/{job_id}/callback")
async def job_callback(job_id: str, callback: JobCallback):
    """
    Callback endpoint для Local PC worker
    
    - Проверяет job_token
    - UPDATE job на 'completed' или 'failed'
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем job_token и получаем текущий статус
        cursor.execute(
            """
            SELECT job_token, status 
            FROM job_queue 
            WHERE id = %s
            """,
            (job_id,)
        )
        
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Job not found")
        
        stored_token, current_status = result
        
        # Проверяем job_token
        if str(stored_token) != callback.job_token:
            raise HTTPException(status_code=403, detail="Invalid job_token")
        
        # Проверяем, что job в статусе dispatched
        if current_status != 'dispatched':
            raise HTTPException(status_code=400, detail=f"Job is not in 'dispatched' status (current: {current_status})")
        
        # UPDATE job (сохраняем result JSONB)
        result_json = json.dumps(callback.result) if callback.result else None
        
        if callback.success:
            cursor.execute(
                """
                UPDATE job_queue 
                SET status = 'completed', 
                    updated_at = NOW(), 
                    error = NULL,
                    result = %s
                WHERE id = %s
                """,
                (result_json, job_id)
            )
        else:
            cursor.execute(
                """
                UPDATE job_queue 
                SET status = 'failed', 
                    updated_at = NOW(), 
                    error = %s,
                    result = %s
                WHERE id = %s
                """,
                (callback.error, result_json, job_id)
            )
        
        conn.commit()
        
        return JSONResponse(
            status_code=200,
            content={
                "job_id": job_id,
                "status": "completed" if callback.success else "failed"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)


@app.post("/webhook/tbank-invoice-paid")
async def tbank_invoice_paid_webhook(request: Request):
    """
    T-Bank Webhook Handler для события INVOICE_PAID
    
    - Принимает POST с JSON payload от T-Bank
    - Валидирует eventType == "INVOICE_PAID" и invoiceId
    - Нормализует payload в internal_event
    - Ставит job в job_queue с idempotency_key = "tbank:invoice_paid:{invoice_id}"
    - Всегда возвращает 200 OK (даже при дублях)
    """
    if not _is_valid_tbank_token(request):
        return JSONResponse(
            status_code=403,
            content={"ok": False, "message": "Forbidden"},
        )

    try:
        body = await request.json()
    except Exception as e:
        # Логируем ошибку, но возвращаем 200 OK (по спецификации)
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": "validation",
            "message": "Invalid JSON payload",
            "context": {"error": str(e)}
        }
        print(json.dumps(log_entry))
        return JSONResponse(
            status_code=200,
            content={"ok": True, "message": "Payment recorded"}
        )
    
    # Валидация payload structure
    if not isinstance(body, dict):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": "validation",
            "message": "Empty webhook payload",
            "context": {"body_type": str(type(body))}
        }
        print(json.dumps(log_entry))
        return JSONResponse(
            status_code=200,
            content={"ok": True, "message": "Payment recorded"}
        )
    
    # Нормализация и валидация полей
    event_type = body.get("eventType") or body.get("event_type")
    invoice_id = body.get("invoiceId") or body.get("invoice_id")
    
    # Валидация eventType
    if event_type != "INVOICE_PAID":
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": "validation",
            "message": f"Unsupported eventType: {event_type}",
            "context": {"event_type": event_type}
        }
        print(json.dumps(log_entry))
        return JSONResponse(
            status_code=200,
            content={"ok": True, "message": "Payment recorded"}
        )
    
    # Валидация invoiceId
    if not invoice_id or not isinstance(invoice_id, str) or not invoice_id.strip():
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": "validation",
            "message": "invoiceId is required",
            "context": {"invoice_id": invoice_id}
        }
        print(json.dumps(log_entry))
        return JSONResponse(
            status_code=200,
            content={"ok": True, "message": "Payment recorded"}
        )
    
    # Нормализация в internal_event
    invoice_number = body.get("invoiceNumber") or body.get("invoice_number") or None
    paid_at = body.get("paidAt") or body.get("paid_at") or datetime.utcnow().isoformat() + "Z"
    
    internal_event = {
        "invoice_id": invoice_id.strip(),
        "invoice_number": invoice_number,
        "paid_at": paid_at
    }
    
    # Idempotency key
    idempotency_key = f"tbank:invoice_paid:{invoice_id.strip()}"
    
    conn = None
    cursor = None
    trace_id = str(uuid4())
    try:
        conn = get_db_connection()
        insert_result = _insert_job_with_idempotency(
            conn=conn,
            job_type="tbank_invoice_paid",
            payload=internal_event,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "tbank_webhook_job_created" if insert_result["created"] else "tbank_webhook_idempotent",
            "job_id": insert_result["job_id"],
            "invoice_id": invoice_id,
            "idempotency_key": idempotency_key,
            "existing_job_status": None if insert_result["created"] else insert_result["status"],
            "trace_id": insert_result["trace_id"],
        }
        print(json.dumps(log_entry))

        return JSONResponse(
            status_code=200,
            content={"ok": True, "message": "Payment recorded", "trace_id": insert_result["trace_id"]},
        )
    except Exception as e:
        if conn:
            conn.rollback()
        
        # Логируем ошибку БД, но возвращаем 200 OK
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": "database",
            "message": f"Database error: {str(e)}",
            "context": {"invoice_id": invoice_id}
        }
        print(json.dumps(log_entry))
        
        return JSONResponse(
            status_code=200,
            content={"ok": True, "message": "Payment recorded"}
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    Telegram Adapter - принимает Telegram Update
    
    - Принимает POST с Telegram Update JSON
    - Валидирует update_id
    - Нормализует в canonical event
    - Ставит job в job_queue с job_type = "telegram_update"
    - Всегда возвращает 200 OK
    """
    if not _is_valid_telegram_secret(request):
        return JSONResponse(
            status_code=403,
            content={"ok": False, "message": "Forbidden"},
        )

    # ЛОГИРОВАНИЕ: получаем raw body ПЕРВЫМ делом (до парсинга)
    raw_body = await request.body()
    
    # #region agent log
    try:
        raw_body_str = raw_body.decode('utf-8', errors='replace')
        debug_log = {
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": "A",
            "location": "webhook_service/main.py:488",
            "message": "telegram_webhook_raw_body",
            "data": {
                "raw_body_received": "YES",
                "raw_body_length": len(raw_body_str),
                "raw_body_preview": raw_body_str[:200]
            },
            "timestamp": int(datetime.utcnow().timestamp() * 1000)
        }
        try:
            DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(debug_log, ensure_ascii=False) + "\n")
        except Exception as log_err:
            print(f"DEBUG LOG ERROR: {log_err}, path: {DEBUG_LOG_PATH}")
    except Exception as e:
        debug_log = {
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": "D",
            "location": "webhook_service/main.py:488",
            "message": "telegram_webhook_raw_body_error",
            "data": {"error": str(e)},
            "timestamp": int(datetime.utcnow().timestamp() * 1000)
        }
        try:
            DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(debug_log, ensure_ascii=False) + "\n")
        except Exception as log_err:
            print(f"DEBUG LOG ERROR: {log_err}, path: {DEBUG_LOG_PATH}")
    # #endregion
    
    # ЛОГИРОВАНИЕ: логируем ВЕСЬ raw body без преобразований
    try:
        raw_body_str = raw_body.decode('utf-8', errors='replace')
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "telegram_webhook_raw_body",
            "raw_body": raw_body_str  # Весь raw body как строка
        }
        print(json.dumps(log_entry))
    except Exception as e:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "telegram_webhook_raw_body_error",
            "error": str(e)
        }
        print(json.dumps(log_entry))
    
    # Парсим JSON из raw_body
    try:
        body = json.loads(raw_body)
    except Exception as e:
        # #region agent log
        debug_log = {
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": "D",
            "location": "webhook_service/main.py:509",
            "message": "json_parse_error",
            "data": {"error": str(e), "raw_body_preview": raw_body_str[:200] if 'raw_body_str' in locals() else "N/A"},
            "timestamp": int(datetime.utcnow().timestamp() * 1000)
        }
        try:
            DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(debug_log, ensure_ascii=False) + "\n")
        except Exception as log_err:
            print(f"DEBUG LOG ERROR: {log_err}, path: {DEBUG_LOG_PATH}")
        # #endregion
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": "validation",
            "message": "Invalid JSON payload",
            "context": {"error": str(e)}
        }
        print(json.dumps(log_entry))
        return JSONResponse(
            status_code=200,
            content={"ok": True, "message": "Update received"}
        )
    
    # #region agent log
    # Проверяем наличие message.chat.id в parsed body
    has_message = "message" in body if isinstance(body, dict) else False
    has_chat_id = False
    chat_id_value = None
    
    if has_message and isinstance(body.get("message"), dict):
        message = body["message"]
        if "chat" in message and isinstance(message.get("chat"), dict):
            chat_id_value = message["chat"].get("id")
            has_chat_id = chat_id_value is not None
    
    debug_log = {
        "sessionId": "debug-session",
        "runId": "run1",
        "hypothesisId": "A",
        "location": "webhook_service/main.py:523",
        "message": "telegram_webhook_parsed_update",
        "data": {
            "parsed_update_received": "YES",
            "update_keys": list(body.keys()) if isinstance(body, dict) else [],
            "has_message": has_message,
            "has_chat_id": has_chat_id,
            "chat_id_value": chat_id_value,
            "message_structure": {
                "keys": list(body.get("message", {}).keys()) if has_message else [],
                "has_chat": "chat" in body.get("message", {}) if has_message else False,
                "chat_keys": list(body.get("message", {}).get("chat", {}).keys()) if has_message and "chat" in body.get("message", {}) else []
            },
            "full_update": body  # Полный Update для анализа
        },
        "timestamp": int(datetime.utcnow().timestamp() * 1000)
    }
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(debug_log, ensure_ascii=False) + "\n")
    except Exception as log_err:
        print(f"DEBUG LOG ERROR: {log_err}, path: {DEBUG_LOG_PATH}")
    # #endregion
    
    # ЛОГИРОВАНИЕ: логируем ВЕСЬ parsed body без преобразований
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event": "telegram_webhook_parsed_update",
        "update": body  # Весь Telegram Update целиком как объект
    }
    print(json.dumps(log_entry))
    
    # Валидация payload structure
    if not isinstance(body, dict):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": "validation",
            "message": "Payload must be object",
            "context": {"body_type": str(type(body))}
        }
        print(json.dumps(log_entry))
        return JSONResponse(
            status_code=200,
            content={"ok": True, "message": "Update received"}
        )
    
    # Валидация update_id
    update_id = body.get("update_id")
    if update_id is None:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": "validation",
            "message": "update_id is required",
            "context": {}
        }
        print(json.dumps(log_entry))
        return JSONResponse(
            status_code=200,
            content={"ok": True, "message": "Update received"}
        )
    
    # Нормализация occurred_at
    # Пытаемся найти timestamp из message или callback_query
    occurred_at = None
    if "message" in body and body["message"].get("date"):
        occurred_at = datetime.utcfromtimestamp(body["message"]["date"]).isoformat() + "Z"
    elif "callback_query" in body and body["callback_query"].get("message") and body["callback_query"]["message"].get("date"):
        occurred_at = datetime.utcfromtimestamp(body["callback_query"]["message"]["date"]).isoformat() + "Z"
    else:
        occurred_at = datetime.utcnow().isoformat() + "Z"
    
    # Нормализация в canonical event
    telegram_event = {
        "source": "telegram",
        "event_type": "telegram_update",
        "external_id": str(update_id),
        "occurred_at": occurred_at,
        "payload": body  # Полный Telegram Update
    }
    
    # Idempotency key
    idempotency_key = f"telegram:update:{update_id}"
    
    # #region agent log
    debug_log("A", "webhook_service/main.py:685", "Telegram webhook received", {"update_id": update_id, "has_message": "message" in body, "text": body.get("message", {}).get("text", "")[:50]})
    # #endregion
    
    conn = None
    cursor = None
    trace_id = str(uuid4())
    try:
        conn = get_db_connection()
        insert_result = _insert_job_with_idempotency(
            conn=conn,
            job_type="telegram_update",
            payload=telegram_event,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )

        # #region agent log
        debug_log(
            "B",
            "webhook_service/main.py:702",
            "Job created in job_queue",
            {
                "job_id": insert_result["job_id"],
                "update_id": update_id,
                "idempotency_key": idempotency_key,
                "trace_id": insert_result["trace_id"],
            },
        )
        # #endregion

        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "telegram_webhook_job_created" if insert_result["created"] else "telegram_webhook_idempotent",
            "job_id": insert_result["job_id"],
            "update_id": update_id,
            "idempotency_key": idempotency_key,
            "existing_job_status": None if insert_result["created"] else insert_result["status"],
            "trace_id": insert_result["trace_id"],
        }
        print(json.dumps(log_entry))

        return JSONResponse(
            status_code=200,
            content={"ok": True, "message": "Update received", "trace_id": insert_result["trace_id"]},
        )
    except Exception as e:
        if conn:
            conn.rollback()
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": "database",
            "message": f"Database error: {str(e)}",
            "context": {"update_id": update_id}
        }
        print(json.dumps(log_entry))
        
        return JSONResponse(
            status_code=200,
            content={"ok": True, "message": "Update received"}
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)


@app.post("/webhook/cdek-shipment-status")
async def cdek_shipment_status_webhook(request: Request):
    """
    CDEK Adapter - принимает webhook от CDEK о статусе накладной
    
    - Принимает POST с JSON payload от CDEK
    - Валидирует наличие cdek_uuid или request_uuid
    - Нормализует в canonical event
    - Ставит job в job_queue с job_type = "cdek_shipment_status"
    - Всегда возвращает 200 OK
    """
    try:
        body = await request.json()
    except Exception as e:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": "validation",
            "message": "Invalid JSON payload",
            "context": {"error": str(e)}
        }
        print(json.dumps(log_entry))
        return JSONResponse(
            status_code=200,
            content={"ok": True, "message": "Status update received"}
        )
    
    # Валидация payload structure
    if not isinstance(body, dict):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": "validation",
            "message": "Payload must be object",
            "context": {"body_type": str(type(body))}
        }
        print(json.dumps(log_entry))
        return JSONResponse(
            status_code=200,
            content={"ok": True, "message": "Status update received"}
        )
    
    # Валидация: наличие cdek_uuid или request_uuid
    cdek_uuid = body.get("cdek_uuid") or body.get("cdekUuid") or body.get("uuid")
    request_uuid = body.get("request_uuid") or body.get("requestUuid")
    
    external_id = cdek_uuid or request_uuid
    if not external_id:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": "validation",
            "message": "cdek_uuid or request_uuid is required",
            "context": {}
        }
        print(json.dumps(log_entry))
        return JSONResponse(
            status_code=200,
            content={"ok": True, "message": "Status update received"}
        )
    
    # Нормализация occurred_at
    status_date = body.get("status_date") or body.get("statusDate") or body.get("date")
    if status_date:
        # Если статус дата есть, используем её (может быть timestamp или ISO8601)
        if isinstance(status_date, (int, float)):
            occurred_at = datetime.utcfromtimestamp(status_date).isoformat() + "Z"
        elif isinstance(status_date, str):
            occurred_at = status_date  # Предполагаем, что уже ISO8601
        else:
            occurred_at = datetime.utcnow().isoformat() + "Z"
    else:
        occurred_at = datetime.utcnow().isoformat() + "Z"
    
    # Нормализация в canonical event
    cdek_event = {
        "source": "cdek",
        "event_type": "shipment_status_update",
        "external_id": str(external_id),
        "occurred_at": occurred_at,
        "payload": body  # Полный CDEK webhook payload
    }
    
    # Idempotency key (включаем occurred_at для уникальности)
    idempotency_key = f"cdek:shipment_status_update:{external_id}:{occurred_at}"
    
    conn = None
    cursor = None
    trace_id = str(uuid4())
    try:
        conn = get_db_connection()
        insert_result = _insert_job_with_idempotency(
            conn=conn,
            job_type="cdek_shipment_status",
            payload=cdek_event,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )

        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "cdek_webhook_job_created" if insert_result["created"] else "cdek_webhook_idempotent",
            "job_id": insert_result["job_id"],
            "external_id": str(external_id),
            "idempotency_key": idempotency_key,
            "existing_job_status": None if insert_result["created"] else insert_result["status"],
            "trace_id": insert_result["trace_id"],
        }
        print(json.dumps(log_entry))

        return JSONResponse(
            status_code=200,
            content={"ok": True, "message": "Status update received", "trace_id": insert_result["trace_id"]},
        )
    except Exception as e:
        if conn:
            conn.rollback()
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": "database",
            "message": f"Database error: {str(e)}",
            "context": {"external_id": str(external_id)}
        }
        print(json.dumps(log_entry))
        
        return JSONResponse(
            status_code=200,
            content={"ok": True, "message": "Status update received"}
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    conn = None
    try:
        conn = get_db_connection()
        return {"status": "healthy", "service": "webhook-queue"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unreachable: {str(e)}")
    finally:
        if conn:
            return_db_connection(conn)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)


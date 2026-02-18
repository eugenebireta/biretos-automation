"""
FastAPI приложение для приёма webhook от Т-Банка
"""

import os
import uuid
from typing import Dict, Any
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .logger import get_logger
from .validators import validate_tbank_payload, normalize_payload
from .forwarder import N8NForwarder, ForwarderError


# Инициализация логгера
logger = get_logger()

# Инициализация FastAPI
app = FastAPI(
    title="T-Bank Webhook Gateway",
    description="Lightweight webhook receiver для Т-Банка",
    version="1.0.0"
)

# Инициализация forwarder
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("N8N_WEBHOOK_SECRET", "")
N8N_TIMEOUT = int(os.getenv("N8N_TIMEOUT", "10"))

if not N8N_WEBHOOK_URL:
    raise ValueError("N8N_WEBHOOK_URL environment variable is required")
if not WEBHOOK_SECRET:
    raise ValueError("N8N_WEBHOOK_SECRET environment variable is required")

forwarder = N8NForwarder(N8N_WEBHOOK_URL, WEBHOOK_SECRET, N8N_TIMEOUT)


def get_client_ip(request: Request) -> str:
    """Извлечение IP адреса клиента"""
    # Проверяем X-Forwarded-For (для nginx reverse proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Берём первый IP (оригинальный клиент)
        return forwarded_for.split(",")[0].strip()
    
    # Проверяем X-Real-IP (альтернативный заголовок)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # Fallback на direct connection
    if request.client:
        return request.client.host
    
    return "unknown"


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "tbank-webhook-gateway",
        "version": "1.0.0"
    }


@app.post("/webhook/tbank")
async def receive_tbank_webhook(
    request: Request,
    payload: Dict[str, Any]
):
    """
    Endpoint для приёма webhook от Т-Банка
    
    Args:
        request: FastAPI request object
        payload: JSON payload от Т-Банка
        
    Returns:
        JSONResponse с статусом
    """
    # Генерация request ID для трейсинга
    request_id = str(uuid.uuid4())
    
    # Извлечение IP адреса
    source_ip = get_client_ip(request)
    
    try:
        # Валидация payload
        is_valid, error_message = validate_tbank_payload(payload)
        
        if not is_valid:
            logger.validation_failed(
                invoice_id=payload.get("invoice_id", "unknown"),
                error=error_message,
                request_id=request_id
            )
            raise HTTPException(status_code=400, detail=error_message)
        
        # Нормализация payload
        normalized = normalize_payload(payload)
        invoice_id = normalized["invoice_id"]
        status = normalized["status"]
        
        # Логирование получения webhook
        logger.webhook_received(
            invoice_id=invoice_id,
            status=status,
            source_ip=source_ip,
            request_id=request_id
        )
        
        # Проксирование в n8n (асинхронно, не блокируем ответ)
        import asyncio
        
        async def forward_async():
            try:
                status_code, error = await forwarder.forward(
                    normalized,
                    request_id,
                    source_ip
                )
                
                if error:
                    logger.forward_failed(
                        invoice_id=invoice_id,
                        request_id=request_id,
                        error=error,
                        n8n_response_code=status_code
                    )
                else:
                    logger.forward_success(
                        invoice_id=invoice_id,
                        request_id=request_id,
                        n8n_response_code=status_code
                    )
            except ForwarderError as e:
                logger.forward_failed(
                    invoice_id=invoice_id,
                    request_id=request_id,
                    error=str(e)
                )
            except Exception as e:
                logger.forward_failed(
                    invoice_id=invoice_id,
                    request_id=request_id,
                    error=f"Unexpected error: {str(e)}"
                )
        
        # Запускаем forward в фоне (fire-and-forget)
        asyncio.create_task(forward_async())
        
        # Немедленно отвечаем 200 OK
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "message": "Webhook received",
                "request_id": request_id
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        # Неожиданная ошибка
        logger.logger.error(
            f"Unexpected error processing webhook: {str(e)}",
            extra={
                "request_id": request_id,
                "error": str(e)
            }
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Обработчик HTTP исключений"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "detail": exc.detail
        }
    )









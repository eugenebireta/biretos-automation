"""
Structured logging для webhook gateway
"""

import logging
import sys
from datetime import datetime
from typing import Any, Dict
import json
import uuid


class StructuredLogger:
    """Structured JSON logger для webhook gateway"""
    
    def __init__(self, name: str = "tbank_gateway"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Console handler с JSON форматированием
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        self.logger.addHandler(handler)
        
    def _log(self, level: str, event_type: str, **kwargs):
        """Создать структурированный лог"""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level.upper(),
            "event_type": event_type,
            **kwargs
        }
        
        method = getattr(self.logger, level.lower())
        method(json.dumps(log_data, ensure_ascii=False))
    
    def webhook_received(self, invoice_id: str, status: str, source_ip: str, request_id: str):
        """Лог получения webhook"""
        self._log(
            "info",
            "webhook_received",
            invoice_id=invoice_id,
            status=status,
            source_ip=source_ip,
            request_id=request_id
        )
    
    def validation_failed(self, invoice_id: str, error: str, request_id: str):
        """Лог ошибки валидации"""
        self._log(
            "warning",
            "validation_failed",
            invoice_id=invoice_id,
            error_message=error,
            request_id=request_id
        )
    
    def forward_success(self, invoice_id: str, request_id: str, n8n_response_code: int):
        """Лог успешного проксирования"""
        self._log(
            "info",
            "forward_success",
            invoice_id=invoice_id,
            request_id=request_id,
            n8n_response_code=n8n_response_code
        )
    
    def forward_failed(self, invoice_id: str, request_id: str, error: str, n8n_response_code: int = None):
        """Лог ошибки проксирования"""
        log_data = {
            "invoice_id": invoice_id,
            "request_id": request_id,
            "error_message": error
        }
        if n8n_response_code:
            log_data["n8n_response_code"] = n8n_response_code
            
        self._log("error", "forward_failed", **log_data)


class JsonFormatter(logging.Formatter):
    """JSON formatter для логов"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Если запись уже JSON строка, вернуть как есть
        if isinstance(record.msg, str):
            try:
                json.loads(record.msg)
                return record.msg
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Иначе создать JSON из атрибутов
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
        }
        
        # Добавить дополнительные поля если есть
        if hasattr(record, "event_type"):
            log_data["event_type"] = record.event_type
        
        return json.dumps(log_data, ensure_ascii=False)


def get_logger(name: str = "tbank_gateway") -> StructuredLogger:
    """Получить экземпляр логгера"""
    return StructuredLogger(name)









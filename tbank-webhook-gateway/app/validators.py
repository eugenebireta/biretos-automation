"""
Валидация payload от Т-Банка webhook
"""

from typing import Dict, Any, Tuple, Optional
from datetime import datetime


class ValidationError(Exception):
    """Ошибка валидации payload"""
    pass


def validate_tbank_payload(payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Валидация payload от Т-Банка
    
    Обязательные поля:
    - invoice_id: string, непустой
    - status: string, значение "PAID"
    
    Опциональные:
    - amount: number
    - currency: string
    - timestamp: ISO 8601
    - metadata: object
    
    Returns:
        (is_valid, error_message)
    """
    
    # Проверка наличия invoice_id
    invoice_id = payload.get("invoice_id")
    if not invoice_id:
        # Пробуем альтернативные поля
        invoice_id = payload.get("invoiceId") or payload.get("id")
        if invoice_id:
            payload["invoice_id"] = invoice_id
        else:
            return False, "Отсутствует обязательное поле: invoice_id"
    
    if not isinstance(invoice_id, str) or not invoice_id.strip():
        return False, "invoice_id должен быть непустой строкой"
    
    # Проверка status
    status = payload.get("status")
    if not status:
        status = payload.get("payment_status") or payload.get("state")
        if status:
            payload["status"] = status
        else:
            return False, "Отсутствует обязательное поле: status"
    
    if not isinstance(status, str):
        return False, "status должен быть строкой"
    
    status_upper = status.upper()
    if status_upper != "PAID":
        return False, f"status должен быть 'PAID', получен: {status}"
    
    # Нормализация status
    payload["status"] = status_upper
    
    # Валидация опциональных полей
    if "amount" in payload and payload["amount"] is not None:
        try:
            amount = float(payload["amount"])
            payload["amount"] = amount
        except (ValueError, TypeError):
            return False, "amount должен быть числом"
    
    if "currency" in payload and payload["currency"] is not None:
        if not isinstance(payload["currency"], str):
            return False, "currency должен быть строкой"
        if not payload["currency"]:
            payload["currency"] = "RUB"
    
    if "timestamp" in payload and payload["timestamp"] is not None:
        timestamp_str = payload["timestamp"]
        try:
            # Пробуем распарсить ISO 8601
            datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            # Если не валидный ISO 8601, всё равно оставляем (n8n разберётся)
            pass
    
    if "metadata" in payload and payload["metadata"] is not None:
        if not isinstance(payload["metadata"], dict):
            return False, "metadata должен быть объектом"
    
    return True, None


def normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Нормализация payload для единообразной обработки
    
    Приводит к стандартному виду с нормализованными полями
    """
    normalized = {
        "invoice_id": payload.get("invoice_id") or payload.get("invoiceId") or payload.get("id"),
        "status": (payload.get("status") or payload.get("payment_status") or payload.get("state") or "").upper(),
    }
    
    # Опциональные поля
    if "amount" in payload:
        normalized["amount"] = payload["amount"]
    
    normalized["currency"] = payload.get("currency") or "RUB"
    
    if "timestamp" in payload:
        normalized["timestamp"] = payload["timestamp"]
    else:
        normalized["timestamp"] = datetime.utcnow().isoformat() + "Z"
    
    if "metadata" in payload:
        normalized["metadata"] = payload["metadata"]
    else:
        normalized["metadata"] = {}
    
    return normalized









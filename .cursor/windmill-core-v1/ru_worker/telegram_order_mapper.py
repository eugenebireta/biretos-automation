"""
Telegram Order Mapper

Назначение: определяет, относится ли Telegram update к заказу.

Правила:
- Если невозможно однозначно определить order_id → возвращает None
- Никакой FSM
- Никаких side-effects
- Чистая функция: telegram_event → OrderEvent | None
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
from uuid import UUID


@dataclass
class OrderEvent:
    """Canonical order event для FSM"""
    event_id: UUID
    source: str  # "telegram"
    event_type: str  # order-related event type
    external_id: str
    occurred_at: str  # ISO8601
    payload: Dict[str, Any]  # order-related payload
    order_id: UUID  # привязанный order_id


def map_telegram_to_order_event(telegram_event: Dict[str, Any], event_id: UUID) -> Optional[OrderEvent]:
    """
    Маппит Telegram event в OrderEvent (если применимо).
    
    Args:
        telegram_event: нормализованный telegram event из job_queue
            {
                "source": "telegram",
                "event_type": "telegram_update",
                "external_id": "update_id",
                "occurred_at": "ISO8601",
                "payload": { ... Telegram Update ... }
            }
        event_id: UUID для нового order event
    
    Returns:
        OrderEvent если удалось определить order_id, иначе None
    """
    payload = telegram_event.get("payload", {})
    external_id = telegram_event.get("external_id")
    occurred_at = telegram_event.get("occurred_at")
    
    if not external_id or not occurred_at:
        return None
    
    # Пытаемся извлечь order_id из callback_data
    order_id = _extract_order_id_from_callback_data(payload)
    if order_id:
        # Найден order_id в callback_data
        return OrderEvent(
            event_id=event_id,
            source="telegram",
            event_type="telegram_callback_order",
            external_id=external_id,
            occurred_at=occurred_at,
            payload={
                "callback_data": payload.get("callback_query", {}).get("data"),
                "chat_id": payload.get("callback_query", {}).get("message", {}).get("chat", {}).get("id"),
                "order_id": str(order_id)
            },
            order_id=order_id
        )
    
    # Дополнительные правила маппинга можно добавить здесь
    # Например: проверка metadata.telegram_chat_id в order_ledger
    # Но для текущей реализации достаточно callback_data
    
    return None


def _extract_order_id_from_callback_data(payload: Dict[str, Any]) -> Optional[UUID]:
    """
    Извлекает order_id из callback_data Telegram Update.
    
    Формат callback_data (предполагаемый):
    - "order_id:{uuid}" - прямой формат
    - "open:{uuid}" - формат из n8n workflow
    - "check:{uuid}", "ship:{uuid}" - другие форматы
    
    Args:
        payload: Telegram Update payload
    
    Returns:
        UUID если найден, иначе None
    """
    callback_query = payload.get("callback_query")
    if not callback_query:
        return None
    
    callback_data = callback_query.get("data")
    if not callback_data or not isinstance(callback_data, str):
        return None
    
    # Пытаемся извлечь UUID из различных форматов
    # Формат: "prefix:uuid" или просто "uuid"
    parts = callback_data.split(":", 1)
    if len(parts) == 2:
        # Формат "prefix:uuid"
        try:
            return UUID(parts[1])
        except (ValueError, AttributeError):
            pass
    else:
        # Возможно, просто UUID
        try:
            return UUID(callback_data)
        except (ValueError, AttributeError):
            pass
    
    return None























"""
CDEK Order Mapper

Назначение: определяет, относится ли CDEK shipment status update к заказу.

Правила:
- Lookup order_id возможен ТОЛЬКО по cdek_uuid
- Если order не найден → возвращает None
- Никакой FSM
- Никаких side-effects
- Чистая функция: cdek_event → OrderEventInput | None
"""

from typing import Dict, Any, Optional
from uuid import UUID

from domain.cdm.event import OrderEventInput


def map_cdek_to_order_event(cdek_event: Dict[str, Any], event_id: UUID, db_conn) -> Optional[OrderEventInput]:
    """
    Маппит CDEK event в OrderEvent (если применимо).
    
    Args:
        cdek_event: нормализованный cdek event из job_queue
            {
                "source": "cdek",
                "event_type": "shipment_status_update",
                "external_id": "cdek_uuid",
                "occurred_at": "ISO8601",
                "payload": { ... CDEK webhook payload ... }
            }
        event_id: UUID для нового order event
        db_conn: PostgreSQL connection для lookup order_ledger
    
    Returns:
        OrderEventInput если удалось найти order по cdek_uuid, иначе None
    """
    payload = cdek_event.get("payload", {})
    external_id = cdek_event.get("external_id")
    occurred_at = cdek_event.get("occurred_at")
    
    if not external_id or not occurred_at:
        return None
    
    # Извлекаем cdek_uuid из payload или external_id
    cdek_uuid = payload.get("cdek_uuid") or payload.get("cdekUuid") or payload.get("uuid") or external_id
    
    # Lookup shipments по carrier_external_id (Phase 2, 1:N model).
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT order_id
            FROM shipments
            WHERE carrier_code = 'cdek'
              AND carrier_external_id = %s
              AND current_status <> 'cancelled'
            ORDER BY shipment_seq DESC
            LIMIT 1
            """,
            (cdek_uuid,)
        )
    except Exception:
        # Backward compatibility with pre-Phase2 schema.
        db_conn.rollback()
        cursor = db_conn.cursor()
        cursor.execute(
            """
            SELECT order_id
            FROM order_ledger
            WHERE cdek_uuid = %s
            LIMIT 1
            """,
            (cdek_uuid,),
        )
    
    result = cursor.fetchone()
    cursor.close()
    
    if not result:
        # Order не найден
        return None
    
    order_id = result[0]
    
    # Создаем OrderEventInput
    return OrderEventInput(
        event_id=event_id,
        source="cdek",
        event_type="cdek_status_update",
        external_id=external_id,
        occurred_at=occurred_at,
        payload={
            "cdek_uuid": cdek_uuid,
            "status": payload.get("status") or payload.get("Status"),
            "status_date": payload.get("status_date") or payload.get("statusDate") or payload.get("date"),
            "order_id": str(order_id)
        },
        order_id=UUID(str(order_id))
    )























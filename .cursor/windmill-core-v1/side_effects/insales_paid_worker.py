"""
InSales Paid Worker

Синхронизирует financial_status='paid' в InSales после FSM transition.

Poll order_ledger WHERE state='paid' AND metadata.insales_paid_synced IS NULL.
PUT InSales /admin/orders/{insales_order_id}.json с financial_status='paid'.
UPDATE Ledger metadata.insales_paid_synced = true.

FSM не трогает - это side-effect после transition.
"""

import json
from datetime import datetime
from typing import Dict, Any

from psycopg2.extras import RealDictCursor

from side_effects.adapters.insales_adapter import InSalesOrderAdapter

_INSALES_ADAPTER = InSalesOrderAdapter()


def _parse_jsonb(value: Any) -> Dict[str, Any]:
    """Парсит JSONB значение."""
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except:
            return {}
    return {}


def execute_insales_paid_sync(payload: Dict[str, Any], db_conn) -> Dict[str, Any]:
    """
    Обрабатывает insales_paid_sync job.
    
    Payload должен содержать:
    - order_id: str (UUID) - опционально, если не указан - обрабатывает все несинхронизированные
    - batch_size: int (опционально, по умолчанию 10)
    """
    order_id_str = payload.get("order_id")
    batch_size = payload.get("batch_size", 10)
    
    cursor = db_conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        if order_id_str:
            # Обработка конкретного заказа
            from uuid import UUID
            try:
                order_id = UUID(order_id_str)
            except:
                raise Exception(f"Invalid order_id format: {order_id_str}")
            
            cursor.execute(
                """
                SELECT * FROM order_ledger
                WHERE order_id = %s
                  AND state = 'paid'
                  AND (metadata->>'insales_paid_synced') IS NULL
                LIMIT 1
                """,
                (order_id,)
            )
            
            orders = cursor.fetchall()
        else:
            # Poll всех несинхронизированных
            cursor.execute(
                """
                SELECT * FROM order_ledger
                WHERE state = 'paid'
                  AND (metadata->>'insales_paid_synced') IS NULL
                ORDER BY updated_at ASC
                LIMIT %s
                """,
                (batch_size,)
            )
            
            orders = cursor.fetchall()
        
        if not orders:
            return {
                "job_type": "insales_paid_sync",
                "status": "completed",
                "synced_count": 0,
                "message": "No orders to sync"
            }
        
        synced_count = 0
        errors = []
        
        for order in orders:
            order_id = order.get("order_id")
            insales_order_id = order.get("insales_order_id")
            metadata = _parse_jsonb(order.get("metadata"))
            
            if not insales_order_id:
                errors.append({
                    "order_id": str(order_id),
                    "error": "insales_order_id is missing"
                })
                continue
            
            try:
                _INSALES_ADAPTER.set_order_financial_status(insales_order_id, "paid")
                response_success = True
            except Exception as e:
                errors.append({
                    "order_id": str(order_id),
                    "insales_order_id": insales_order_id,
                    "error": str(e)
                })
                log_entry = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "event": "insales_paid_sync_error",
                    "order_id": str(order_id),
                    "insales_order_id": insales_order_id,
                    "error": str(e)
                }
                print(json.dumps(log_entry))
                continue
            
            # UPDATE Ledger metadata.insales_paid_synced = true (выполняется в обоих режимах при успехе)
            if response_success:
                updated_metadata = metadata.copy()
                updated_metadata["insales_paid_synced"] = True
                
                cursor.execute(
                    """
                    UPDATE order_ledger
                    SET metadata = %s::jsonb,
                        updated_at = NOW()
                    WHERE order_id = %s
                    """,
                    (json.dumps(updated_metadata), order_id)
                )
                
                synced_count += 1
        
        db_conn.commit()
        
        return {
            "job_type": "insales_paid_sync",
            "status": "completed",
            "synced_count": synced_count,
            "errors_count": len(errors),
            "errors": errors if errors else None
        }
    
    finally:
        cursor.close()


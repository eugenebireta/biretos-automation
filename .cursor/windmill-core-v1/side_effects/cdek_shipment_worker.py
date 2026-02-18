"""
CDEK shipment worker (Phase 2 / Contract Pack v2.1).

Core:
- supports 1:N shipments
- legacy order_ledger.cdek_uuid cache maintained by ShipmentService
- cancellation path triggers deterministic unpack flow
- provider HTTP delegated to adapters
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, Any
from uuid import UUID, uuid4

import httpx
from psycopg2.extras import RealDictCursor

from config import get_config
from domain.shipment_service import (
    create_shipment_atomic,
    update_shipment_status_atomic,
)
from domain.ports import ShipmentCreateRequest
from side_effects.adapters.factory import (
    get_order_source_adapter,
    get_shipment_adapter,
)

_CONFIG = get_config()
TELEGRAM_BOT_TOKEN = _CONFIG.telegram_bot_token
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def _parse_jsonb(value: Any) -> Dict[str, Any]:
    """РџР°СЂСЃРёС‚ JSONB Р·РЅР°С‡РµРЅРёРµ."""
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


def _send_telegram_message(chat_id: int, text: str) -> Dict[str, Any]:
    """РћС‚РїСЂР°РІР»СЏРµС‚ СЃРѕРѕР±С‰РµРЅРёРµ РІ Telegram."""
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    
    # Telegram API РІСЃРµРіРґР° СЂРµР°Р»СЊРЅС‹Р№ (РЅРµ РёСЃРїРѕР»СЊР·СѓРµС‚ DRY_RUN, С‡С‚РѕР±С‹ UI Р±С‹Р» Р¶РёРІРѕР№)
    if not TELEGRAM_BOT_TOKEN:
        raise Exception("TELEGRAM_BOT_TOKEN is not set")
    
    response = httpx.post(url, json=payload, timeout=10.0)
    response.raise_for_status()
    return response.json()


def _answer_callback_query(callback_query_id: str, text: str) -> Dict[str, Any]:
    """РћС‚РІРµС‡Р°РµС‚ РЅР° callback query."""
    url = f"{TELEGRAM_API_URL}/answerCallbackQuery"
    payload = {
        "callback_query_id": callback_query_id,
        "text": text
    }
    
    # Telegram API РІСЃРµРіРґР° СЂРµР°Р»СЊРЅС‹Р№ (РЅРµ РёСЃРїРѕР»СЊР·СѓРµС‚ DRY_RUN, С‡С‚РѕР±С‹ UI Р±С‹Р» Р¶РёРІРѕР№)
    if not TELEGRAM_BOT_TOKEN:
        raise Exception("TELEGRAM_BOT_TOKEN is not set")
    
    response = httpx.post(url, json=payload, timeout=10.0)
    response.raise_for_status()
    return response.json()


def execute_cdek_shipment(payload: Dict[str, Any], db_conn) -> Dict[str, Any]:
    """
    РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ cdek_shipment job.
    
    Payload РґРѕР»Р¶РµРЅ СЃРѕРґРµСЂР¶Р°С‚СЊ:
    - order_id: str (UUID)
    - initiator_chat_id: int (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ, РґР»СЏ Telegram РѕС‚РІРµС‚Р°)
    - initiator_user_id: int (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ)
    - callback_query_id: str (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ, РґР»СЏ callback answer)
    """
    order_id_str = payload.get("order_id")
    initiator_chat_id = payload.get("initiator_chat_id")
    initiator_user_id = payload.get("initiator_user_id")
    callback_query_id = payload.get("callback_query_id")
    trace_id = payload.get("_trace_id") or payload.get("trace_id")
    execution_mode = (payload.get("execution_mode") or _CONFIG.execution_mode or "LIVE").upper()
    
    if not order_id_str:
        raise Exception("order_id is required in payload")
    
    try:
        order_id = UUID(order_id_str)
    except:
        raise Exception(f"Invalid order_id format: {order_id_str}")
    
    cursor = db_conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        if payload.get("action") == "cancel":
            shipment_id = payload.get("shipment_id")
            cdek_uuid = payload.get("cdek_uuid")
            if not shipment_id and not cdek_uuid:
                raise Exception("shipment_id or cdek_uuid is required for cancel action")

            if shipment_id:
                target_shipment_id = UUID(str(shipment_id))
            else:
                cursor.execute(
                    """
                    SELECT id
                    FROM shipments
                    WHERE order_id = %s
                      AND carrier_code = 'cdek'
                      AND carrier_external_id = %s
                    ORDER BY shipment_seq DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (str(order_id), str(cdek_uuid)),
                )
                row = cursor.fetchone()
                if not row:
                    raise Exception(f"Shipment not found for cdek_uuid={cdek_uuid}")
                target_shipment_id = UUID(str(row["id"]))

            result = update_shipment_status_atomic(
                db_conn,
                shipment_id=target_shipment_id,
                to_status="cancelled",
                event_id=str(uuid4()),
                occurred_at=datetime.utcnow().isoformat() + "Z",
                reason="SHIPMENT_VOIDED",
                trace_id=trace_id,
                context={"source": "cdek_shipment_worker"},
            )
            db_conn.commit()
            if initiator_chat_id:
                _send_telegram_message(initiator_chat_id, "вќЋ РќР°РєР»Р°РґРЅР°СЏ РѕС‚РјРµРЅРµРЅР°, СЂР°СЃРїСЂРµРґРµР»РµРЅРёРµ РїРµСЂРµСЃС‡РёС‚Р°РЅРѕ.")
            if callback_query_id:
                _answer_callback_query(callback_query_id, "РќР°РєР»Р°РґРЅР°СЏ РѕС‚РјРµРЅРµРЅР°")
            return {
                "job_type": "cdek_shipment",
                "status": "completed",
                "ok": True,
                "order_id": str(order_id),
                "shipment_id": str(target_shipment_id),
                "cancel_result": result,
            }

        # SQL 1.2: GET РїРѕ order_id (1-РІ-1 РёР· forensic mapping)
        cursor.execute(
            """
            SELECT * FROM order_ledger
            WHERE order_id = %s
            LIMIT 1
            """,
            (order_id,)
        )
        
        order = cursor.fetchone()
        if not order:
            raise Exception(f"Order not found: {order_id_str}")
        
        # РџР°СЂСЃРёРЅРі РґР°РЅРЅС‹С…
        customer_data = _parse_jsonb(order.get("customer_data"))
        delivery_data = _parse_jsonb(order.get("delivery_data"))
        metadata = _parse_jsonb(order.get("metadata"))
        
        # Р’РђР›РР”РђР¦РРЇ РРќР’РђР РРђРќРўРћР’ (1-РІ-1 РёР· n8n Prepare Order Context)
        
        # 1. state РґРѕР»Р¶РµРЅ РїРѕР·РІРѕР»СЏС‚СЊ СЃРѕР·РґР°РЅРёРµ РЅРѕРІРѕР№ РѕС‚РіСЂСѓР·РєРё
        state = (order.get("state") or "").lower()
        if state not in {"paid", "shipment_pending", "partially_shipped"}:
            error_msg = "РЎС‡С‘С‚ РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ РѕРїР»Р°С‡РµРЅ РїРµСЂРµРґ СЃРѕР·РґР°РЅРёРµРј РЅР°РєР»Р°РґРЅРѕР№."
            if initiator_chat_id:
                _send_telegram_message(initiator_chat_id, f"вќЊ {error_msg}")
            if callback_query_id:
                _answer_callback_query(callback_query_id, "РћС€РёР±РєР°")
            return {
                "job_type": "cdek_shipment",
                "status": "completed",
                "ok": False,
                "error": {
                    "code": "NOT_PAID",
                    "message": error_msg
                }
            }
        
        # 2. РџСЂРѕРІРµСЂРєР° РѕР±СЏР·Р°С‚РµР»СЊРЅС‹С… РїРѕР»РµР№ (phone, email)
        required_fields = []
        if not customer_data.get("phone"):
            required_fields.append("phone")
        if not customer_data.get("email"):
            required_fields.append("email")
        
        if required_fields:
            # Р”Р°РЅРЅС‹С… РЅРµС‚ в†’ СЃРѕС…СЂР°РЅСЏРµРј dialog_context (1-РІ-1 РёР· n8n Prepare Dialog Upsert)
            missing_field = required_fields[0]  # Р‘РµСЂРµРј РїРµСЂРІС‹Р№ РЅРµРґРѕСЃС‚Р°СЋС‰РёР№
            
            dialog_context = {
                "action": "create_cdek_shipment",
                "missing_field": missing_field,
                "missing_fields": required_fields,
                "order_id": str(order_id),
                "chat_id": str(initiator_chat_id) if initiator_chat_id else None,
                "user_id": str(initiator_user_id) if initiator_user_id else None,
                "requested_at": datetime.utcnow().isoformat() + "Z"
            }
            
            updated_metadata = metadata.copy()
            updated_metadata["dialog_context"] = dialog_context
            
            # SQL 1.1: UPSERT metadata (РѕР±РЅРѕРІР»РµРЅРёРµ dialog_context)
            cursor.execute(
                """
                UPDATE order_ledger
                SET metadata = %s::jsonb,
                    updated_at = NOW()
                WHERE order_id = %s
                RETURNING *
                """,
                (json.dumps(updated_metadata), order_id)
            )
            db_conn.commit()
            
            # Prompt (1-РІ-1 РёР· n8n)
            if missing_field == "phone":
                prompt = "Р”Р»СЏ РѕС‚РїСЂР°РІРєРё РЅСѓР¶РµРЅ С‚РµР»РµС„РѕРЅ РїРѕР»СѓС‡Р°С‚РµР»СЏ. Р’РІРµРґРёС‚Рµ С‚РµР»РµС„РѕРЅ."
            else:
                prompt = "Р”Р»СЏ РѕС‚РїСЂР°РІРєРё РЅСѓР¶РµРЅ email РїРѕР»СѓС‡Р°С‚РµР»СЏ. Р’РІРµРґРёС‚Рµ email."
            
            # РћС‚РїСЂР°РІРєР° prompt РІ Telegram
            if initiator_chat_id:
                _send_telegram_message(initiator_chat_id, prompt)
            if callback_query_id:
                _answer_callback_query(callback_query_id, "РўСЂРµР±СѓСЋС‚СЃСЏ РґР°РЅРЅС‹Рµ")
            
            return {
                "job_type": "cdek_shipment",
                "status": "completed",
                "ok": False,
                "need_dialog": True,
                "order_id": str(order_id),
                "missing_field": missing_field,
                "prompt": prompt
            }
        
        # Р”Р°РЅРЅС‹Рµ РµСЃС‚СЊ в†’ СЃРѕР·РґР°РµРј РЅР°РєР»Р°РґРЅСѓСЋ (1-РІ-1 РёР· n8n Prepare CDEK Payload)
        
        phone = customer_data.get("phone")
        if not phone:
            raise Exception("Phone is required but not found")
        
        city = delivery_data.get("city") or delivery_data.get("to_location", {}).get("city")
        if not city:
            raise Exception("City is required but not found")
        
        # Packages (1-РІ-1 РёР· n8n)
        packages = delivery_data.get("packages") or metadata.get("packages") or [{
            "weight": metadata.get("packageWeight") or 1000,
            "length": metadata.get("packageLength") or 10,
            "width": metadata.get("packageWidth") or 10,
            "height": metadata.get("packageHeight") or 10
        }]
        
        # CDEK API request body (1-РІ-1 РёР· forensic mapping)
        cdek_body = {
            "type": delivery_data.get("type") or 1,
            "tariff_code": delivery_data.get("tariff_code") or 136,
            "from_location": delivery_data.get("from_location") or {"code": 270},
            "to_location": {
                "city": city,
                "address": delivery_data.get("address") or delivery_data.get("to_location", {}).get("address")
            },
            "recipient": {
                "name": customer_data.get("companyName") or customer_data.get("name") or "РљР»РёРµРЅС‚",
                "company": customer_data.get("companyName"),
                "phones": [{"number": phone}],
                "email": customer_data.get("email") or None
            },
            "packages": packages
        }
        
        # Sender (1-РІ-1 РёР· n8n)
        cdek_body["sender"] = delivery_data.get("sender") or {
            "company": "Biretos",
            "phones": [{"number": "+7 (000) 000-00-00"}],
            "address": "РњРѕСЃРєРІР°"
        }
        
        adapter = get_shipment_adapter(
            execution_mode=execution_mode,
            db_conn=db_conn,
            trace_id=trace_id,
        )
        adapter_response = adapter.create_shipment(
            ShipmentCreateRequest(
                payload=cdek_body,
                trace_id=trace_id,
            )
        )
        cdek_uuid = adapter_response.carrier_external_id
        
        shipment_result = create_shipment_atomic(
            db_conn,
            order_id=order_id,
            trace_id=trace_id,
            carrier_code="cdek",
            carrier_external_id=cdek_uuid,
            service_tariff=str(cdek_body.get("tariff_code")) if cdek_body.get("tariff_code") is not None else None,
            packages=packages,
            address_snapshot={
                "raw": delivery_data.get("address") or delivery_data.get("to_location", {}).get("address"),
                "city": city,
                "recipient_name": customer_data.get("companyName") or customer_data.get("name") or "РљР»РёРµРЅС‚",
                "recipient_phone": phone,
            },
            idempotency_key=f"shipment:cdek:{order_id}:{cdek_uuid}",
            event_id=str(uuid4()),
            occurred_at=datetime.utcnow().isoformat() + "Z",
            metadata={"initiator_user_id": initiator_user_id},
            carrier_metadata=adapter_response.raw_response,
        )

        # РЎРѕР·РґР°РЅРёРµ FSM event (СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚СЊ СЃРѕ СЃС‚Р°СЂС‹Рј РїР°Р№РїР»Р°Р№РЅРѕРј)
        event_id = uuid4()
        order_event_payload = {
            "event_id": str(event_id),
            "source": "cdek",
            "event_type": "SHIPMENT_CREATED",
            "external_id": str(cdek_uuid),
            "occurred_at": datetime.utcnow().isoformat() + "Z",
            "payload": {
                "cdek_uuid": cdek_uuid,
                "order_id": str(order_id)
            },
            "order_id": str(order_id)
        }
        
        cursor.execute(
            """
            INSERT INTO job_queue (id, job_type, payload, status, idempotency_key, trace_id)
            VALUES (gen_random_uuid(), %s, %s, 'pending', %s, %s::uuid)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (
                "order_event",
                json.dumps(order_event_payload),
                f"order_event:cdek:SHIPMENT_CREATED:{cdek_uuid}",
                trace_id,
            )
        )
        fsm_job_row = cursor.fetchone()
        fsm_job_id = str(fsm_job_row[0]) if fsm_job_row else None
        db_conn.commit()
        
        # UPDATE InSales custom field (1-РІ-1 РёР· n8n Update InSales with Track)
        insales_order_id = order.get("insales_order_id")
        if insales_order_id:
            try:
                get_order_source_adapter(execution_mode=execution_mode).set_order_custom_field(
                    external_order_id=insales_order_id,
                    field_handle="cdek_track_number",
                    value=cdek_uuid,
                )
            except Exception as e:
                log_entry = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "event": "cdek_shipment_insales_update_failed",
                    "order_id": str(order_id),
                    "error": str(e)
                }
                print(json.dumps(log_entry))
        
        # РћС‚РїСЂР°РІРєР° РѕС‚РІРµС‚Р° РІ Telegram (1-РІ-1 РёР· n8n Format Success Response)
        success_message = f"рџ“¦ РќР°РєР»Р°РґРЅР°СЏ СЃРѕР·РґР°РЅР°. РўСЂРµРє: {cdek_uuid}"
        
        if initiator_chat_id:
            _send_telegram_message(initiator_chat_id, success_message)
        if callback_query_id:
            _answer_callback_query(callback_query_id, "РќР°РєР»Р°РґРЅР°СЏ СЃРѕР·РґР°РЅР°")
        
        return {
            "job_type": "cdek_shipment",
            "status": "completed",
            "ok": True,
            "order_id": str(order_id),
            "cdek_uuid": cdek_uuid,
            "message": success_message,
            "fsm_job_id": fsm_job_id,
            "shipment_id": shipment_result.get("shipment_id"),
        }
    
    finally:
        cursor.close()



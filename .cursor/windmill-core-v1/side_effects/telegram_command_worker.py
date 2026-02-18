"""
Telegram Command Worker

РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ РєРѕРјР°РЅРґС‹ Telegram Р±РѕС‚Р°:
- /start в†’ СЃРїРёСЃРѕРє РїРѕСЃР»РµРґРЅРёС… СЃС‡РµС‚РѕРІ
- open:<order_id> в†’ РєР°СЂС‚РѕС‡РєР° Р·Р°РєР°Р·Р°
- check:<order_id> в†’ РїСЂРѕРІРµСЂРєР° СЃС‚Р°С‚СѓСЃР°
- Р”РёР°Р»РѕРі Р·Р°РїСЂРѕСЃР° phone/email

РСЃРїРѕР»СЊР·СѓРµС‚ SQL Р·Р°РїСЂРѕСЃС‹ Рё С„РѕСЂРјР°С‚РёСЂРѕРІР°РЅРёРµ 1-РІ-1 РёР· n8n workflows (forensic mapping).
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID

import httpx
import psycopg2
from psycopg2.extras import RealDictCursor

from config import get_config

_CONFIG = get_config()

# РљРѕРЅС„РёРіСѓСЂР°С†РёСЏ Telegram Bot API
TELEGRAM_BOT_TOKEN = _CONFIG.telegram_bot_token
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# DRY-RUN СЂРµР¶РёРј
DRY_RUN_EXTERNAL_APIS = bool(_CONFIG.dry_run_external_apis)

# PostgreSQL connection (Р±СѓРґРµС‚ РїРµСЂРµРґР°РІР°С‚СЊСЃСЏ РёР· ru_worker)
# РСЃРїРѕР»СЊР·СѓРµРј С‚Рµ Р¶Рµ env РїРµСЂРµРјРµРЅРЅС‹Рµ


def _parse_callback_data(callback_data: str) -> tuple[str, Optional[str]]:
    """
    РџР°СЂСЃРёС‚ callback_data РёР· С„РѕСЂРјР°С‚Р° "action:order_id" РёР»Рё "action".
    
    Р’РѕР·РІСЂР°С‰Р°РµС‚ (action, order_id).
    """
    if not callback_data:
        return ("unknown", None)
    
    # Split РїРѕ РїРµСЂРІРѕРјСѓ РІС…РѕР¶РґРµРЅРёСЋ ':'
    # Р’РђР–РќРћ: order_id РјРѕР¶РµС‚ СЃРѕРґРµСЂР¶Р°С‚СЊ UUID, РЅРѕ РЅРµ РґРѕР»Р¶РµРЅ СЃРѕРґРµСЂР¶Р°С‚СЊ ':'
    parts = callback_data.split(":", 1)
    action = parts[0].lower()
    order_id = parts[1] if len(parts) > 1 else None
    
    return (action, order_id)


def _send_telegram_message(chat_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    РћС‚РїСЂР°РІР»СЏРµС‚ СЃРѕРѕР±С‰РµРЅРёРµ РІ Telegram С‡РµСЂРµР· Bot API.
    
    Returns response JSON РёР»Рё raises Exception.
    """
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    # Telegram API РІСЃРµРіРґР° СЂРµР°Р»СЊРЅС‹Р№ (РЅРµ РёСЃРїРѕР»СЊР·СѓРµС‚ DRY_RUN, С‡С‚РѕР±С‹ UI Р±С‹Р» Р¶РёРІРѕР№)
    if not TELEGRAM_BOT_TOKEN:
        error_msg = "TELEGRAM_BOT_TOKEN is not set"
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "telegram_send_error",
            "error": error_msg,
            "chat_id": chat_id,
            "url": url.replace(TELEGRAM_BOT_TOKEN, "***") if TELEGRAM_BOT_TOKEN else url
        }
        print(json.dumps(log_entry))
        raise Exception(error_msg)
    
    # Р›РѕРіРёСЂСѓРµРј РЅР°С‡Р°Р»Рѕ Р·Р°РїСЂРѕСЃР°
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event": "telegram_send_start",
        "chat_id": chat_id,
        "text": text[:50],  # РџРµСЂРІС‹Рµ 50 СЃРёРјРІРѕР»РѕРІ
        "url": url.replace(TELEGRAM_BOT_TOKEN, "***")
    }
    print(json.dumps(log_entry))
    
    try:
        response = httpx.post(url, json=payload, timeout=10.0)
        status_code = response.status_code
        response_body = response.text
        
        # Р›РѕРіРёСЂСѓРµРј РѕС‚РІРµС‚
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "telegram_send_response",
            "status_code": status_code,
            "response_body": response_body[:500]  # РџРµСЂРІС‹Рµ 500 СЃРёРјРІРѕР»РѕРІ
        }
        print(json.dumps(log_entry))
        
        # РџСЂРѕРІРµСЂСЏРµРј СЃС‚Р°С‚СѓСЃ
        response.raise_for_status()
        result = response.json()
        
        # Р›РѕРіРёСЂСѓРµРј СѓСЃРїРµС…
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "telegram_send_success",
            "chat_id": chat_id,
            "message_id": result.get("result", {}).get("message_id")
        }
        print(json.dumps(log_entry))
        
        return result
        
    except httpx.HTTPStatusError as e:
        # HTTP РѕС€РёР±РєР° (4xx, 5xx)
        status_code = e.response.status_code
        response_body = e.response.text
        
        error_msg = f"Telegram API HTTP error: {status_code}"
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "telegram_send_http_error",
            "error": error_msg,
            "status_code": status_code,
            "response_body": response_body[:500],
            "chat_id": chat_id
        }
        print(json.dumps(log_entry))
        raise Exception(f"{error_msg} - {response_body[:200]}")
        
    except Exception as e:
        # Р”СЂСѓРіРёРµ РѕС€РёР±РєРё (timeout, network, etc)
        error_msg = f"Telegram API error: {str(e)}"
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "telegram_send_error",
            "error": error_msg,
            "error_type": type(e).__name__,
            "chat_id": chat_id
        }
        print(json.dumps(log_entry))
        raise Exception(error_msg)


def _answer_callback_query(callback_query_id: str, text: str) -> Dict[str, Any]:
    """
    РћС‚РІРµС‡Р°РµС‚ РЅР° callback query (СѓР±РёСЂР°РµС‚ loading indicator).
    """
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


def _format_status_label(order: Dict[str, Any]) -> str:
    """
    Р¤РѕСЂРјР°С‚РёСЂСѓРµС‚ СЃС‚Р°С‚СѓСЃ Р·Р°РєР°Р·Р° (1-РІ-1 РёР· n8n Format Recent Orders).
    """
    cdek_uuid = order.get("cdek_uuid")
    state = (order.get("state") or "").lower()
    
    if cdek_uuid:
        return "рџљљ РЅР°РєР»Р°РґРЅР°СЏ СЃРѕР·РґР°РЅР°"
    elif state == "paid":
        return "вњ… РѕРїР»Р°С‡РµРЅРѕ"
    else:
        return "вќ“ РЅРµРёР·РІРµСЃС‚РЅРѕ"


def _format_money(value: Any) -> str:
    """
    Р¤РѕСЂРјР°С‚РёСЂСѓРµС‚ СЃСѓРјРјСѓ (1-РІ-1 РёР· n8n).
    """
    num = float(value or 0)
    if num:
        return f"{num:,.0f} в‚Ѕ".replace(",", " ")
    return "вЂ”"


def _parse_jsonb(value: Any) -> Dict[str, Any]:
    """
    РџР°СЂСЃРёС‚ JSONB Р·РЅР°С‡РµРЅРёРµ (РјРѕР¶РµС‚ Р±С‹С‚СЊ dict, str РёР»Рё None).
    """
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


def execute_telegram_command(payload: Dict[str, Any], db_conn) -> Dict[str, Any]:
    """
    РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ telegram_command job.
    
    Payload РґРѕР»Р¶РµРЅ СЃРѕРґРµСЂР¶Р°С‚СЊ:
    - command: "/start" | "open" | "check" | "dialog"
    - chat_id: int
    - user_id: int (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ)
    - order_id: str (РґР»СЏ open/check)
    - callback_query_id: str (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ, РґР»СЏ callback)
    - text: str (РґР»СЏ dialog - С‚РµРєСЃС‚ РѕС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ)
    """
    command = payload.get("command")
    chat_id = payload.get("chat_id")
    callback_query_id = payload.get("callback_query_id")
    
    # Р›РѕРіРёСЂСѓРµРј РЅР°С‡Р°Р»Рѕ РѕР±СЂР°Р±РѕС‚РєРё
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event": "telegram_command_start",
        "command": command,
        "chat_id": chat_id,
        "payload_keys": list(payload.keys())
    }
    print(json.dumps(log_entry))
    
    if not chat_id:
        error_msg = "chat_id is required in payload"
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "telegram_command_error",
            "error": error_msg,
            "payload": payload
        }
        print(json.dumps(log_entry))
        raise Exception(error_msg)
    
    cursor = db_conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        if command == "/start":
            result = _handle_start_command(chat_id, cursor)
            log_entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "event": "telegram_command_completed",
                "command": command,
                "chat_id": chat_id,
                "result": result
            }
            print(json.dumps(log_entry))
            return result
        elif command == "open":
            order_id = payload.get("order_id")
            if not order_id:
                raise Exception("order_id is required for open command")
            return _handle_open_command(chat_id, order_id, callback_query_id, cursor)
        elif command == "check":
            order_id = payload.get("order_id")
            if not order_id:
                raise Exception("order_id is required for check command")
            return _handle_check_command(chat_id, order_id, callback_query_id, cursor)
        elif command == "dialog":
            text = payload.get("text", "").strip()
            return _handle_dialog_command(chat_id, text, cursor, db_conn)
        else:
            error_msg = f"Unknown command: {command}"
            log_entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "event": "telegram_command_error",
                "error": error_msg,
                "command": command
            }
            print(json.dumps(log_entry))
            raise Exception(error_msg)
    
    except Exception as e:
        # Р›РѕРіРёСЂСѓРµРј РѕС€РёР±РєСѓ РІС‹РїРѕР»РЅРµРЅРёСЏ
        error_msg = str(e)
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "telegram_command_error",
            "error": error_msg,
            "error_type": type(e).__name__,
            "command": command,
            "chat_id": chat_id
        }
        print(json.dumps(log_entry))
        raise
    
    finally:
        cursor.close()


def _handle_start_command(chat_id: int, cursor) -> Dict[str, Any]:
    """
    РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ РєРѕРјР°РЅРґСѓ /start в†’ РѕС‚РїСЂР°РІР»СЏРµС‚ "OK" (MVP).
    """
    # MVP: РїСЂРѕСЃС‚Рѕ РѕС‚РїСЂР°РІР»СЏРµРј "OK"
    _send_telegram_message(chat_id, "OK")
    
    return {
        "job_type": "telegram_command",
        "status": "completed",
        "command": "/start"
    }


def _handle_open_command(chat_id: int, order_id: str, callback_query_id: Optional[str], cursor) -> Dict[str, Any]:
    """
    РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ РєРѕРјР°РЅРґСѓ open:<order_id> в†’ РєР°СЂС‚РѕС‡РєР° Р·Р°РєР°Р·Р°.
    
    SQL: GET (1.2 РёР· forensic mapping)
    """
    try:
        order_uuid = UUID(order_id)
    except:
        raise Exception(f"Invalid order_id format: {order_id}")
    
    # SQL 1.2: SELECT * FROM order_ledger WHERE order_id = $1 LIMIT 1
    cursor.execute(
        """
        SELECT * FROM order_ledger
        WHERE order_id = %s
        LIMIT 1
        """,
        (order_uuid,)
    )
    
    order = cursor.fetchone()
    if not order:
        raise Exception(f"Order not found: {order_id}")
    
    # Р¤РѕСЂРјР°С‚РёСЂРѕРІР°РЅРёРµ РєР°СЂС‚РѕС‡РєРё (1-РІ-1 РёР· n8n Format Order Card)
    metadata = _parse_jsonb(order.get("metadata"))
    customer_data = _parse_jsonb(order.get("customer_data"))
    
    invoice_number = metadata.get("invoiceNumber") or order.get("insales_order_id") or str(order.get("order_id"))
    company_name = customer_data.get("companyName") or customer_data.get("name") or "РљР»РёРµРЅС‚"
    total_amount = metadata.get("totalAmount") or 0
    
    # РЎС‚Р°С‚СѓСЃ
    cdek_uuid = order.get("cdek_uuid")
    state = (order.get("state") or "").lower()
    
    if cdek_uuid:
        status = "рџљљ РќР°РєР»Р°РґРЅР°СЏ СЃРѕР·РґР°РЅР°"
    elif state == "paid":
        status = "вњ… РћРїР»Р°С‡РµРЅРѕ"
    else:
        status = "вќ“ РЎС‚Р°С‚СѓСЃ РЅРµРёР·РІРµСЃС‚РµРЅ"
    
    # Р¤РѕСЂРјРёСЂРѕРІР°РЅРёРµ С‚РµРєСЃС‚Р° РєР°СЂС‚РѕС‡РєРё
    lines = [
        f"РЎС‡С‘С‚: в„–{invoice_number}",
        f"РџРѕРєСѓРїР°С‚РµР»СЊ: {company_name}",
        f"РЎСѓРјРјР°: {_format_money(total_amount)}",
        f"РЎС‚Р°С‚СѓСЃ РѕРїР»Р°С‚С‹: {status}",
        f"РќР°РєР»Р°РґРЅР°СЏ: {cdek_uuid if cdek_uuid else 'РЅРµ СЃРѕР·РґР°РЅР°'}"
    ]
    
    text = "\n".join(lines)
    
    # Inline keyboard (1-РІ-1 РёР· n8n)
    keyboard = [
        [{"text": "рџ”„ РџСЂРѕРІРµСЂРёС‚СЊ РѕРїР»Р°С‚Сѓ", "callback_data": f"check:{order_id}"}]
    ]
    
    if not cdek_uuid:
        keyboard.append([{"text": "рџљљ РЎРѕР·РґР°С‚СЊ РЅР°РєР»Р°РґРЅСѓСЋ", "callback_data": f"ship:{order_id}"}])
    else:
        keyboard.append([{"text": "рџљ« РќР°РєР»Р°РґРЅР°СЏ СЃРѕР·РґР°РЅР°", "callback_data": "noop"}])
    
    keyboard.append([{"text": "в—ЂпёЏ РќР°Р·Р°Рґ", "callback_data": "back:list"}])
    
    reply_markup = {"inline_keyboard": keyboard}
    
    # РћС‚РїСЂР°РІРєР° СЃРѕРѕР±С‰РµРЅРёСЏ
    _send_telegram_message(chat_id, text, reply_markup)
    
    # РћС‚РІРµС‚ РЅР° callback query
    if callback_query_id:
        _answer_callback_query(callback_query_id, "РљР°СЂС‚РѕС‡РєР° РѕС‚РїСЂР°РІР»РµРЅР°")
    
    return {
        "job_type": "telegram_command",
        "status": "completed",
        "command": "open",
        "order_id": order_id
    }


def _handle_check_command(chat_id: int, order_id: str, callback_query_id: Optional[str], cursor) -> Dict[str, Any]:
    """
    РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ РєРѕРјР°РЅРґСѓ check:<order_id> в†’ РїСЂРѕРІРµСЂРєР° СЃС‚Р°С‚СѓСЃР°.
    
    SQL: GET (1.2 РёР· forensic mapping)
    Р’РђР–РќРћ: РџСЂРѕРІРµСЂРєР° С‚РѕР»СЊРєРѕ РїРѕ Ledger, Р±РµР· T-Bank API.
    """
    try:
        order_uuid = UUID(order_id)
    except:
        raise Exception(f"Invalid order_id format: {order_id}")
    
    # SQL 1.2: SELECT * FROM order_ledger WHERE order_id = $1 LIMIT 1
    cursor.execute(
        """
        SELECT * FROM order_ledger
        WHERE order_id = %s
        LIMIT 1
        """,
        (order_uuid,)
    )
    
    order = cursor.fetchone()
    if not order:
        raise Exception(f"Order not found: {order_id}")
    
    # Р¤РѕСЂРјР°С‚РёСЂРѕРІР°РЅРёРµ СЃС‚Р°С‚СѓСЃР° (1-РІ-1 РёР· n8n Format Status Message)
    metadata = _parse_jsonb(order.get("metadata"))
    invoice_number = metadata.get("invoiceNumber") or order.get("insales_order_id") or str(order.get("order_id"))
    
    cdek_uuid = order.get("cdek_uuid")
    state = (order.get("state") or "").lower()
    
    if cdek_uuid:
        status = "рџљљ РќР°РєР»Р°РґРЅР°СЏ СЃРѕР·РґР°РЅР°"
    elif state == "paid":
        status = "вњ… РћРїР»Р°С‡РµРЅРѕ"
    else:
        status = "вќ“ РЎС‚Р°С‚СѓСЃ РЅРµРёР·РІРµСЃС‚РµРЅ"
    
    text = f"РЎС‚Р°С‚СѓСЃ РѕРїР»Р°С‚С‹ РґР»СЏ СЃС‡С‘С‚Р° в„–{invoice_number}: {status}"
    
    # РћС‚РїСЂР°РІРєР° СЃРѕРѕР±С‰РµРЅРёСЏ
    _send_telegram_message(chat_id, text)
    
    # РћС‚РІРµС‚ РЅР° callback query
    if callback_query_id:
        _answer_callback_query(callback_query_id, "РЎС‚Р°С‚СѓСЃ РѕС‚РїСЂР°РІР»РµРЅ")
    
    return {
        "job_type": "telegram_command",
        "status": "completed",
        "command": "check",
        "order_id": order_id
    }


def _handle_dialog_command(chat_id: int, text: str, cursor, db_conn) -> Dict[str, Any]:
    """
    РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ РґРёР°Р»РѕРі (С‚РµРєСЃС‚ РѕС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РїСЂРё Р°РєС‚РёРІРЅРѕРј dialog_context).
    
    SQL: FIND_DIALOG (1.6 РёР· forensic mapping)
    Р›РѕРіРёРєР°: 1-РІ-1 РёР· n8n Process Dialog Input
    """
    if not text:
        raise Exception("Text is required for dialog command")
    
    # SQL 1.6: SELECT * FROM order_ledger WHERE metadata->'dialog_context'->>'chat_id' = $1 LIMIT 1
    cursor.execute(
        """
        SELECT * FROM order_ledger
        WHERE metadata->'dialog_context'->>'chat_id' = %s
        LIMIT 1
        """,
        (str(chat_id),)
    )
    
    order = cursor.fetchone()
    if not order:
        # РќРµС‚ Р°РєС‚РёРІРЅРѕРіРѕ РґРёР°Р»РѕРіР° - РёРіРЅРѕСЂРёСЂСѓРµРј
        return {
            "job_type": "telegram_command",
            "status": "completed",
            "command": "dialog",
            "message": "No active dialog found"
        }
    
    # РџР°СЂСЃРёРЅРі РґР°РЅРЅС‹С… (1-РІ-1 РёР· n8n Process Dialog Input)
    metadata = _parse_jsonb(order.get("metadata"))
    customer_data = _parse_jsonb(order.get("customer_data"))
    delivery_data = _parse_jsonb(order.get("delivery_data"))
    
    dialog_context = metadata.get("dialog_context")
    if not dialog_context:
        return {
            "job_type": "telegram_command",
            "status": "completed",
            "command": "dialog",
            "message": "Dialog context not found in metadata"
        }
    
    missing_field = dialog_context.get("missing_field")
    if not missing_field:
        return {
            "job_type": "telegram_command",
            "status": "completed",
            "command": "dialog",
            "message": "Missing field not found in dialog context"
        }
    
    # РЎРѕС…СЂР°РЅРµРЅРёРµ phone/email (1-РІ-1 РёР· n8n)
    if missing_field == "phone":
        customer_data["phone"] = text
    elif missing_field == "email":
        customer_data["email"] = text
    else:
        raise Exception(f"Unknown missing_field: {missing_field}")
    
    # РЈРґР°Р»РµРЅРёРµ dialog_context (1-РІ-1 РёР· n8n)
    updated_metadata = metadata.copy()
    del updated_metadata["dialog_context"]
    
    # SQL 1.1: UPSERT (РѕР±РЅРѕРІР»РµРЅРёРµ customer_data Рё metadata)
    order_uuid = UUID(str(order.get("order_id")))
    
    cursor.execute(
        """
        UPDATE order_ledger
        SET customer_data = %s::jsonb,
            metadata = %s::jsonb,
            updated_at = NOW()
        WHERE order_id = %s
        RETURNING *
        """,
        (json.dumps(customer_data), json.dumps(updated_metadata), order_uuid)
    )
    
    updated_order = cursor.fetchone()
    db_conn.commit()
    
    # РЎРѕР·РґР°РЅРёРµ РЅРѕРІРѕРіРѕ job РґР»СЏ cdek_shipment (РїРѕРІС‚РѕСЂРЅР°СЏ РїРѕРїС‹С‚РєР°)
    cursor.execute(
        """
        INSERT INTO job_queue (id, job_type, payload, status, idempotency_key)
        VALUES (gen_random_uuid(), %s, %s, 'pending', %s)
        RETURNING id
        """,
        (
            "cdek_shipment",
            json.dumps({
                "order_id": str(order_uuid),
                "initiator_chat_id": chat_id,
                "initiator_user_id": dialog_context.get("user_id")
            }),
            f"cdek_shipment:{order_uuid}"
        )
    )
    
    new_job_id = cursor.fetchone()[0]
    db_conn.commit()
    
    return {
        "job_type": "telegram_command",
        "status": "completed",
        "command": "dialog",
        "missing_field": missing_field,
        "cdek_shipment_job_id": str(new_job_id)
    }



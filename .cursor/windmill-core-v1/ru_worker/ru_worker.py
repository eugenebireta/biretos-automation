"""
RFQ Execution Core Business v1 - RU Worker
Executor РґР»СЏ РІС‹РїРѕР»РЅРµРЅРёСЏ RU-side Р±РёР·РЅРµСЃ-Р»РѕРіРёРєРё (test_job, rfq_v1_from_ocr)

Р’РђР–РќРћ: Р­С‚Рѕ polling executor РЅР° RU-VPS, РЅРµ РїСѓР±Р»РёС‡РЅС‹Р№ СЃРµСЂРІРёСЃ.

EXECUTION NODE: RU VPS (77.233.222.214) - Р•Р”РРќРЎРўР’Р•РќРќР«Р™ execution node.
Р’СЃРµ job_types РѕР±СЂР°Р±Р°С‚С‹РІР°СЋС‚СЃСЏ РўРћР›Р¬РљРћ РЅР° RU VPS:
- telegram_update в†’ telegram_command в†’ sendMessage
- tbank_invoice_paid в†’ FSM v2
- cdek_shipment_status в†’ order_event
- order_event в†’ FSM v2
- rfq_v1_from_ocr в†’ RFQ pipeline
- test_job в†’ simple test

USA VPS РќР• РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ РґР»СЏ execution.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from uuid import uuid4, UUID

import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import ValidationError
from psycopg2.pool import SimpleConnectionPool
import requests

from config import get_config

# Compatibility shim:
# when this file is imported as top-level module "ru_worker" (not package),
# expose package path so imports like ru_worker.shopware_idempotency keep working.
if __name__ == "ru_worker":
    __path__ = [os.path.dirname(__file__)]  # type: ignore[name-defined]

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

_CONFIG = get_config()

# Debug logging path (platform-safe, configurable)
DEBUG_LOG_PATH = Path(
    os.getenv(
        "DEBUG_LOG_PATH",
        str(Path(__file__).resolve().parents[1] / "logs" / "debug.log"),
    )
)

def debug_log(hypothesis_id: str, location: str, message: str, data: dict):
    """РљРѕРјРїР°РєС‚РЅР°СЏ С„СѓРЅРєС†РёСЏ РґР»СЏ Р·Р°РїРёСЃРё debug Р»РѕРіРѕРІ"""
    try:
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
        pass  # РРіРЅРѕСЂРёСЂСѓРµРј РѕС€РёР±РєРё Р»РѕРіРёСЂРѕРІР°РЅРёСЏ

# РРјРїРѕСЂС‚С‹ РґР»СЏ RFQ pipeline
from rfq_parser import parse_rfq_deterministic, merge_llm_results
from llm_client import parse_rfq_with_llm
from rfq_converter import convert_to_canonical  # Phase 1c: Shadow mode
from price_adapter import enrich_prices  # ADR-007: Soft Fail price enrichment
from rfq_idempotency import (
    TRACE_ID_PAYLOAD_KEY,
    RFQ_ID_PAYLOAD_KEY,
    resolve_execution_mode,
    insert_rfq_idempotent,
    insert_price_log,
)

# РРјРїРѕСЂС‚ FSM v2
from fsm_v2 import Event, LedgerRecord, FSMResult, fsm_v2_process_event
from domain.availability_service import release_reservations_for_order_atomic
from domain.payment_service import record_payment_transaction_atomic

# РРјРїРѕСЂС‚ CDEK Order Mapper
from cdek_order_mapper import map_cdek_to_order_event

# РРјРїРѕСЂС‚ CDM adapters
from cdm_adapters import order_event_input_to_fsm_event
from domain.cdm.event import OrderEventInput

# РРјРїРѕСЂС‚ Side-Effect Workers
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'side_effects'))
from telegram_command_worker import execute_telegram_command
from cdek_shipment_worker import execute_cdek_shipment
from insales_paid_worker import execute_insales_paid_sync
from invoice_worker import execute_invoice_create
from side_effects.shopware_product_worker import execute_shopware_product_sync
from shopware_order_handoff import execute_shopware_order_handoff

# РќРѕРІС‹Рµ РјРѕРґСѓР»СЊРЅС‹Рµ РєРѕРјРїРѕРЅРµРЅС‚С‹
from telegram_router import route_update, extract_chat_id_from_update
from dispatch_action import dispatch_action
from policy_hash import current_policy_context, upsert_config_snapshot
try:
    from idempotency import sweep_expired_locks
except ImportError:
    from .idempotency import sweep_expired_locks  # type: ignore

# РљРѕРЅС„РёРіСѓСЂР°С†РёСЏ PostgreSQL
POSTGRES_HOST = _CONFIG.postgres_host or "localhost"
POSTGRES_PORT = _CONFIG.postgres_port or 5432
POSTGRES_DB = _CONFIG.postgres_db or "biretos_automation"
POSTGRES_USER = _CONFIG.postgres_user or "biretos_user"
POSTGRES_PASSWORD = _CONFIG.postgres_password

# РљРѕРЅС„РёРіСѓСЂР°С†РёСЏ worker
POLL_INTERVAL = _CONFIG.ru_worker_poll_interval or 5  # СЃРµРєСѓРЅРґС‹
LLM_ENABLED_DEFAULT = bool(_CONFIG.llm_enabled_default)
DB_POOL_MIN = max(1, int(os.getenv("RU_WORKER_DB_POOL_MIN", "1")))
DB_POOL_MAX = max(DB_POOL_MIN, int(os.getenv("RU_WORKER_DB_POOL_MAX", "5")))
ZOMBIE_TIMEOUT_MINUTES = max(1, int(os.getenv("RU_WORKER_ZOMBIE_TIMEOUT_MINUTES", "10")))
ZOMBIE_SWEEP_EVERY_CYCLES = max(1, int(os.getenv("RU_WORKER_ZOMBIE_SWEEP_EVERY_CYCLES", "12")))

# Telegram API
TELEGRAM_BOT_TOKEN = _CONFIG.telegram_bot_token
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# State storage
STATE_TABLE_INITIALIZED = False
_DB_POOL: Optional[SimpleConnectionPool] = None
_JOB_QUEUE_HAS_TRACE_ID: Optional[bool] = None
TERMINAL_FAILURE_STATES = {"failed", "cancelled", "quarantine_expired", "human_decision_timeout"}


def log_event(event: str, data: Dict[str, Any]) -> None:
    """Structured logging helper."""
    log_entry = {
        "event": event,
        "timestamp": time.time(),
        **data
    }
    print(json.dumps(log_entry), flush=True)


def ensure_state_table(conn) -> None:
    """РЎРѕР·РґР°С‘С‚ С‚Р°Р±Р»РёС†Сѓ РґР»СЏ key-value state, РµСЃР»Рё РµС‘ РµС‰С‘ РЅРµС‚."""
    global STATE_TABLE_INITIALIZED
    if STATE_TABLE_INITIALIZED:
        return
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS wm_state (
            key TEXT PRIMARY KEY,
            value JSONB,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    conn.commit()
    STATE_TABLE_INITIALIZED = True


def get_state(conn, key: str) -> Optional[Dict[str, Any]]:
    """РџРѕР»СѓС‡Р°РµС‚ Р·РЅР°С‡РµРЅРёРµ state РїРѕ РєР»СЋС‡Сѓ."""
    ensure_state_table(conn)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM wm_state WHERE key = %s", (key,))
    row = cursor.fetchone()
    return row[0] if row else None


def set_state(conn, key: str, value: Dict[str, Any]) -> None:
    """РЈСЃС‚Р°РЅР°РІР»РёРІР°РµС‚ Р·РЅР°С‡РµРЅРёРµ state (upsert)."""
    ensure_state_table(conn)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO wm_state (key, value, updated_at)
        VALUES (%s, %s::jsonb, NOW())
        ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value,
            updated_at = NOW()
        """,
        (key, json.dumps(value, ensure_ascii=False))
    )
    conn.commit()


def delete_state(conn, key: str) -> None:
    """РЈРґР°Р»СЏРµС‚ Р·Р°РїРёСЃСЊ state."""
    ensure_state_table(conn)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM wm_state WHERE key = %s", (key,))
    conn.commit()


def send_telegram_message(chat_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> bool:
    """РћС‚РїСЂР°РІР»СЏРµС‚ СЃРѕРѕР±С‰РµРЅРёРµ РІ Telegram."""
    # #region agent log
    debug_log("E", "ru_worker.py:143", "send_telegram_message called", {"chat_id": chat_id, "text_length": len(text), "has_token": bool(TELEGRAM_API_URL)})
    # #endregion
    
    if not TELEGRAM_API_URL:
        log_event("telegram_send_error", {
            "error": "TELEGRAM_BOT_TOKEN not configured",
            "chat_id": chat_id
        })
        # #region agent log
        debug_log("E", "ru_worker.py:150", "TELEGRAM_BOT_TOKEN not configured", {"chat_id": chat_id})
        # #endregion
        return False
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        response = requests.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        
        # РљР РРўРР§РќРћ: РџСЂРѕРІРµСЂСЏРµРј РїРѕР»Рµ "ok" РІ JSON РѕС‚РІРµС‚Рµ Telegram API
        # Telegram РјРѕР¶РµС‚ РІРµСЂРЅСѓС‚СЊ HTTP 200, РЅРѕ СЃ {"ok": false, "error_code": 400, ...}
        result = response.json()
        if not result.get("ok", False):
            # #region agent log
            debug_log("E", "ru_worker.py:168", "Telegram API returned ok=false", {"chat_id": chat_id, "error_code": result.get("error_code"), "description": result.get("description", "")[:100]})
            # #endregion
            error_code = result.get("error_code", "unknown")
            error_description = result.get("description", "Unknown error")
            error_msg = f"Telegram API error {error_code}: {error_description}"
            log_event("telegram_send_error", {
                "error": error_msg,
                "chat_id": chat_id,
                "error_code": error_code,
                "response": result
            })
            return False
        
        log_event("telegram_message_sent", {
            "chat_id": chat_id,
            "text_length": len(text),
            "has_reply_markup": bool(reply_markup),
            "message_id": result.get("result", {}).get("message_id")
        })
        # #region agent log
        debug_log("E", "ru_worker.py:186", "Message sent successfully", {"chat_id": chat_id, "message_id": result.get("result", {}).get("message_id")})
        # #endregion
        return True
    except requests.RequestException as e:
        error_details = {
            "error": str(e),
            "chat_id": chat_id
        }
        # Р”РѕР±Р°РІР»СЏРµРј РґРµС‚Р°Р»Рё РѕС‚РІРµС‚Р°, РµСЃР»Рё РµСЃС‚СЊ
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_details["status_code"] = e.response.status_code
                error_details["response_text"] = e.response.text[:200]
            except:
                pass
        log_event("telegram_send_error", error_details)
        return False


def answer_callback_query(callback_query_id: str, text: str = "", show_alert: bool = False) -> bool:
    """РћС‚РІРµС‡Р°РµС‚ РЅР° callback_query, С‡С‚РѕР±С‹ Telegram РЅРµ РїРѕРєР°Р·С‹РІР°Р» СЃРїРёРЅРЅРµСЂ."""
    if not TELEGRAM_API_URL:
        return False
    try:
        response = requests.post(
            f"{TELEGRAM_API_URL}/answerCallbackQuery",
            json={
                "callback_query_id": callback_query_id,
                "text": text,
                "show_alert": show_alert
            },
            timeout=5
        )
        response.raise_for_status()
        log_event("telegram_callback_acked", {
            "callback_query_id": callback_query_id
        })
        return True
    except requests.RequestException as e:
        log_event("telegram_callback_ack_error", {
            "callback_query_id": callback_query_id,
            "error": str(e)
        })
        return False


def extract_tracking_from_result(result: Dict[str, Any]) -> Optional[str]:
    """РР·РІР»РµРєР°РµС‚ tracking РЅРѕРјРµСЂ РёР· СЂРµР·СѓР»СЊС‚Р°С‚Р° dispatch_action."""
    if not result:
        return None
    response = result.get("result") or result.get("response")
    if not response and "result" in result:
        response = result.get("result", {}).get("response")
    if not isinstance(response, dict):
        return None
    entity = response.get("entity", {})
    if isinstance(entity, dict):
        tracking = entity.get("uuid") or entity.get("barcode")
        if tracking:
            return tracking
    requests_list = response.get("requests")
    if isinstance(requests_list, list) and requests_list:
        first = requests_list[0]
        if isinstance(first, dict):
            tracking = first.get("request_uuid") or first.get("uuid")
            if tracking:
                return tracking
    return None


def format_action_result(action: Dict[str, Any], result: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Р¤РѕСЂРјР°С‚РёСЂСѓРµС‚ СЂРµР·СѓР»СЊС‚Р°С‚ action РґР»СЏ РѕС‚РїСЂР°РІРєРё РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ."""
    action_type = action.get("action_type")
    status = result.get("status")

    if action_type == "ship_paid":
        if status == "success":
            tracking = extract_tracking_from_result(result) or result.get("tracking_number") or "N/A"
            return (f"вњ… РќР°РєР»Р°РґРЅР°СЏ СЃРѕР·РґР°РЅР°!\nРўСЂРµРє-РЅРѕРјРµСЂ: {tracking}", None)
        elif status == "duplicate":
            tracking = result.get("tracking", "N/A")
            return (f"вњ… РќР°РєР»Р°РґРЅР°СЏ СѓР¶Рµ СЃРѕР·РґР°РЅР°!\nРўСЂРµРє-РЅРѕРјРµСЂ: {tracking}", None)
        elif status == "not_paid":
            return ("вќЊ РЎС‡С‘С‚ РЅРµ РѕРїР»Р°С‡РµРЅ", None)
        else:
            error = result.get("error", "Unknown error")
            return (f"вќЊ РћС€РёР±РєР°: {error}", None)

    if action_type == "auto_ship_all_paid":
        if status == "success":
            processed = result.get("processed_count", 0)
            success = result.get("success_count", 0)
            lines = [
                "рџљЂ РђРІС‚РѕРјР°С‚РёС‡РµСЃРєР°СЏ РѕР±СЂР°Р±РѕС‚РєР° Р·Р°РІРµСЂС€РµРЅР°",
                "",
                f"рџ“Љ РћР±СЂР°Р±РѕС‚Р°РЅРѕ: {processed} СЃС‡РµС‚РѕРІ",
                f"вњ… РЈСЃРїРµС€РЅРѕ: {success}"
            ]
            results = result.get("results", [])
            success_items = [r for r in results if r.get("status") == "success"]
            if success_items:
                lines.append("")
                lines.append("рџ“¦ РЎРѕР·РґР°РЅРЅС‹Рµ РЅР°РєР»Р°РґРЅС‹Рµ:")
                for item in success_items[:10]:
                    lines.append(f"  вњ“ {item.get('invoice_id')}: {item.get('tracking', 'N/A')}")
            errors = [r for r in results if r.get("status") == "error"]
            if errors:
                lines.append("")
                lines.append(f"вќЊ РћС€РёР±РєРё: {len(errors)}")
                for item in errors[:5]:
                    error_msg = item.get("error", "Unknown error")
                    if len(error_msg) > 50:
                        error_msg = error_msg[:47] + "..."
                    lines.append(f"  вњ— {item.get('invoice_id')}: {error_msg}")
            if len(results) > 10:
                lines.append("")
                lines.append(f"... Рё РµС‰Рµ {len(results) - 10} СЃС‡РµС‚РѕРІ")
            return ("\n".join(lines), None)
        else:
            error = result.get("error", "Unknown error")
            return (f"вќЊ РћС€РёР±РєР°: {error}", None)

    if action_type == "tbank_invoices_list":
        if status == "success":
            invoices = result.get("invoices", [])
            if not invoices:
                return ("рџ§ѕ РџРѕСЃР»РµРґРЅРёРµ СЃС‡РµС‚Р°\n\nРЎС‡РµС‚Р° РЅРµ РЅР°Р№РґРµРЅС‹", None)
            lines = ["рџ§ѕ РџРѕСЃР»РµРґРЅРёРµ СЃС‡РµС‚Р°"]
            inline_keyboard = []
            for inv in invoices:
                invoice_id = inv.get("invoice_id", "N/A")
                inv_status = inv.get("status", "unknown")
                if inv_status == "paid":
                    status_text = "вњ… РћРїР»Р°С‡РµРЅ"
                    inline_keyboard.append([{
                        "text": "рџ“¦ РЎРѕР·РґР°С‚СЊ РЅР°РєР»Р°РґРЅСѓСЋ",
                        "callback_data": f"ship_paid:{invoice_id}"
                    }])
                else:
                    status_text = "вЏі РќРµ РѕРїР»Р°С‡РµРЅ"
                lines.append(f"{invoice_id} вЂ” {status_text}")
            reply_markup = {"inline_keyboard": inline_keyboard} if inline_keyboard else None
            return ("\n".join(lines), reply_markup)
        else:
            # РРЎРџР РђР’Р›Р•РќРР•: Р’СЃРµРіРґР° РІРѕР·РІСЂР°С‰Р°РµРј СЃРѕРѕР±С‰РµРЅРёРµ РѕР± РѕС€РёР±РєРµ СЃ РґРµС‚Р°Р»СЏРјРё
            error = result.get("error", "Unknown error")
            # РЎРѕРєСЂР°С‰Р°РµРј РґР»РёРЅРЅС‹Рµ СЃРѕРѕР±С‰РµРЅРёСЏ РѕР± РѕС€РёР±РєР°С…
            if len(error) > 200:
                error = error[:197] + "..."
            return (f"вќЊ РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ СЃС‡РµС‚РѕРІ: {error}", None)

    if action_type == "tbank_invoice_status":
        if status == "success":
            invoice_status = result.get("result", {}).get("result_status") or result.get("result_status", "unknown")
            invoice_id = action.get("payload", {}).get("invoice_id", "N/A")
            status_emoji = "вњ…" if invoice_status == "paid" else "вЏі"
            return (f"{status_emoji} РЎС‡С‘С‚ {invoice_id}: {invoice_status}", None)
        else:
            error = result.get("error", "Unknown error")
            return (f"вќЊ РћС€РёР±РєР°: {error}", None)

    if status == "success":
        return ("вњ… Р’С‹РїРѕР»РЅРµРЅРѕ", None)
    elif status == "error":
        error = result.get("error", "Unknown error")
        return (f"вќЊ РћС€РёР±РєР°: {error}", None)
    elif status == "duplicate":
        return ("в„№пёЏ Р”РµР№СЃС‚РІРёРµ СѓР¶Рµ РІС‹РїРѕР»РЅСЏРµС‚СЃСЏ", None)
    else:
        return (f"в„№пёЏ РЎС‚Р°С‚СѓСЃ: {status}", None)


def handle_router_action(action: Dict[str, Any], db_conn) -> Dict[str, Any]:
    """
    Р’С‹РїРѕР»РЅСЏРµС‚ action, РІРѕР·РІСЂР°С‰РµРЅРЅС‹Р№ telegram_router.
    РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ Р±РёР·РЅРµСЃ-РёРґРµРјРїРѕС‚РµРЅС‚РЅРѕСЃС‚СЊ Рё С„РѕСЂРјР°С‚РёСЂСѓРµС‚ РѕС‚РІРµС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ.
    """
    action_type = action.get("action_type")
    metadata = action.get("metadata", {})
    chat_id = metadata.get("chat_id")
    user_id = metadata.get("user_id")
    result: Dict[str, Any] = {"status": "noop"}

    try:
        if action_type == "ship_paid":
            invoice_id = action.get("payload", {}).get("invoice_id")
            if not invoice_id:
                log_event("router_action_error", {
                    "action_type": action_type,
                    "error": "invoice_id missing"
                })
                if chat_id:
                    send_telegram_message(chat_id, "вќЊ РћС€РёР±РєР°: invoice_id РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚")
                return {
                    "status": "error",
                    "error": "invoice_id missing"
                }
            result = dispatch_action(action, db_conn=db_conn, trace_id=metadata.get("trace_id"))

        else:
            result = dispatch_action(action, db_conn=db_conn, trace_id=metadata.get("trace_id"))

        if result.get("status") == "pending_approval":
            try:
                from governance_trigger import handle_pending_approval

                trigger_result = handle_pending_approval(
                    action=action,
                    pending_result=result,
                    db_conn=db_conn,
                    trace_id=metadata.get("trace_id"),
                )
                result["governance"] = trigger_result
            except Exception as e:
                error_msg = str(e)
                log_event(
                    "governance_trigger_failed",
                    {
                        "action_type": action_type,
                        "error": error_msg,
                        "trace_id": metadata.get("trace_id"),
                    },
                )
                result["governance_error"] = error_msg
                if chat_id:
                    send_telegram_message(
                        chat_id,
                        "Внимание: действие требует одобрения, но автоматическое создание заявки не удалось. Обратитесь к администратору.",
                    )

        # РРЎРџР РђР’Р›Р•РќРР•: Р’СЃРµРіРґР° С„РѕСЂРјР°С‚РёСЂСѓРµРј Рё РѕС‚РїСЂР°РІР»СЏРµРј СЂРµР·СѓР»СЊС‚Р°С‚
        message_text, reply_markup = format_action_result(action, result)
        if message_text and chat_id:
            send_telegram_message(chat_id, message_text, reply_markup)
        elif chat_id and result.get("status") == "error":
            # Р•СЃР»Рё format_action_result РЅРµ РІРµСЂРЅСѓР» С‚РµРєСЃС‚, РЅРѕ РµСЃС‚СЊ РѕС€РёР±РєР° - РѕС‚РїСЂР°РІР»СЏРµРј РѕС€РёР±РєСѓ
            error_msg = result.get("error", "Unknown error")
            send_telegram_message(chat_id, f"вќЊ РћС€РёР±РєР°: {error_msg[:200]}")

        return result
    except Exception as e:
        # РРЎРџР РђР’Р›Р•РќРР•: РћР±СЂР°Р±РѕС‚РєР° РёСЃРєР»СЋС‡РµРЅРёР№
        error_msg = str(e)
        log_event("router_action_exception", {
            "action_type": action_type,
            "error": error_msg
        })
        if chat_id:
            try:
                send_telegram_message(chat_id, f"вќЊ РћС€РёР±РєР° РѕР±СЂР°Р±РѕС‚РєРё: {error_msg[:200]}")
            except:
                pass
        return {
            "status": "error",
            "error": error_msg
        }


def get_db_pool() -> SimpleConnectionPool:
    """Lazy-init shared PostgreSQL pool for RU worker."""
    global _DB_POOL
    if _DB_POOL is None:
        _DB_POOL = SimpleConnectionPool(
            minconn=DB_POOL_MIN,
            maxconn=DB_POOL_MAX,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
        )
    return _DB_POOL


def get_db_connection():
    """Р‘РµСЂРµС‚ РїРѕРґРєР»СЋС‡РµРЅРёРµ РёР· shared pool."""
    return get_db_pool().getconn()


def return_db_connection(conn) -> None:
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ РїРѕРґРєР»СЋС‡РµРЅРёРµ РІ pool c rollback РґР»СЏ clean state."""
    if conn is None:
        return
    pool = _DB_POOL
    if pool is None:
        return
    try:
        conn.rollback()
        pool.putconn(conn)
    except Exception:
        try:
            pool.putconn(conn, close=True)
        except Exception:
            pass


def ensure_policy_snapshot(db_conn) -> Optional[str]:
    """Persist current policy snapshot (deduplicated by policy_hash)."""
    try:
        context = current_policy_context(_CONFIG)
        policy_hash = context["policy_hash"]
        upsert_config_snapshot(db_conn, policy_hash, context["policy_inputs"])
        db_conn.commit()
        log_event("policy_snapshot_ready", {"policy_hash": policy_hash})
        return policy_hash
    except Exception as e:
        db_conn.rollback()
        log_event("policy_snapshot_error", {"error": str(e)})
        return None


def _job_queue_has_trace_id(db_conn) -> bool:
    global _JOB_QUEUE_HAS_TRACE_ID
    if _JOB_QUEUE_HAS_TRACE_ID is not None:
        return _JOB_QUEUE_HAS_TRACE_ID
    cursor = db_conn.cursor()
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


def enqueue_job_with_trace(
    db_conn,
    job_type: str,
    payload: Dict[str, Any],
    idempotency_key: str,
    trace_id: Optional[str],
) -> UUID:
    """Enqueue helper with backward-compatible trace_id insert."""
    cursor = db_conn.cursor()
    has_trace = _job_queue_has_trace_id(db_conn)
    try:
        if has_trace:
            cursor.execute(
                """
                INSERT INTO job_queue (id, job_type, payload, status, idempotency_key, trace_id)
                VALUES (gen_random_uuid(), %s, %s, 'pending', %s, %s::uuid)
                RETURNING id
                """,
                (job_type, json.dumps(payload, ensure_ascii=False), idempotency_key, trace_id),
            )
        else:
            cursor.execute(
                """
                INSERT INTO job_queue (id, job_type, payload, status, idempotency_key)
                VALUES (gen_random_uuid(), %s, %s, 'pending', %s)
                RETURNING id
                """,
                (job_type, json.dumps(payload, ensure_ascii=False), idempotency_key),
            )
        return cursor.fetchone()[0]
    finally:
        cursor.close()


def _release_reservations_safe(
    db_conn,
    *,
    order_id: Optional[UUID],
    trace_id: Optional[str],
    reason: str,
) -> Dict[str, Any]:
    if order_id is None:
        return {"action": "noop", "released_count": 0}
    try:
        result = release_reservations_for_order_atomic(
            db_conn,
            order_id=order_id,
            trace_id=trace_id,
            reason=reason,
        )
        log_event(
            "reservation_release_executed",
            {
                "order_id": str(order_id),
                "trace_id": trace_id,
                "reason": reason,
                "result": result,
            },
        )
        return result
    except Exception as e:
        log_event(
            "reservation_release_failed",
            {
                "order_id": str(order_id),
                "trace_id": trace_id,
                "reason": reason,
                "error": str(e),
            },
        )
        raise


def _resolve_order_id_for_cleanup(job_type: str, payload: Dict[str, Any], db_conn) -> Optional[UUID]:
    if job_type == "governance_case_create":
        return None  # H2: governance jobs must never release reservations on failure.
    order_id_value = payload.get("order_id")
    if order_id_value:
        try:
            return UUID(str(order_id_value))
        except Exception:
            return None

    if job_type == "tbank_invoice_paid":
        invoice_id = payload.get("invoice_id")
        if not invoice_id:
            return None
        cursor = db_conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute(
                """
                SELECT order_id
                FROM order_ledger
                WHERE tbank_invoice_id = %s
                LIMIT 1
                """,
                (invoice_id,),
            )
            row = cursor.fetchone()
            if row and row.get("order_id"):
                return UUID(str(row["order_id"]))
            return None
        finally:
            cursor.close()

    return None


def legacy_maintenance_only(func):
    """Marker: legacy handler frozen for maintenance-only changes."""
    setattr(func, "__legacy_maintenance_only__", True)
    return func


def execute_test_job(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Р’С‹РїРѕР»РЅСЏРµС‚ РїСЂРѕСЃС‚СѓСЋ С‚РµСЃС‚РѕРІСѓСЋ Р·Р°РґР°С‡Сѓ"""
    time.sleep(1)  # Р¤РёРєС‚РёРІРЅРѕРµ РІС‹РїРѕР»РЅРµРЅРёРµ
    return {
        "job_type": "test_job",
        "message": "Test job completed",
        "payload": payload
    }


@legacy_maintenance_only
def execute_tbank_invoice_paid(payload: Dict[str, Any], db_conn, trace_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Р’С‹РїРѕР»РЅСЏРµС‚ РѕР±СЂР°Р±РѕС‚РєСѓ T-Bank webhook INVOICE_PAID С‡РµСЂРµР· FSM v2:
    1. Lookup order_ledger РїРѕ tbank_invoice_id
    2. Р•СЃР»Рё РЅРµ РЅР°Р№РґРµРЅ - Р»РѕРіРёСЂСѓРµРј РѕС€РёР±РєСѓ, job completed
    3. Р•СЃР»Рё РЅР°Р№РґРµРЅ - РІС‹Р·С‹РІР°РµРј FSM v2 РґР»СЏ РѕРїСЂРµРґРµР»РµРЅРёСЏ РёР·РјРµРЅРµРЅРёР№
    4. РџСЂРёРјРµРЅСЏРµРј РёР·РјРµРЅРµРЅРёСЏ Рє Ledger
    """
    invoice_id = payload.get("invoice_id")
    invoice_number = payload.get("invoice_number")
    paid_at = payload.get("paid_at", datetime.utcnow().isoformat() + "Z")
    
    if not invoice_id:
        raise Exception("invoice_id is required in payload")
    
    cursor = db_conn.cursor(cursor_factory=RealDictCursor)
    
    # Lookup РІ order_ledger
    cursor.execute(
        """
        SELECT * FROM order_ledger
        WHERE tbank_invoice_id = %s
        LIMIT 1
        FOR UPDATE
        """,
        (invoice_id,)
    )
    
    record = cursor.fetchone()
    
    if not record:
        # Р—Р°РїРёСЃСЊ РЅРµ РЅР°Р№РґРµРЅР° - Р»РѕРіРёСЂСѓРµРј РѕС€РёР±РєСѓ
        error_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": "ledger_lookup",
            "message": "Ledger record not found for invoice",
            "context": {
                "invoice_id": invoice_id,
                "invoice_number": invoice_number,
                "paid_at": paid_at
            }
        }
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "tbank_invoice_paid_ledger_not_found",
            "invoice_id": invoice_id,
            "error": error_entry,
            "trace_id": trace_id,
        }
        print(json.dumps(log_entry))
        
        return {
            "job_type": "tbank_invoice_paid",
            "status": "completed",
            "message": "Invoice not found in ledger (logged)",
            "error": error_entry
        }
    
    order_id = record["order_id"]
    record_metadata = record.get("metadata") or {}
    if isinstance(record_metadata, str):
        try:
            record_metadata = json.loads(record_metadata)
        except Exception:
            record_metadata = {}
    payload_amount_minor = int(payload.get("amount_minor", 0) or 0)
    if payload_amount_minor <= 0:
        try:
            payload_amount_minor = int(round(float(record_metadata.get("totalAmount", 0) or 0) * 100))
        except Exception:
            payload_amount_minor = 0

    # Phase 2 v2.1:
    # PaymentTransaction + order_ledger.payment_status cache update MUST be atomic
    # in the same transaction before FSM state transition.
    payment_result = record_payment_transaction_atomic(
        db_conn,
        order_id=UUID(str(order_id)),
        trace_id=trace_id,
        transaction_type="charge",
        provider_code="tbank",
        provider_transaction_id=str(invoice_id),
        amount_minor=payload_amount_minor,
        currency=str(payload.get("currency", "RUB")),
        status="confirmed",
        status_changed_at=paid_at,
        idempotency_key=f"payment:tbank:{invoice_id}:INVOICE_PAID",
        raw_provider_response=payload,
        metadata={"invoice_number": invoice_number},
    )
    
    # РџРѕРґРіРѕС‚РѕРІРєР° Event РґР»СЏ FSM v2
    # event_id РіРµРЅРµСЂРёСЂСѓРµРј Р·РґРµСЃСЊ (РІ СЂРµР°Р»СЊРЅРѕСЃС‚Рё РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ РёР· job РёР»Рё РІРЅРµС€РЅРµРіРѕ РёСЃС‚РѕС‡РЅРёРєР°)
    event_id = uuid4()
    
    event = Event(
        event_id=event_id,
        source="tbank",
        event_type="INVOICE_PAID",
        occurred_at=paid_at,
        payload={
            "invoice_id": invoice_id,
            "invoice_number": invoice_number,
            "paid_at": paid_at,
            "is_partial": payment_result.get("payment_status") == "partially_paid",
        }
    )
    
    # РџРѕРґРіРѕС‚РѕРІРєР° LedgerRecord РґР»СЏ FSM v2
    state_history = record["state_history"]
    if isinstance(state_history, str):
        state_history = json.loads(state_history)
    
    metadata = record["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    
    ledger_record = LedgerRecord(
        order_id=UUID(str(order_id)),
        state=record["state"],
        state_history=state_history if state_history else [],
        metadata=metadata if metadata else {}
    )
    
    # Р’С‹Р·РѕРІ FSM v2 (pure function)
    fsm_result = fsm_v2_process_event(event, ledger_record)
    
    # РџСЂРёРјРµРЅРµРЅРёРµ СЂРµР·СѓР»СЊС‚Р°С‚Р° FSM Рє Ledger
    if fsm_result.action == "skip":
        # Idempotent skip
        db_conn.commit()
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "tbank_invoice_paid_idempotent",
            "order_id": str(order_id),
            "invoice_id": invoice_id,
            "current_state": fsm_result.from_state,
            "trace_id": trace_id,
        }
        print(json.dumps(log_entry))
        
        return {
            "job_type": "tbank_invoice_paid",
            "status": "completed",
            "message": "State already in target state (idempotent skip)",
            "order_id": str(order_id),
            "fsm_action": "skip"
        }
    
    elif fsm_result.action == "error":
        # FSM РІРµСЂРЅСѓР» РѕС€РёР±РєСѓ - Р·Р°РїРёСЃС‹РІР°РµРј РІ error_log
        error_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": fsm_result.error.get("error_type", "fsm_error"),
            "message": fsm_result.error.get("message", "FSM processing error"),
            "context": fsm_result.error.get("context", {}),
            "event_id": str(event_id)
        }
        
        cursor.execute(
            """
            UPDATE order_ledger
            SET error_log = error_log || %s::jsonb,
                trace_id = COALESCE(trace_id, %s::uuid),
                updated_at = NOW()
            WHERE order_id = %s
            """,
            (json.dumps([error_entry]), trace_id, order_id)
        )
        db_conn.commit()

        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "tbank_invoice_paid_fsm_error",
            "order_id": str(order_id),
            "invoice_id": invoice_id,
            "error": error_entry,
            "trace_id": trace_id,
        }
        print(json.dumps(log_entry))
        
        return {
            "job_type": "tbank_invoice_paid",
            "status": "completed",
            "message": "FSM error (logged)",
            "order_id": str(order_id),
            "error": error_entry,
            "fsm_action": "error"
        }
    
    elif fsm_result.action == "transition":
        # Р’С‹РїРѕР»РЅСЏРµРј transition
        cursor.execute(
            """
            UPDATE order_ledger
            SET state = %s,
                state_history = state_history || %s::jsonb,
                metadata = metadata || %s::jsonb,
                status_changed_at = NOW(),
                trace_id = COALESCE(trace_id, %s::uuid),
                updated_at = NOW()
            WHERE order_id = %s
            RETURNING *
            """,
            (
                fsm_result.to_state,
                json.dumps([fsm_result.state_history_entry]),
                json.dumps(fsm_result.metadata_patch),
                trace_id,
                order_id
            )
        )
        
        updated_record = cursor.fetchone()
        release_result = None
        if fsm_result.to_state in TERMINAL_FAILURE_STATES:
            release_result = _release_reservations_safe(
                db_conn,
                order_id=UUID(str(order_id)),
                trace_id=trace_id,
                reason=f"fsm_terminal:{fsm_result.to_state}",
            )
        db_conn.commit()
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "tbank_invoice_paid_transition_completed",
            "order_id": str(order_id),
            "invoice_id": invoice_id,
            "from_state": fsm_result.from_state,
            "to_state": fsm_result.to_state,
            "trace_id": trace_id,
        }
        print(json.dumps(log_entry))
        
        return {
            "job_type": "tbank_invoice_paid",
            "status": "completed",
            "message": "State transition completed",
            "order_id": str(order_id),
            "from_state": fsm_result.from_state,
            "to_state": fsm_result.to_state,
            "fsm_action": "transition",
            "trace_id": trace_id,
            "payment_status": payment_result.get("payment_status"),
            "release_result": release_result,
        }
    
    else:
        # РќРµРѕР¶РёРґР°РЅРЅС‹Р№ СЂРµР·СѓР»СЊС‚Р°С‚ FSM
        raise Exception(f"Unexpected FSM action: {fsm_result.action}")


def _load_rfq_snapshot(db_conn, rfq_id: UUID) -> Tuple[Dict[str, Any], list]:
    """Load parsed_json + part numbers from persisted RFQ."""
    cursor = db_conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT parsed_json
            FROM rfq_requests
            WHERE id = %s
            LIMIT 1
            """,
            (rfq_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise Exception(f"rfq_id not found: {rfq_id}")

        parsed_json = row.get("parsed_json") or {}
        if isinstance(parsed_json, str):
            parsed_json = json.loads(parsed_json)
        if not isinstance(parsed_json, dict):
            parsed_json = {}

        cursor.execute(
            """
            SELECT part_number
            FROM rfq_items
            WHERE rfq_id = %s
            ORDER BY line_no ASC
            """,
            (rfq_id,),
        )
        part_numbers = [r["part_number"] for r in cursor.fetchall() if r.get("part_number")]
        return parsed_json, part_numbers
    finally:
        cursor.close()


def execute_rfq_v1_from_ocr(payload: Dict[str, Any], db_conn) -> Dict[str, Any]:
    """
    Р’С‹РїРѕР»РЅСЏРµС‚ RFQ pipeline v1 (ADR-008):
    - full mode (parse + persist)
    - re-enrich mode (price only for existing rfq_id)
    """
    if db_conn.autocommit:
        raise RuntimeError("execute_rfq_v1_from_ocr requires autocommit=False")

    if not isinstance(payload, dict):
        raise Exception("payload must be a dict")

    execution_mode = resolve_execution_mode(db_conn, payload)
    trace_id = execution_mode.trace_id
    task_id = uuid4()

    # Infrastructure keys are not part of business payload.
    business_payload = dict(payload)
    business_payload.pop(TRACE_ID_PAYLOAD_KEY, None)
    business_payload.pop(RFQ_ID_PAYLOAD_KEY, None)

    logger.info(
        "RFQ pipeline started",
        extra={"trace_id": str(trace_id), "task_id": str(task_id), "mode": execution_mode.mode},
    )

    # T1: Insert task record (status=processing)
    cursor = db_conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks (id, trace_id, task_type, status, payload, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, now(), now())
        """,
        (task_id, trace_id, "rfq_v1", "processing", json.dumps(business_payload, ensure_ascii=False)),
    )
    db_conn.commit()

    rfq_id: Optional[UUID] = execution_mode.existing_rfq_id

    try:
        parsed_result: Dict[str, Any] = {}
        part_numbers: list = []

        if execution_mode.mode == "re_enrich":
            if not rfq_id:
                raise Exception("Re-enrich mode requires existing rfq_id")
            parsed_result, part_numbers = _load_rfq_snapshot(db_conn, rfq_id)
        else:
            # ========================================
            # FULL PIPELINE
            # ========================================
            ocr_job_id = business_payload.get("ocr_job_id")
            text = business_payload.get("text")
            source = business_payload.get("source", "manual")
            llm_enabled = business_payload.get("llm_enabled", LLM_ENABLED_DEFAULT)

            raw_text = text

            if ocr_job_id and not raw_text:
                cursor = db_conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute(
                    """
                    SELECT result, status
                    FROM job_queue
                    WHERE id = %s
                    """,
                    (ocr_job_id,),
                )
                ocr_job = cursor.fetchone()

                if not ocr_job:
                    raise Exception(f"OCR job {ocr_job_id} not found")

                if ocr_job["status"] != "completed":
                    raise Exception(f"OCR job {ocr_job_id} is not completed (status: {ocr_job['status']})")

                ocr_result = ocr_job["result"]
                if isinstance(ocr_result, str):
                    ocr_result = json.loads(ocr_result)

                raw_text = ocr_result.get("sample_text", "") if ocr_result else ""

                if not raw_text:
                    raise Exception(f"OCR job {ocr_job_id} has no text result")

            if not raw_text:
                raise Exception("No text provided (neither 'text' nor 'ocr_job_id' with result)")

            parsed_result = parse_rfq_deterministic(raw_text)

            if llm_enabled:
                llm_result = parse_rfq_with_llm(raw_text)
                if llm_result:
                    parsed_result = merge_llm_results(parsed_result, llm_result)
                else:
                    parsed_result["llm_used"] = False
                    parsed_result["llm_error"] = "LLM API unavailable, using deterministic parser only"
            else:
                parsed_result["llm_used"] = False

            provisional_rfq_id = uuid4()

            # ========================================
            # SHADOW MODE вЂ” canonical model validation only
            # ========================================
            try:
                canonical_request = convert_to_canonical(
                    merged_dict=parsed_result,
                    raw_text=raw_text,
                    source=source,
                    request_id=provisional_rfq_id,
                    created_at=datetime.now(timezone.utc),
                )

                old_db_params = {
                    "id": provisional_rfq_id,
                    "source": source,
                    "raw_text": raw_text,
                    "parsed_json": json.dumps(parsed_result),
                    "status": "processed",
                }

                new_db_params = canonical_request.to_db_params()
                new_db_params["parsed_json"] = json.dumps(new_db_params["parsed_json"])

                if old_db_params != new_db_params:
                    logger.warning(
                        "RFQ_CANONICAL_MISMATCH: rfq_requests params differ",
                        extra={
                            "rfq_id": str(provisional_rfq_id),
                            "old_keys": list(old_db_params.keys()),
                            "new_keys": list(new_db_params.keys()),
                            "old_parsed_json_sample": str(parsed_result)[:200],
                            "new_parsed_json_sample": str(new_db_params["parsed_json"])[:200],
                        },
                    )

                old_items = []
                for idx, part_num in enumerate(parsed_result.get("candidate_part_numbers", [])[:100], start=1):
                    old_items.append(
                        {
                            "rfq_id": provisional_rfq_id,
                            "line_no": idx,
                            "part_number": part_num,
                            "qty": None,
                            "notes": None,
                        }
                    )

                new_items = canonical_request.get_items_db_params()

                old_items_comparable = [{k: v for k, v in item.items() if k != "id"} for item in old_items]
                new_items_comparable = [{k: v for k, v in item.items() if k != "id"} for item in new_items]

                if old_items_comparable != new_items_comparable:
                    logger.warning(
                        "RFQ_ITEMS_MISMATCH: rfq_items params differ",
                        extra={
                            "rfq_id": str(provisional_rfq_id),
                            "old_count": len(old_items),
                            "new_count": len(new_items),
                            "old_sample": old_items[:3] if old_items else [],
                            "new_sample": new_items_comparable[:3] if new_items else [],
                        },
                    )
            except Exception as e:
                logger.error(
                    "RFQ_CANONICAL_CONVERSION_ERROR: Shadow mode failed",
                    extra={
                        "rfq_id": str(provisional_rfq_id),
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )

            # T2: idempotent rfq_requests insert + rfq_items insert (single transaction)
            insert_result = insert_rfq_idempotent(
                db_conn=db_conn,
                rfq_id=provisional_rfq_id,
                source=source,
                raw_text=raw_text,
                parsed_json=parsed_result,
                trace_id=trace_id,
            )
            rfq_id = insert_result.rfq_id

            if insert_result.is_new:
                cursor = db_conn.cursor()
                for idx, part_num in enumerate(parsed_result.get("candidate_part_numbers", [])[:100], start=1):
                    cursor.execute(
                        """
                        INSERT INTO rfq_items (rfq_id, line_no, part_number, qty, notes)
                        VALUES (%s, %s, %s, NULL, NULL)
                        """,
                        (rfq_id, idx, part_num),
                    )
            db_conn.commit()

            parsed_result, part_numbers = _load_rfq_snapshot(db_conn, rfq_id)

        items_count = len(part_numbers)

        # ========================================
        # ADR-007 вЂ” Soft Fail Price Enrichment
        # ========================================
        if os.getenv("ENABLE_PRICE_ENRICHMENT", "false").lower() == "true":
            try:
                price_result = enrich_prices(part_numbers)
            except Exception as e:
                logger.warning(
                    "PRICE_ENRICHMENT_ERROR: unexpected adapter failure",
                    extra={
                        "trace_id": str(trace_id),
                        "task_id": str(task_id),
                        "rfq_id": str(rfq_id),
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )
                price_result = {
                    "price_status": "error",
                    "price_items_total": items_count,
                    "price_items_found": 0,
                    "price_error": str(e),
                    "price_audit": None,
                }
        else:
            price_result = {
                "price_status": "skipped",
                "price_items_total": items_count,
                "price_items_found": 0,
                "price_error": None,
                "price_audit": None,
            }

        # T3: append-only price log (own transaction, soft-fail persistence)
        price_log_payload = dict(price_result)
        price_log_payload[TRACE_ID_PAYLOAD_KEY] = str(trace_id)
        insert_price_log(db_conn, rfq_id, price_log_payload)

        # T4: task done
        cursor = db_conn.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET status = %s, updated_at = now()
            WHERE id = %s
            """,
            ("done", task_id),
        )
        db_conn.commit()

        logger.info(
            "RFQ pipeline completed successfully",
            extra={"trace_id": str(trace_id), "task_id": str(task_id), "rfq_id": str(rfq_id)},
        )

        company_identifiers = parsed_result.get("company_identifiers", {}) or {}
        inn = None
        if isinstance(company_identifiers, dict):
            inn_value = company_identifiers.get("inn")
            if isinstance(inn_value, list) and inn_value:
                inn = inn_value[0]
            elif isinstance(inn_value, str):
                inn = inn_value

        return {
            "job_type": "rfq_v1_from_ocr",
            "trace_id": str(trace_id),
            "rfq_id": str(rfq_id),
            "items_count": items_count,
            "sample_parts": part_numbers[:5] if part_numbers else [],
            "emails": parsed_result.get("emails", [])[:3],
            "phones": parsed_result.get("phones", [])[:3],
            "inn": inn,
            "llm_used": parsed_result.get("llm_used", False),
            "confidence_overall": parsed_result.get("confidence_overall"),
            "confidence_breakdown": parsed_result.get("confidence_breakdown", {}),
            "price_status": price_result["price_status"],
            "price_items_total": price_result["price_items_total"],
            "price_items_found": price_result["price_items_found"],
            "price_error": price_result["price_error"],
            "price_audit": price_result["price_audit"],
        }

    except Exception as e:
        try:
            db_conn.rollback()
        except Exception:
            logger.error(
                "RFQ_PIPELINE_ROLLBACK_FAILED",
                extra={
                    "trace_id": str(trace_id),
                    "task_id": str(task_id),
                    "original_error": str(e),
                },
            )
            raise

        try:
            cursor = db_conn.cursor()
            cursor.execute(
                """
                UPDATE tasks
                SET status = %s, error = %s, updated_at = now()
                WHERE id = %s
                """,
                ("failed", str(e), task_id),
            )
            db_conn.commit()
        except Exception as update_err:
            logger.error(
                "RFQ_PIPELINE_TASK_UPDATE_FAILED",
                extra={
                    "trace_id": str(trace_id),
                    "task_id": str(task_id),
                    "original_error": str(e),
                    "update_error": str(update_err),
                },
            )

        logger.error(
            "RFQ pipeline failed",
            extra={
                "trace_id": str(trace_id),
                "task_id": str(task_id),
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        raise


@legacy_maintenance_only
def execute_telegram_update(
    payload: Dict[str, Any], db_conn, job_id: UUID, trace_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    РќРѕРІР°СЏ РѕР±СЂР°Р±РѕС‚РєР° Telegram update С‡РµСЂРµР· РјРѕРґСѓР»СЊРЅС‹Р№ router + dispatch_action.
    """
    telegram_payload = payload.get("payload")

    if not isinstance(telegram_payload, dict):
        log_event("telegram_update_invalid_payload", {
            "job_id": str(job_id),
            "payload_type": str(type(telegram_payload)),
            "trace_id": trace_id,
        })
        return {
            "job_type": "telegram_update",
            "status": "completed",
            "message": "Payload missing or invalid"
        }

    update_id = telegram_payload.get("update_id")
    log_event("telegram_update_router_start", {
        "job_id": str(job_id),
        "update_id": update_id,
        "trace_id": trace_id,
    })

    # #region agent log
    debug_log("C", "ru_worker.py:810", "execute_telegram_update started", {"job_id": str(job_id), "update_id": update_id, "text": telegram_payload.get("message", {}).get("text", "")[:50]})
    # #endregion

    try:
        callback_query = telegram_payload.get("callback_query")
        if callback_query:
            callback_query_id = callback_query.get("id")
            if callback_query_id:
                answer_callback_query(callback_query_id)

        response_text, action = route_update(telegram_payload)
        chat_id = extract_chat_id_from_update(telegram_payload)
        
        # #region agent log
        debug_log("D", "ru_worker.py:824", "route_update returned", {"response_text": response_text[:50] if response_text else None, "has_action": bool(action), "action_type": action.get("action_type") if action else None, "chat_id": chat_id})
        # #endregion

        # РРЎРџР РђР’Р›Р•РќРР•: РќРµ РѕС‚РїСЂР°РІР»СЏРµРј РїСЂРѕРјРµР¶СѓС‚РѕС‡РЅРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ, РµСЃР»Рё РµСЃС‚СЊ action
        # Action СЃР°Рј РѕС‚РїСЂР°РІРёС‚ С„РёРЅР°Р»СЊРЅРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ С‡РµСЂРµР· handle_router_action
        if response_text and chat_id and not action:
            # #region agent log
            debug_log("E", "ru_worker.py:829", "Sending direct response", {"chat_id": chat_id, "text": response_text[:50]})
            # #endregion
            send_telegram_message(chat_id, response_text)
        elif response_text and not chat_id:
            log_event("telegram_update_response_no_chat", {
                "update_id": update_id,
                "response_text": response_text
            })

        action_info = None
        if action:
            # #region agent log
            debug_log("G", "ru_worker.py:837", "Processing action", {"action_type": action.get("action_type"), "chat_id": chat_id})
            # #endregion
            try:
                action_result = handle_router_action(action, db_conn)
                action_info = {
                    "action_type": action.get("action_type"),
                    "status": action_result.get("status")
                }
                # #region agent log
                debug_log("G", "ru_worker.py:843", "Action completed", {"action_type": action.get("action_type"), "status": action_result.get("status")})
                # #endregion
            except Exception as action_error:
                # РРЎРџР РђР’Р›Р•РќРР•: РћР±СЂР°Р±РѕС‚РєР° РѕС€РёР±РѕРє РІ handle_router_action
                error_msg = str(action_error)
                log_event("telegram_update_action_error", {
                    "job_id": str(job_id),
                    "update_id": update_id,
                    "action_type": action.get("action_type"),
                    "error": error_msg
                })
                # РћС‚РїСЂР°РІР»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ РѕР± РѕС€РёР±РєРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ
                if chat_id:
                    send_telegram_message(chat_id, f"вќЊ РћС€РёР±РєР° РѕР±СЂР°Р±РѕС‚РєРё РєРѕРјР°РЅРґС‹: {error_msg[:200]}")
                action_info = {
                    "action_type": action.get("action_type"),
                    "status": "error",
                    "error": error_msg
                }

        log_event("telegram_update_router_completed", {
            "job_id": str(job_id),
            "update_id": update_id,
            "action_type": action.get("action_type") if action else None,
            "trace_id": trace_id,
        })

        return {
            "job_type": "telegram_update",
            "status": "completed",
            "message": "Telegram update processed via router",
            "update_id": update_id,
            "action": action_info,
            "trace_id": trace_id,
        }
    except Exception as e:
        db_conn.rollback()
        error_msg = str(e)
        log_event("telegram_update_router_error", {
            "job_id": str(job_id),
            "update_id": update_id,
            "error": error_msg,
            "trace_id": trace_id,
        })
        # РРЎРџР РђР’Р›Р•РќРР•: РћС‚РїСЂР°РІР»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ РѕР± РѕС€РёР±РєРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ
        chat_id = extract_chat_id_from_update(telegram_payload) if isinstance(telegram_payload, dict) else None
        if chat_id:
            try:
                send_telegram_message(chat_id, f"вќЊ РћС€РёР±РєР° РѕР±СЂР°Р±РѕС‚РєРё Р·Р°РїСЂРѕСЃР°: {error_msg[:200]}")
            except:
                pass  # Р•СЃР»Рё РЅРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РїСЂР°РІРёС‚СЊ, РЅРµ РїР°РґР°РµРј РґР°Р»СЊС€Рµ
        raise


@legacy_maintenance_only
def execute_cdek_shipment_status(
    payload: Dict[str, Any], db_conn, job_id: UUID, trace_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ CDEK shipment status update:
    1. Р’С‹Р·С‹РІР°РµС‚ cdek_order_mapper
    2. Р•СЃР»Рё OrderEvent в†’ СЃРѕР·РґР°РµС‚ РЅРѕРІС‹Р№ job (order_event)
    3. Р•СЃР»Рё None в†’ job completed
    """
    try:
        # Р’С‹Р·С‹РІР°РµРј mapper (РЅСѓР¶РµРЅ db_conn РґР»СЏ lookup)
        order_event = map_cdek_to_order_event(payload, uuid4(), db_conn)
        
        if order_event is None:
            # РќРµ РЅР°Р№РґРµРЅ Р·Р°РєР°Р· - Р·Р°РІРµСЂС€Р°РµРј job
            log_entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "event": "cdek_shipment_status_no_order",
                "job_id": str(job_id),
                "external_id": payload.get("external_id"),
                "trace_id": trace_id,
            }
            print(json.dumps(log_entry))
            
            return {
                "job_type": "cdek_shipment_status",
                "status": "completed",
                "message": "CDEK shipment status not mapped to order",
                "external_id": payload.get("external_id")
            }
        
        # РЎРѕР·РґР°РµРј РЅРѕРІС‹Р№ job (order_event)
        occurred_at_iso = (
            order_event.occurred_at.isoformat()
            if hasattr(order_event.occurred_at, "isoformat")
            else str(order_event.occurred_at)
        )
        order_event_payload = {
            "event_id": str(order_event.event_id),
            "source": order_event.source,
            "event_type": order_event.event_type,
            "external_id": order_event.external_id,
            "occurred_at": occurred_at_iso,
            "payload": order_event.payload,
            "order_id": str(order_event.order_id)
        }
        
        status_bucket = (
            str(order_event.payload.get("status_date") or occurred_at_iso or "")[:16]
            or "na"
        )
        status_value = str(order_event.payload.get("status") or "unknown")
        order_event_idempotency_key = (
            f"order_event:{order_event.source}:{order_event.external_id}:{status_value}:{status_bucket}"
        )
        
        new_job_id = enqueue_job_with_trace(
            db_conn=db_conn,
            job_type="order_event",
            payload=order_event_payload,
            idempotency_key=order_event_idempotency_key,
            trace_id=trace_id,
        )
        db_conn.commit()
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "cdek_shipment_status_mapped_to_order_event",
            "job_id": str(job_id),
            "order_event_job_id": str(new_job_id),
            "order_id": str(order_event.order_id),
            "external_id": order_event.external_id,
            "trace_id": trace_id,
        }
        print(json.dumps(log_entry))
        
        return {
            "job_type": "cdek_shipment_status",
            "status": "completed",
            "message": "CDEK shipment status mapped to order event",
            "order_event_job_id": str(new_job_id),
            "order_id": str(order_event.order_id),
            "trace_id": trace_id,
        }
        
    except Exception as e:
        db_conn.rollback()
        error_msg = str(e)
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "cdek_shipment_status_error",
            "job_id": str(job_id),
            "error": error_msg,
            "trace_id": trace_id,
        }
        print(json.dumps(log_entry))
        raise


@legacy_maintenance_only
def execute_order_event(payload: Dict[str, Any], db_conn, trace_id: Optional[str] = None) -> Dict[str, Any]:
    """
    РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ order_event С‡РµСЂРµР· FSM v2:
    1. Lookup order_ledger РїРѕ order_id
    2. Р•СЃР»Рё РЅРµ РЅР°Р№РґРµРЅ - Р»РѕРіРёСЂСѓРµРј РѕС€РёР±РєСѓ, job completed
    3. Р•СЃР»Рё РЅР°Р№РґРµРЅ - РІС‹Р·С‹РІР°РµРј FSM v2
    4. РџСЂРёРјРµРЅСЏРµРј РёР·РјРµРЅРµРЅРёСЏ Рє Ledger
    """
    order_id_str = payload.get("order_id")
    if not order_id_str:
        raise Exception("order_id is required in order_event payload")
    
    try:
        order_id = UUID(order_id_str)
    except (ValueError, TypeError):
        raise Exception(f"Invalid order_id format: {order_id_str}")
    
    cursor = db_conn.cursor(cursor_factory=RealDictCursor)
    
    # Lookup РІ order_ledger
    cursor.execute(
        """
        SELECT * FROM order_ledger
        WHERE order_id = %s
        LIMIT 1
        FOR UPDATE
        """,
        (order_id,)
    )
    
    record = cursor.fetchone()
    
    if not record:
        error_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": "ledger_lookup",
            "message": "Ledger record not found for order_id",
            "context": {
                "order_id": order_id_str,
                "source": payload.get("source"),
                "event_type": payload.get("event_type")
            }
        }
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "order_event_ledger_not_found",
            "order_id": order_id_str,
            "error": error_entry,
            "trace_id": trace_id,
        }
        print(json.dumps(log_entry))
        
        return {
            "job_type": "order_event",
            "status": "completed",
            "message": "Order not found in ledger (logged)",
            "error": error_entry
        }
    
    # РџРѕРґРіРѕС‚РѕРІРєР° Event РґР»СЏ FSM v2 (CDM validation + adapter)
    try:
        ev = OrderEventInput.model_validate(payload)
        event = order_event_input_to_fsm_event(ev)
    except ValidationError as e:
        error_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": "payload_validation",
            "message": "OrderEventInput validation failed",
            "context": {"errors": e.errors()},
        }
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "order_event_validation_error",
            "order_id": order_id_str,
            "error": error_entry,
            "trace_id": trace_id,
        }
        print(json.dumps(log_entry))
        return {
            "job_type": "order_event",
            "status": "completed",
            "message": "Payload validation failed (logged)",
            "error": error_entry,
        }
    
    # РџРѕРґРіРѕС‚РѕРІРєР° LedgerRecord РґР»СЏ FSM v2
    state_history = record["state_history"]
    if isinstance(state_history, str):
        state_history = json.loads(state_history)
    
    metadata = record["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    
    ledger_record = LedgerRecord(
        order_id=UUID(str(record["order_id"])),
        state=record["state"],
        state_history=state_history if state_history else [],
        metadata=metadata if metadata else {}
    )
    
    # Р’С‹Р·РѕРІ FSM v2 (pure function)
    fsm_result = fsm_v2_process_event(event, ledger_record)
    
    # РџСЂРёРјРµРЅРµРЅРёРµ СЂРµР·СѓР»СЊС‚Р°С‚Р° FSM Рє Ledger
    if fsm_result.action == "skip":
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "order_event_idempotent",
            "order_id": order_id_str,
            "current_state": fsm_result.from_state,
            "trace_id": trace_id,
        }
        print(json.dumps(log_entry))
        
        return {
            "job_type": "order_event",
            "status": "completed",
            "message": "State already in target state (idempotent skip)",
            "order_id": order_id_str,
            "fsm_action": "skip"
        }
    
    elif fsm_result.action == "error":
        error_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error_type": fsm_result.error.get("error_type", "fsm_error"),
            "message": fsm_result.error.get("message", "FSM processing error"),
            "context": fsm_result.error.get("context", {}),
            "event_id": str(event_id)
        }
        
        cursor.execute(
            """
            UPDATE order_ledger
            SET error_log = error_log || %s::jsonb,
                trace_id = COALESCE(trace_id, %s::uuid),
                updated_at = NOW()
            WHERE order_id = %s
            """,
            (json.dumps([error_entry]), trace_id, order_id)
        )
        db_conn.commit()
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "order_event_fsm_error",
            "order_id": order_id_str,
            "error": error_entry,
            "trace_id": trace_id,
        }
        print(json.dumps(log_entry))
        
        return {
            "job_type": "order_event",
            "status": "completed",
            "message": "FSM error (logged)",
            "order_id": order_id_str,
            "error": error_entry,
            "fsm_action": "error"
        }
    
    elif fsm_result.action == "transition":
        cursor.execute(
            """
            UPDATE order_ledger
            SET state = %s,
                state_history = state_history || %s::jsonb,
                metadata = metadata || %s::jsonb,
                status_changed_at = NOW(),
                trace_id = COALESCE(trace_id, %s::uuid),
                updated_at = NOW()
            WHERE order_id = %s
            RETURNING *
            """,
            (
                fsm_result.to_state,
                json.dumps([fsm_result.state_history_entry]),
                json.dumps(fsm_result.metadata_patch),
                trace_id,
                order_id
            )
        )
        
        updated_record = cursor.fetchone()
        release_result = None
        if fsm_result.to_state in TERMINAL_FAILURE_STATES:
            release_result = _release_reservations_safe(
                db_conn,
                order_id=order_id,
                trace_id=trace_id,
                reason=f"fsm_terminal:{fsm_result.to_state}",
            )
        db_conn.commit()
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": "order_event_transition_completed",
            "order_id": order_id_str,
            "from_state": fsm_result.from_state,
            "to_state": fsm_result.to_state,
            "trace_id": trace_id,
        }
        print(json.dumps(log_entry))
        
        return {
            "job_type": "order_event",
            "status": "completed",
            "message": "State transition completed",
            "order_id": order_id_str,
            "from_state": fsm_result.from_state,
            "to_state": fsm_result.to_state,
            "fsm_action": "transition",
            "trace_id": trace_id,
            "release_result": release_result,
        }
    
    else:
        raise Exception(f"Unexpected FSM action: {fsm_result.action}")


def process_job(job: Dict[str, Any], db_conn) -> Dict[str, Any]:
    """РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ Р·Р°РґР°С‡Сѓ РІ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё РѕС‚ job_type"""
    job_type = job.get("job_type", "")
    payload = job.get("payload", {})
    job_id = job.get("id")
    trace_id_raw = job.get("trace_id")
    trace_id = str(trace_id_raw) if trace_id_raw else None
    
    if isinstance(payload, str):
        payload = json.loads(payload)
    
    if job_type == "test_job":
        return execute_test_job(payload)
    elif job_type == "rfq_v1_from_ocr":
        return execute_rfq_v1_from_ocr(payload, db_conn)
    elif job_type == "tbank_invoice_paid":
        return execute_tbank_invoice_paid(payload, db_conn, trace_id=trace_id)
    elif job_type == "telegram_update":
        if not job_id:
            raise Exception("job_id is required for telegram_update")
        return execute_telegram_update(payload, db_conn, UUID(str(job_id)), trace_id=trace_id)
    elif job_type == "telegram_command":
        # MAINTENANCE ONLY: legacy beta path, no feature expansion.
        return execute_telegram_command(payload, db_conn)
    elif job_type == "cdek_shipment":
        # MAINTENANCE ONLY: legacy beta path, no feature expansion.
        return execute_cdek_shipment(payload, db_conn)
    elif job_type == "cdek_shipment_status":
        if not job_id:
            raise Exception("job_id is required for cdek_shipment_status")
        return execute_cdek_shipment_status(payload, db_conn, UUID(str(job_id)), trace_id=trace_id)
    elif job_type == "insales_paid_sync":
        # MAINTENANCE ONLY: legacy beta path, no feature expansion.
        return execute_insales_paid_sync(payload, db_conn)
    elif job_type == "invoice_create":
        # MAINTENANCE ONLY: legacy beta path, no feature expansion.
        return execute_invoice_create(payload, db_conn)
    elif job_type == "shopware_product_sync":
        # MAINTENANCE ONLY: legacy beta path, no feature expansion.
        return execute_shopware_product_sync(payload, db_conn)
    elif job_type == "shopware_order_handoff":
        return execute_shopware_order_handoff(payload, db_conn, trace_id=trace_id)
    elif job_type == "order_event":
        return execute_order_event(payload, db_conn, trace_id=trace_id)
    elif job_type == "governance_case_create":
        from governance_case_creator import execute_governance_case_create

        return execute_governance_case_create(payload, db_conn, trace_id=trace_id)
    elif job_type == "governance_execute":
        from governance_executor import execute_governance_case

        return execute_governance_case(payload, db_conn, trace_id=trace_id)
    else:
        raise Exception(f"Unknown job_type for RU worker: {job_type}")


def sweep_stuck_jobs(db_conn, timeout_minutes: int = ZOMBIE_TIMEOUT_MINUTES) -> int:
    """Requeue zombie jobs: processing older than timeout -> pending."""
    cursor = db_conn.cursor(cursor_factory=RealDictCursor)
    zombie_note = f"zombie_recovery: requeued after {timeout_minutes}m in processing"
    has_trace = _job_queue_has_trace_id(db_conn)
    try:
        if has_trace:
            cursor.execute(
                """
                UPDATE job_queue
                SET status = 'pending',
                    error = CASE
                        WHEN error IS NULL OR error = '' THEN %s
                        ELSE error || E'\\n' || %s
                    END,
                    updated_at = NOW()
                WHERE status = 'processing'
                  AND updated_at < NOW() - (%s * INTERVAL '1 minute')
                RETURNING id, job_type, trace_id
                """,
                (zombie_note, zombie_note, timeout_minutes),
            )
        else:
            cursor.execute(
                """
                UPDATE job_queue
                SET status = 'pending',
                    error = CASE
                        WHEN error IS NULL OR error = '' THEN %s
                        ELSE error || E'\\n' || %s
                    END,
                    updated_at = NOW()
                WHERE status = 'processing'
                  AND updated_at < NOW() - (%s * INTERVAL '1 minute')
                RETURNING id, job_type
                """,
                (zombie_note, zombie_note, timeout_minutes),
            )

        rows = cursor.fetchall()
        db_conn.commit()

        for row in rows:
            log_payload = {
                "job_id": str(row["id"]),
                "job_type": row["job_type"],
                "timeout_minutes": timeout_minutes,
            }
            if has_trace:
                log_payload["trace_id"] = str(row.get("trace_id")) if row.get("trace_id") else None
            log_event("zombie_job_requeued", log_payload)

        return len(rows)
    except Exception:
        db_conn.rollback()
        raise
    finally:
        cursor.close()


def main():
    """Р“Р»Р°РІРЅС‹Р№ С†РёРєР» RU worker"""
    print("RU Worker started")
    print(f"POSTGRES: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
    print(f"POLL_INTERVAL: {POLL_INTERVAL}s")
    print(f"LLM_ENABLED_DEFAULT: {LLM_ENABLED_DEFAULT}")
    print("Press Ctrl+C to stop\n")
    
    bootstrap_conn = None
    try:
        bootstrap_conn = get_db_connection()
        ensure_policy_snapshot(bootstrap_conn)
    finally:
        if bootstrap_conn:
            return_db_connection(bootstrap_conn)

    poll_cycle = 0
    while True:
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            poll_cycle += 1

            if poll_cycle % ZOMBIE_SWEEP_EVERY_CYCLES == 0:
                recovered_jobs = sweep_stuck_jobs(conn, timeout_minutes=ZOMBIE_TIMEOUT_MINUTES)
                if recovered_jobs:
                    log_event(
                        "zombie_sweep_summary",
                        {
                            "recovered_jobs": recovered_jobs,
                            "timeout_minutes": ZOMBIE_TIMEOUT_MINUTES,
                        },
                    )
                expired_action_locks = sweep_expired_locks(conn)
                if expired_action_locks:
                    log_event(
                        "action_lock_sweep_summary",
                        {
                            "expired_action_locks": expired_action_locks,
                        },
                    )

            # SELECT RU-side jobs (РІРєР»СЋС‡Р°СЏ РЅРѕРІС‹Рµ side-effect workers)
            if _job_queue_has_trace_id(conn):
                cursor.execute(
                    """
                    SELECT id, job_type, payload, trace_id
                    FROM job_queue
                    WHERE status = 'pending'
                      AND job_type IN ('test_job', 'rfq_v1_from_ocr', 'tbank_invoice_paid', 'telegram_update', 'telegram_command', 'cdek_shipment', 'cdek_shipment_status', 'insales_paid_sync', 'invoice_create', 'shopware_product_sync', 'shopware_order_handoff', 'order_event', 'governance_case_create', 'governance_execute')
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """
                )
            else:
                cursor.execute(
                    """
                    SELECT id, job_type, payload, NULL::uuid AS trace_id
                    FROM job_queue
                    WHERE status = 'pending'
                      AND job_type IN ('test_job', 'rfq_v1_from_ocr', 'tbank_invoice_paid', 'telegram_update', 'telegram_command', 'cdek_shipment', 'cdek_shipment_status', 'insales_paid_sync', 'invoice_create', 'shopware_product_sync', 'shopware_order_handoff', 'order_event', 'governance_case_create', 'governance_execute')
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """
                )

            job = cursor.fetchone()

            if not job:
                # РќРµС‚ Р·Р°РґР°С‡, Р¶РґРµРј
                time.sleep(POLL_INTERVAL)
                continue

            job_id = job["id"]
            job_type = job["job_type"]
            payload = job["payload"]
            trace_id = str(job["trace_id"]) if job.get("trace_id") else None

            if isinstance(payload, str):
                payload = json.loads(payload)

            # #region agent log
            debug_log(
                "C",
                "ru_worker.py:job_poll",
                "Job selected for processing",
                {
                    "job_id": str(job_id),
                    "job_type": job_type,
                    "trace_id": trace_id,
                    "update_id": payload.get("payload", {}).get("update_id") if job_type == "telegram_update" else None,
                },
            )
            # #endregion

            log_event(
                "job_processing_started",
                {
                    "job_id": str(job_id),
                    "job_type": job_type,
                    "trace_id": trace_id,
                },
            )
            print(f"Processing job: {job_id} ({job_type})")

            # UPDATE РЅР° processing
            cursor.execute(
                """
                UPDATE job_queue
                SET status = 'processing', updated_at = NOW()
                WHERE id = %s
                """,
                (job_id,),
            )
            conn.commit()

            # Р’С‹РїРѕР»РЅСЏРµРј Р·Р°РґР°С‡Сѓ
            cleanup_order_id = _resolve_order_id_for_cleanup(job_type, payload, conn)
            job_failed = False
            try:
                result = process_job(dict(job), conn)
                if isinstance(result, dict) and trace_id and "trace_id" not in result:
                    result["trace_id"] = trace_id

                # UPDATE РЅР° completed СЃ result
                cursor.execute(
                    """
                    UPDATE job_queue
                    SET status = 'completed',
                        result = %s,
                        updated_at = NOW()
                    WHERE id = %s
                      AND status = 'processing'
                    """,
                    (json.dumps(result, ensure_ascii=False), job_id),
                )
                if cursor.rowcount == 0:
                    conn.rollback()
                    log_event(
                        "job_status_update_skipped",
                        {
                            "job_id": str(job_id),
                            "reason": "not_processing_zombie_race",
                            "trace_id": trace_id,
                        },
                    )
                else:
                    conn.commit()

                    log_event(
                        "job_processing_completed",
                        {
                            "job_id": str(job_id),
                            "job_type": job_type,
                            "trace_id": trace_id,
                        },
                    )
                    print(f"Job {job_id} completed successfully\n")

            except Exception as e:
                job_failed = True
                error_msg = str(e)
                print(f"Job {job_id} failed: {error_msg}")

                # UPDATE РЅР° failed
                cursor.execute(
                    """
                    UPDATE job_queue
                    SET status = 'failed',
                        error = %s,
                        updated_at = NOW()
                    WHERE id = %s
                      AND status = 'processing'
                    """,
                    (error_msg, job_id),
                )
                if cursor.rowcount == 0:
                    conn.rollback()
                    log_event(
                        "job_status_update_skipped",
                        {
                            "job_id": str(job_id),
                            "reason": "not_processing_zombie_race",
                            "trace_id": trace_id,
                        },
                    )
                else:
                    conn.commit()
                    log_event(
                        "job_processing_failed",
                        {
                            "job_id": str(job_id),
                            "job_type": job_type,
                            "trace_id": trace_id,
                            "error": error_msg,
                        },
                    )
            finally:
                if job_failed and cleanup_order_id is not None:
                    try:
                        _release_reservations_safe(
                            conn,
                            order_id=cleanup_order_id,
                            trace_id=trace_id,
                            reason="job_processor_failure_cleanup",
                        )
                        conn.commit()
                    except Exception:
                        conn.rollback()

        except KeyboardInterrupt:
            print("\nStopping RU worker...")
            break
        except Exception as e:
            error_msg = str(e)
            print(f"Unexpected error in main loop: {error_msg}")

            # Р›РѕРіРёСЂСѓРµРј РѕС€РёР±РєСѓ
            log_event(
                "main_loop_error",
                {
                    "error": error_msg,
                    "error_type": type(e).__name__,
                },
            )

            # Р•СЃР»Рё РѕС€РёР±РєР° РїРѕРґРєР»СЋС‡РµРЅРёСЏ Рє Р‘Р” - СѓРІРµР»РёС‡РёРІР°РµРј Р·Р°РґРµСЂР¶РєСѓ
            if "connection" in error_msg.lower() or "password" in error_msg.lower() or "fe_sendauth" in error_msg.lower():
                log_event("db_connection_error_retry", {"error": error_msg})
                time.sleep(POLL_INTERVAL * 3)  # РЈРІРµР»РёС‡РёРІР°РµРј Р·Р°РґРµСЂР¶РєСѓ РїСЂРё РѕС€РёР±РєРµ Р‘Р”
            else:
                time.sleep(POLL_INTERVAL)

            continue
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    return_db_connection(conn)
                except Exception:
                    pass

    if _DB_POOL is not None:
        _DB_POOL.closeall()


if __name__ == "__main__":
    main()



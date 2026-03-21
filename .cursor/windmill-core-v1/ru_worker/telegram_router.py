#!/usr/bin/env python3
"""
Telegram Router для Windmill
Pure функция: update → action (без side-effects).
Полная версия со всеми handlers.
"""

import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from config import get_config

_CONFIG = get_config()

# Debug logging path
DEBUG_LOG_PATH = Path(r"c:\cursor_project\biretos-automation\.cursor\.cursor\debug.log")

def debug_log(hypothesis_id: str, location: str, message: str, data: dict):
    """Компактная функция для записи debug логов"""
    try:
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

# CDEK конфигурация (для handle_ship)
CDEK_FROM_LOCATION_CODE = _CONFIG.cdek_from_location_code
CDEK_SENDER_COMPANY = _CONFIG.cdek_sender_company
CDEK_SENDER_PHONE = _CONFIG.cdek_sender_phone
CDEK_SENDER_ADDRESS = _CONFIG.cdek_sender_address

# ACL из ENV
_allowed_user_ids_raw = _CONFIG.allowed_user_ids if getattr(_CONFIG, "allowed_user_ids", None) else ()
ALLOWED_USER_IDS = set(_allowed_user_ids_raw)


def log_event(event: str, data: Dict[str, Any]) -> None:
    """Structured logging в stdout."""
    log_entry = {
        "event": event,
        "timestamp": time.time(),
        **data
    }
    print(json.dumps(log_entry), flush=True)


def extract_user_id_from_update(update: Dict[str, Any]) -> Optional[int]:
    """Извлекает user_id из update."""
    message = update.get("message")
    if message:
        from_user = message.get("from")
        if from_user:
            return from_user.get("id")
    
    callback_query = update.get("callback_query")
    if callback_query:
        from_user = callback_query.get("from")
        if from_user:
            return from_user.get("id")
    
    return None


def extract_chat_id_from_update(update: Dict[str, Any]) -> Optional[int]:
    """Извлекает chat_id из update."""
    message = update.get("message")
    if message:
        chat = message.get("chat")
        if chat:
            return chat.get("id")
    
    callback_query = update.get("callback_query")
    if callback_query:
        message = callback_query.get("message")
        if message:
            chat = message.get("chat")
            if chat:
                return chat.get("id")
    
    return None


def check_acl(user_id: Optional[int]) -> bool:
    """Проверка ACL."""
    if user_id is None:
        return False
    return user_id in ALLOWED_USER_IDS


def handle_callback_query(callback_query: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int]) -> Optional[Dict[str, Any]]:
    """
    Обрабатывает callback_query и формирует action.
    
    Returns:
        action dict или None
    """
    callback_data = callback_query.get("data", "")
    callback_query_id = callback_query.get("id")
    
    log_event("callback_query_processing", {
        "callback_data": callback_data,
        "callback_query_id": callback_query_id,
        "user_id": user_id,
        "chat_id": chat_id
    })
    
    # Обработка ship_paid callback
    if callback_data.startswith("ship_paid:"):
        invoice_id = callback_data[len("ship_paid:"):].strip()

        if not invoice_id:
            log_event("callback_query_error", {
                "error": "Empty invoice_id in ship_paid callback",
                "callback_data": callback_data
            })
            return None

        action = {
            "action_type": "ship_paid",
            "payload": {
                "invoice_id": invoice_id
            },
            "source": "callback:/ship_paid",
            "metadata": {
                "chat_id": chat_id,
                "user_id": user_id,
                "callback_query_id": callback_query_id,
                "timestamp": time.time()
            }
        }

        log_event("callback_query_action_formed", {
            "action_type": action["action_type"],
            "invoice_id": invoice_id
        })

        return action

    # Phase 7 — NLU confirm callback  nlu_confirm:<confirmation_id>
    if callback_data.startswith("nlu_confirm:"):
        import uuid as _uuid
        confirmation_id = callback_data[len("nlu_confirm:"):].strip()
        if not confirmation_id:
            log_event("nlu_confirm_error", {"error": "empty confirmation_id"})
            return None
        trace_id = str(_uuid.uuid4())
        action = {
            "action_type": "nlu_confirm",
            "payload": {
                "confirmation_id": confirmation_id,
            },
            "source": "callback:nlu_confirm",
            "metadata": {
                "chat_id": chat_id,
                "user_id": user_id,
                "employee_id": str(user_id) if user_id else "unknown",
                "employee_role": "operator",
                "callback_query_id": callback_query_id,
                "trace_id": trace_id,
                "timestamp": time.time(),
            },
        }
        log_event("nlu_confirm_action_formed", {
            "confirmation_id": confirmation_id,
            "trace_id": trace_id,
        })
        return action

    # Phase 7 — NLU cancel callback  nlu_cancel:<confirmation_id>
    if callback_data.startswith("nlu_cancel:"):
        confirmation_id = callback_data[len("nlu_cancel:"):].strip()
        log_event("nlu_cancel_received", {"confirmation_id": confirmation_id})
        # No action needed — confirmation will expire via TTL.
        # Return a no-op action so the router knows it was handled.
        return {
            "action_type": "__nlu_cancel_ack__",
            "payload": {"confirmation_id": confirmation_id},
            "source": "callback:nlu_cancel",
            "metadata": {"chat_id": chat_id, "user_id": user_id},
        }

    # Неизвестный callback_data
    log_event("callback_query_unknown", {
        "callback_data": callback_data
    })
    return None


def route_update(update: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Маршрутизирует Telegram update и возвращает action.
    
    Args:
        update: Telegram Update object
    
    Returns:
        tuple: (response_text, action)
        - response_text: текст ответа пользователю (или None)
        - action: action dict для dispatch (или None)
    """
    update_id = update.get("update_id")
    
    log_event("router_update_received", {
        "update_id": update_id,
        "has_message": "message" in update,
        "has_callback_query": "callback_query" in update
    })
    
    # Извлечение user_id и chat_id
    user_id = extract_user_id_from_update(update)
    chat_id = extract_chat_id_from_update(update)
    
    # Обработка callback_query (требует ACL)
    callback_query = update.get("callback_query")
    if callback_query:
        # Для callback_query нужна ACL проверка
        if not check_acl(user_id):
            log_event("router_acl_denied", {
                "user_id": user_id,
                "update_id": update_id
            })
            return ("ERR: FORBIDDEN", None)
        
        action = handle_callback_query(callback_query, chat_id, user_id)
        if action:
            return (None, action)
        return ("ERR: UNKNOWN CALLBACK", None)
    
    # Обработка message
    message = update.get("message")
    if not message:
        log_event("router_no_message", {
            "update_id": update_id
        })
        return (None, None)
    
    # Извлечение текста команды
    text = message.get("text", "").strip()
    
    # #region agent log
    debug_log("D", "telegram_router.py:193", "Extracted command text", {"update_id": update_id, "text": text[:50], "user_id": user_id, "chat_id": chat_id})
    # #endregion
    
    if not text:
        log_event("router_no_text", {"update_id": update_id})
        return (None, None)

    # Phase 7 — free-text → NLU parse (non-slash messages from ACL'd users)
    if not text.startswith("/"):
        if not check_acl(user_id):
            log_event("router_acl_denied", {"user_id": user_id, "update_id": update_id})
            return ("ERR: FORBIDDEN", None)
        import uuid as _uuid
        trace_id = str(_uuid.uuid4())
        action = {
            "action_type": "nlu_parse",
            "payload": {"text": text},
            "source": "message:free_text",
            "metadata": {
                "chat_id": chat_id,
                "user_id": user_id,
                "employee_id": str(user_id) if user_id else "unknown",
                "employee_role": "operator",
                "trace_id": trace_id,
                "timestamp": time.time(),
            },
        }
        log_event("router_nlu_parse_action_formed", {
            "trace_id": trace_id,
            "text_len": len(text),
        })
        return (None, action)
    
    # Используем полный route_command (ACL проверка внутри для команд с requires_acl: True)
    result = route_command(text, message, chat_id, user_id)
    
    # #region agent log
    debug_log("D", "telegram_router.py:203", "route_command returned", {"text": text, "response_text": result[0][:50] if result[0] else None, "has_action": bool(result[1])})
    # #endregion
    
    return result


# Command Handlers
def handle_start(message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Обрабатывает команду /start."""
    return ("OK", None)


def handle_health(message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Обрабатывает команду /health."""
    return ("OK", None)


def handle_ping(message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Обрабатывает команду /ping."""
    return ("pong", None)


def handle_help(message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Обрабатывает команду /help."""
    help_text = (
        "/start\n/health\n/ping\n/ship <order_id> | <tariff> | <city> | <address> | <name> | <phone> | <weight_g> | <L> | <W> | <H>\n"
        "/invoice <invoice_id>\n/invoices — показать последние счета\n"
        "/ship_paid <invoice_id> — создать накладную для оплаченного счета\n"
        "/auto_ship — 🚀 автоматически создать накладные для всех оплаченных счетов"
    )
    return (help_text, None)


def handle_echo(message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int], echo_text: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Обрабатывает команду /echo <text>."""
    if not echo_text:
        return ("ERR: EMPTY", None)
    elif len(echo_text) > 256:
        return ("ERR: TOO LONG", None)
    else:
        return (echo_text, None)


def handle_whoami(message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Обрабатывает команду /whoami."""
    from_user = message.get("from", {})
    username = from_user.get("username")
    response_text = f"chat_id: {chat_id}\nuser_id: {user_id}\nusername: {username if username else 'none'}"
    return (response_text, None)


def handle_admin(message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Обрабатывает команду /admin."""
    return ("OK", None)


def handle_stats(message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Обрабатывает команду /stats."""
    # В Windmill нет глобальных переменных для uptime, поэтому упрощённая версия
    response_text = "Stats: Windmill mode (uptime not available)"
    return (response_text, None)


def handle_build(message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Обрабатывает команду /build."""
    import os
    import sys
    response_text = f"Build: Windmill\nFile: {os.path.abspath(__file__)}"
    return (response_text, None)


def handle_export(message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int], category_str: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Stub для команды /export <category>. R2 Telegram Export — Tier-3 adapter only."""
    import uuid
    trace_id = str(uuid.uuid4())
    log_event("export_requested", {"trace_id": trace_id, "chat_id": str(chat_id) if chat_id else None})
    return ("Coming soon", None)


def handle_invoice(message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int], invoice_id_str: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Обрабатывает команду /invoice <invoice_id>."""
    if not invoice_id_str or not invoice_id_str.strip():
        return ("ERR: EMPTY", None)
    
    invoice_id = invoice_id_str.strip()
    
    action = {
        "action_type": "tbank_invoice_status",
        "payload": {
            "invoice_id": invoice_id
        },
        "source": "command:/invoice",
        "metadata": {
            "chat_id": chat_id,
            "user_id": user_id,
            "timestamp": time.time()
        }
    }
    
    return ("OK", action)


def handle_invoices(message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Обрабатывает команду /invoices."""
    # T-Bank API не предоставляет метод для получения списка счетов
    # Доступны только: POST /api/v1/invoice/send (создание) и webhook для статуса
    return ("ℹ️ Список счетов недоступен через T-Bank API.\n\nДоступные функции:\n• Создание счета через /invoice\n• Получение статуса счета через /invoice <invoice_id>", None)


def handle_ship_paid(message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int], invoice_id_str: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Обрабатывает команду /ship_paid <invoice_id>."""
    if not invoice_id_str or not invoice_id_str.strip():
        return ("ERR: EMPTY", None)
    
    invoice_id = invoice_id_str.strip()
    
    action = {
        "action_type": "ship_paid",
        "payload": {
            "invoice_id": invoice_id
        },
        "source": "command:/ship_paid",
        "metadata": {
            "chat_id": chat_id,
            "user_id": user_id,
            "timestamp": time.time()
        }
    }
    
    return ("OK", action)


def handle_auto_ship(message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Обрабатывает команду /auto_ship."""
    action = {
        "action_type": "auto_ship_all_paid",
        "payload": {},
        "source": "command:/auto_ship",
        "metadata": {
            "chat_id": chat_id,
            "user_id": user_id,
            "timestamp": time.time()
        }
    }
    return ("⏳ Обрабатываю оплаченные счета...", action)


def handle_pay(message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int], amount_str: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Обрабатывает команду /pay <amount>."""
    if not amount_str or not amount_str.strip():
        return ("ERR: EMPTY", None)
    
    amount_str = amount_str.strip()
    
    try:
        amount = float(amount_str)
        if amount <= 0:
            return ("ERR: INVALID AMOUNT", None)
    except (ValueError, TypeError):
        return ("ERR: INVALID AMOUNT", None)
    
    action = {
        "action_type": "tbank_payment",
        "payload": {
            "amount": amount,
            "currency": "RUB"
        },
        "source": "command:/pay",
        "metadata": {
            "chat_id": chat_id,
            "user_id": user_id,
            "timestamp": time.time()
        }
    }
    
    return ("OK", action)


def handle_ship(message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int], ship_params_str: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Обрабатывает команду /ship с pipe-форматом."""
    if not ship_params_str or not ship_params_str.strip():
        return ("ERR: EMPTY", None)
    
    parts = [p.strip() for p in ship_params_str.split(" | ")]
    
    if len(parts) != 10:
        return ("ERR: BAD FORMAT", None)
    
    order_id, tariff_code_str, to_city, to_address, recipient_name, recipient_phone, weight_str, length_str, width_str, height_str = parts
    
    if not order_id or len(order_id) > 64:
        if not order_id:
            return ("ERR: EMPTY", None)
        return ("ERR: TOO LONG", None)
    
    if not tariff_code_str or not to_city or not to_address or not recipient_name or not recipient_phone:
        return ("ERR: BAD FORMAT", None)
    
    try:
        tariff_code = int(tariff_code_str)
    except ValueError:
        return ("ERR: BAD FORMAT", None)
    
    try:
        weight = float(weight_str)
        length = float(length_str)
        width = float(width_str)
        height = float(height_str)
        
        if weight <= 0 or length <= 0 or width <= 0 or height <= 0:
            return ("ERR: INVALID DIMENSIONS", None)
    except ValueError:
        return ("ERR: INVALID DIMENSIONS", None)
    
    action = {
        "action_type": "cdek_shipment",
        "payload": {
            "order_id": order_id,
            "type": 1,
            "tariff_code": tariff_code,
            "from_location": {
                "code": CDEK_FROM_LOCATION_CODE
            },
            "to_location": {
                "city": to_city,
                "address": to_address
            },
            "recipient": {
                "name": recipient_name,
                "phones": [{"number": recipient_phone}]
            },
            "sender": {
                "company": CDEK_SENDER_COMPANY,
                "phones": [{"number": CDEK_SENDER_PHONE}],
                "address": CDEK_SENDER_ADDRESS
            },
            "packages": [{
                "weight": int(weight),
                "length": int(length),
                "width": int(width),
                "height": int(height)
            }]
        },
        "source": "command:/ship",
        "metadata": {
            "chat_id": chat_id,
            "user_id": user_id,
            "timestamp": time.time()
        }
    }
    
    return ("OK", action)


# Command Router
COMMAND_ROUTER = {
    "/start": {
        "handler": handle_start,
        "requires_acl": False,
        "log_event": "start_command_received"
    },
    "/health": {
        "handler": handle_health,
        "requires_acl": False,
        "log_event": "health_command_received"
    },
    "/ping": {
        "handler": handle_ping,
        "requires_acl": False,
        "log_event": "ping_command_received"
    },
    "/help": {
        "handler": handle_help,
        "requires_acl": False,
        "log_event": "help_command_received"
    },
    "/echo": {
        "handler": handle_echo,
        "requires_acl": False,
        "log_event": "echo_command_received",
        "pattern": "startswith"
    },
    "/whoami": {
        "handler": handle_whoami,
        "requires_acl": False,
        "log_event": "whoami_command_received"
    },
    "/admin": {
        "handler": handle_admin,
        "requires_acl": True,
        "log_event": "admin_command_received",
        "forbidden_log": "admin_forbidden"
    },
    "/stats": {
        "handler": handle_stats,
        "requires_acl": True,
        "log_event": "stats_command_received",
        "forbidden_log": "stats_forbidden"
    },
    "/pay": {
        "handler": handle_pay,
        "requires_acl": True,
        "log_event": "pay_command_received",
        "forbidden_log": "pay_forbidden",
        "pattern": "startswith"
    },
    "/ship": {
        "handler": handle_ship,
        "requires_acl": True,
        "log_event": "ship_command_received",
        "forbidden_log": "ship_forbidden",
        "pattern": "startswith"
    },
    "/invoice": {
        "handler": handle_invoice,
        "requires_acl": True,
        "log_event": "invoice_command_received",
        "forbidden_log": "invoice_forbidden",
        "pattern": "startswith"
    },
    "/invoices": {
        "handler": handle_invoices,
        "requires_acl": True,
        "log_event": "invoices_command_received",
        "forbidden_log": "invoices_forbidden"
    },
    "/ship_paid": {
        "handler": handle_ship_paid,
        "requires_acl": True,
        "log_event": "ship_paid_command_received",
        "forbidden_log": "ship_paid_forbidden",
        "pattern": "startswith"
    },
    "/auto_ship": {
        "handler": handle_auto_ship,
        "requires_acl": True,
        "log_event": "auto_ship_command_received",
        "forbidden_log": "auto_ship_forbidden"
    },
    "/build": {
        "handler": handle_build,
        "requires_acl": False,
        "log_event": "build_command_received"
    },
    "/export": {
        "handler": handle_export,
        "requires_acl": True,
        "log_event": "export_command_received",
        "forbidden_log": "export_forbidden",
        "pattern": "startswith"
    }
}


def route_command(text: str, message: Dict[str, Any], chat_id: Optional[int], user_id: Optional[int]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Маршрутизирует команду к соответствующему хэндлеру.
    
    Returns:
        tuple: (response_text, optional_action)
    """
    if not text or not text.startswith("/"):
        return (None, None)
    
    # PASS 1: Точное совпадение (exact match)
    route = COMMAND_ROUTER.get(text)
    if route:
        # #region agent log
        debug_log("D", "telegram_router.py:550", "Command matched (exact)", {"text": text, "requires_acl": route["requires_acl"], "user_id": user_id, "user_allowed": user_id in ALLOWED_USER_IDS if user_id else False})
        # #endregion
        
        # ACL проверка
        if route["requires_acl"]:
            if user_id is None or user_id not in ALLOWED_USER_IDS:
                # #region agent log
                debug_log("F", "telegram_router.py:554", "ACL denied", {"text": text, "user_id": user_id, "allowed_users": list(ALLOWED_USER_IDS)})
                # #endregion
                return ("ERR: FORBIDDEN", None)
        
        # Вызов хэндлера
        handler_result = route["handler"](message, chat_id, user_id)
        
        # #region agent log
        debug_log("D", "telegram_router.py:558", "Handler executed", {"text": text, "response_text": handler_result[0][:50] if isinstance(handler_result, tuple) and handler_result[0] else str(handler_result)[:50], "has_action": isinstance(handler_result, tuple) and bool(handler_result[1])})
        # #endregion
        
        # Обработка результата хэндлера
        if isinstance(handler_result, tuple) and len(handler_result) == 2:
            response_text, optional_action = handler_result
        else:
            response_text = handler_result
            optional_action = None
        
        log_event("command_routed", {
            "matched_route_key": text,
            "pattern": "exact",
            "text": text
        })
        
        return (response_text, optional_action)
    
    # PASS 2: startswith match (только для команд с pattern="startswith")
    for command, route in COMMAND_ROUTER.items():
        if route.get("pattern") == "startswith" and text.startswith(command):
            # Извлечение параметров
            param_str = text[len(command):].strip()
            
            # ACL проверка
            if route["requires_acl"]:
                if user_id is None or user_id not in ALLOWED_USER_IDS:
                    return ("ERR: FORBIDDEN", None)
            
            # Вызов хэндлера с параметром
            handler_result = route["handler"](message, chat_id, user_id, param_str)
            
            # Обработка результата хэндлера
            if isinstance(handler_result, tuple) and len(handler_result) == 2:
                response_text, optional_action = handler_result
            else:
                response_text = handler_result
                optional_action = None
            
            log_event("command_routed", {
                "matched_route_key": command,
                "pattern": "startswith",
                "text": text
            })
            
            return (response_text, optional_action)
    
    # Команда не найдена
    log_event("command_unknown", {
        "text": text
    })
    
    return (None, None)


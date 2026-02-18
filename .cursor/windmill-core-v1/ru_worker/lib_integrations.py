#!/usr/bin/env python3
"""
Library для интеграций (T-Bank, CDEK)
Общие функции для использования в worker_dispatch и других скриптах.
"""

import json
import time
import sys
import requests
from typing import Dict, Any, Optional, Tuple


def log_event(event: str, data: Dict[str, Any]) -> None:
    """Structured logging в stdout."""
    log_entry = {
        "event": event,
        "timestamp": time.time(),
        **data
    }
    print(json.dumps(log_entry), flush=True)


def execute_tbank_payment(config, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Выполняет реальный платеж через T-Bank API.
    
    Args:
        payload: dict с amount, currency
    
    Returns:
        dict: Результат выполнения
    """
    try:
        tbank_api_url = config.tbank_api_url or "https://api.tbank.ru/v1/payments"
        response = requests.post(
            tbank_api_url,
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        
        return {
            "status": "success",
            "response": result
        }
    except requests.Timeout:
        return {
            "status": "error",
            "error": "Request timeout"
        }
    except requests.HTTPError as e:
        return {
            "status": "error",
            "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        }
    except requests.RequestException as e:
        return {
            "status": "error",
            "error": str(e)
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Unexpected error: {str(e)}"
        }


def execute_tbank_invoice_status(config, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Выполняет реальный запрос статуса счёта через T-Bank API.
    
    Args:
        payload: dict с invoice_id
    
    Returns:
        dict: Результат выполнения с полем "result_status": "paid" | "unpaid" | "not_found" | "unknown" | "error"
    """
    tbank_api_base = config.tbank_api_base
    tbank_invoice_status_path = config.tbank_invoice_status_path or ""
    tbank_api_token = config.tbank_api_token
    # #region agent log
    DEBUG_LOG_PATH = None
    try:
        from pathlib import Path
        # Вычисляем абсолютный путь относительно корня проекта
        current_file = Path(__file__).resolve()
        # lib_integrations.py находится в windmill-core-v1/ru_worker/
        # Корень проекта - это parent.parent.parent (windmill-core-v1 -> корень)
        project_root = current_file.parent.parent.parent
        DEBUG_LOG_PATH = project_root / ".cursor" / ".cursor" / "debug.log"
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        debug_log = {
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": "E",
            "location": "lib_integrations.py:87",
            "message": "tbank_invoice_status_entry",
            "data": {
                "payload": payload,
                "has_api_base": bool(tbank_api_base),
                "has_path": bool(tbank_invoice_status_path),
                "has_token": bool(tbank_api_token),
            },
            "timestamp": int(time.time() * 1000)
        }
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(debug_log, ensure_ascii=False) + "\n")
            f.flush()
    except Exception as e:
        print(f"DEBUG LOG ERROR in tbank_invoice_status_entry: {e}", file=sys.stderr)
        if DEBUG_LOG_PATH:
            print(f"DEBUG LOG PATH was: {DEBUG_LOG_PATH}", file=sys.stderr)
    # #endregion
    # Проверка конфигурации
    if not tbank_api_base or not tbank_invoice_status_path:
        # #region agent log
        try:
            from pathlib import Path
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent
            DEBUG_LOG_PATH = project_root / ".cursor" / ".cursor" / "debug.log"
            debug_log = {
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "F",
                "location": "lib_integrations.py:98",
                "message": "tbank_config_missing",
                "data": {"api_base": tbank_api_base, "path": tbank_invoice_status_path},
                "timestamp": int(time.time() * 1000)
            }
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(debug_log, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"DEBUG LOG ERROR: {e}")
        # #endregion
        return {
            "status": "error",
            "error": "TBANK NOT CONFIGURED: TBANK_API_BASE, TBANK_INVOICE_STATUS_PATH required",
            "result_status": "error"
        }
    
    invoice_id = payload.get("invoice_id")
    if not invoice_id:
        return {
            "status": "error",
            "error": "invoice_id is required",
            "result_status": "error"
        }
    
    try:
        # Формирование URL с подстановкой invoice_id
        url_template = f"{tbank_api_base.rstrip('/')}/{tbank_invoice_status_path.lstrip('/')}"
        url = url_template.replace("{invoice_id}", invoice_id)
        
        headers = {}
        if tbank_api_token:
            headers["Authorization"] = f"Bearer {tbank_api_token}"
        # #region agent log
        try:
            from pathlib import Path
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent
            DEBUG_LOG_PATH = project_root / ".cursor" / ".cursor" / "debug.log"
            debug_log = {
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "E",
                "location": "lib_integrations.py:113",
                "message": "tbank_request_before",
                "data": {"url": url, "has_token": bool(tbank_api_token), "invoice_id": invoice_id},
                "timestamp": int(time.time() * 1000)
            }
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(debug_log, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"DEBUG LOG ERROR: {e}")
        # #endregion
        
        response = requests.get(url, headers=headers, timeout=10)
        # #region agent log
        try:
            from pathlib import Path
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent
            DEBUG_LOG_PATH = project_root / ".cursor" / ".cursor" / "debug.log"
            debug_log = {
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "E",
                "location": "lib_integrations.py:122",
                "message": "tbank_request_response",
                "data": {"status_code": response.status_code, "response_time_ms": int(response.elapsed.total_seconds() * 1000) if hasattr(response, 'elapsed') else 0},
                "timestamp": int(time.time() * 1000)
            }
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(debug_log, ensure_ascii=False) + "\n")
        except Exception as e:
            try:
                from pathlib import Path
                current_file = Path(__file__).resolve()
                project_root = current_file.parent.parent.parent
                DEBUG_LOG_PATH = project_root / ".cursor" / ".cursor" / "debug.log"
                debug_log = {
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "E",
                    "location": "lib_integrations.py:122",
                    "message": "tbank_request_error",
                    "data": {"error": str(e), "error_type": type(e).__name__},
                    "timestamp": int(time.time() * 1000)
                }
                with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(debug_log, ensure_ascii=False) + "\n")
            except Exception:
                pass
        # #endregion
        response.raise_for_status()
        result = response.json()
        
        # Определение статуса из ответа
        result_status = "unknown"
        if isinstance(result, dict):
            status = result.get("status") or result.get("invoice_status") or result.get("state")
            if status:
                status_lower = str(status).lower()
                if "paid" in status_lower or status_lower == "оплачен":
                    result_status = "paid"
                elif "unpaid" in status_lower or status_lower == "не оплачен":
                    result_status = "unpaid"
                elif "not_found" in status_lower or status_lower == "не найден":
                    result_status = "not_found"
                else:
                    result_status = status_lower
        
        return {
            "status": "success",
            "result_status": result_status,
            "response": result
        }
    except requests.Timeout:
        return {
            "status": "error",
            "error": "Request timeout",
            "result_status": "error"
        }
    except requests.HTTPError as e:
        error_text = e.response.text[:200] if e.response else str(e)
        return {
            "status": "error",
            "error": f"TBank HTTP {e.response.status_code}: {error_text}",
            "result_status": "error"
        }
    except requests.RequestException as e:
        return {
            "status": "error",
            "error": f"TBank Request error: {str(e)}",
            "result_status": "error"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"TBank Unexpected error: {str(e)}",
            "result_status": "error"
        }


def execute_tbank_invoices_list(config, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Выполняет реальный запрос списка счетов через T-Bank API.
    
    Args:
        payload: dict с limit (опционально)
    
    Returns:
        dict: Результат выполнения с полем "invoices": список счетов
    """
    # Проверка конфигурации
    tbank_api_base = config.tbank_api_base
    tbank_invoices_list_path = config.tbank_invoices_list_path or ""
    tbank_api_token = config.tbank_api_token
    if not tbank_api_base or not tbank_invoices_list_path:
        return {
            "status": "error",
            "error": "TBANK NOT CONFIGURED: TBANK_API_BASE, TBANK_INVOICES_LIST_PATH required",
            "invoices": []
        }
    
    limit = payload.get("limit", 20)
    
    try:
        url = f"{tbank_api_base.rstrip('/')}/{tbank_invoices_list_path.lstrip('/')}"
        params = {"limit": limit} if limit else {}
        
        headers = {}
        if tbank_api_token:
            headers["Authorization"] = f"Bearer {tbank_api_token}"
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        invoices = []
        if isinstance(result, list):
            for item in result[:limit]:
                invoices.append({
                    "invoice_id": item.get("invoice_id") or item.get("id") or "",
                    "status": item.get("status", "unknown")
                })
        elif isinstance(result, dict) and "invoices" in result:
            for item in result.get("invoices", [])[:limit]:
                invoices.append({
                    "invoice_id": item.get("invoice_id") or item.get("id") or "",
                    "status": item.get("status", "unknown")
                })
        elif isinstance(result, dict) and "data" in result:
            for item in result.get("data", [])[:limit]:
                invoices.append({
                    "invoice_id": item.get("invoice_id") or item.get("id") or "",
                    "status": item.get("status", "unknown")
                })
        
        return {
            "status": "success",
            "invoices": invoices,
            "count": len(invoices)
        }
    except requests.Timeout:
        return {
            "status": "error",
            "error": "Request timeout",
            "invoices": []
        }
    except requests.HTTPError as e:
        error_text = e.response.text[:200] if e.response else str(e)
        return {
            "status": "error",
            "error": f"TBank HTTP {e.response.status_code}: {error_text}",
            "invoices": []
        }
    except requests.RequestException as e:
        return {
            "status": "error",
            "error": f"TBank Request error: {str(e)}",
            "invoices": []
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"TBank Unexpected error: {str(e)}",
            "invoices": []
        }


def map_tbank_invoice_to_cdek_payload(config, invoice_id: str, invoice_data: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Маппинг данных T-Bank invoice в формат CDEK payload с валидацией.
    
    Args:
        invoice_id: str - ID счета
        invoice_data: dict - Данные из T-Bank API response
    
    Returns:
        tuple: (payload_dict, error_str)
        - Если успех: (payload, None)
        - Если ошибка: (None, "error message")
    """
    # Извлечение данных с приоритетом полей
    city = invoice_data.get("city") or invoice_data.get("delivery_city") or invoice_data.get("delivery", {}).get("city")
    address = invoice_data.get("address") or invoice_data.get("delivery_address") or invoice_data.get("delivery", {}).get("address")
    recipient_name = invoice_data.get("recipient_name") or invoice_data.get("name") or invoice_data.get("customer_name")
    phone = invoice_data.get("phone") or invoice_data.get("recipient_phone") or invoice_data.get("customer_phone") or invoice_data.get("contact_phone")
    
    # Валидация обязательных полей
    validation_errors = []
    if not city:
        validation_errors.append("city")
    if not address:
        validation_errors.append("address")
    if not recipient_name:
        validation_errors.append("recipient_name")
    if not phone:
        validation_errors.append("phone")
    
    if validation_errors:
        return (None, f"Missing required fields in invoice data: {', '.join(validation_errors)}")
    
    # Габариты и вес - используем дефолты если нет данных
    weight = int(invoice_data.get("weight", 1000))
    length = int(invoice_data.get("length", 10))
    width = int(invoice_data.get("width", 10))
    height = int(invoice_data.get("height", 10))
    
    # Формирование payload
    payload = {
        "order_id": invoice_id,
        "type": 1,
        "tariff_code": 136,
        "from_location": {
            "code": config.cdek_from_location_code
        },
        "to_location": {
            "city": city,
            "address": address
        },
        "recipient": {
            "name": recipient_name,
            "phones": [{"number": phone}]
        },
        "sender": {
            "company": config.cdek_sender_company,
            "phones": [{"number": config.cdek_sender_phone}],
            "address": config.cdek_sender_address
        },
        "packages": [{
            "weight": weight,
            "length": length,
            "width": width,
            "height": height
        }]
    }
    
    return (payload, None)


def execute_cdek_shipment(config, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Выполняет реальное создание накладной через CDEK API v2.
    
    Args:
        payload: dict с order_id, type, tariff_code, from_location, to_location, recipient, sender, packages
    
    Returns:
        dict: Результат выполнения
    """
    cdek_api_base = config.cdek_api_base or ""
    cdek_client_id = config.cdek_client_id
    cdek_client_secret = config.cdek_client_secret
    cdek_sender_company = config.cdek_sender_company or ""
    cdek_sender_phone = config.cdek_sender_phone or ""
    cdek_sender_address = config.cdek_sender_address or ""
    cdek_oauth_path = config.cdek_oauth_path or ""
    cdek_orders_path = config.cdek_orders_path or ""
    # #region agent log
    try:
        from pathlib import Path
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent.parent
        DEBUG_LOG_PATH = project_root / ".cursor" / ".cursor" / "debug.log"
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        debug_log = {
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": "C",
            "location": "lib_integrations.py:328",
            "message": "cdek_shipment_entry",
            "data": {
                "payload_keys": list(payload.keys()),
                "has_api_base": bool(cdek_api_base),
                "has_client_id": bool(cdek_client_id),
                "has_client_secret": bool(cdek_client_secret),
            },
            "timestamp": int(time.time() * 1000)
        }
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(debug_log, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"DEBUG LOG ERROR: {e}")
    # #endregion
    # Проверка конфигурации
    if not cdek_api_base or not cdek_client_id or not cdek_client_secret:
        # #region agent log
        try:
            from pathlib import Path
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent
            DEBUG_LOG_PATH = project_root / ".cursor" / ".cursor" / "debug.log"
            debug_log = {
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "C",
                "location": "lib_integrations.py:339",
                "message": "cdek_config_missing",
                "data": {
                    "api_base": cdek_api_base,
                    "has_client_id": bool(cdek_client_id),
                    "has_client_secret": bool(cdek_client_secret),
                },
                "timestamp": int(time.time() * 1000)
            }
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(debug_log, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"DEBUG LOG ERROR: {e}")
        # #endregion
        return {
            "status": "error",
            "error": "CDEK NOT CONFIGURED: CDEK_API_BASE, CDEK_CLIENT_ID, CDEK_CLIENT_SECRET required"
        }
    
    if not cdek_sender_company or not cdek_sender_phone or not cdek_sender_address:
        return {
            "status": "error",
            "error": "CDEK NOT CONFIGURED: CDEK_SENDER_COMPANY, CDEK_SENDER_PHONE, CDEK_SENDER_ADDRESS required"
        }
    
    if not cdek_oauth_path or not cdek_orders_path:
        return {
            "status": "error",
            "error": "CDEK NOT CONFIGURED: CDEK_OAUTH_PATH, CDEK_ORDERS_PATH required"
        }
    
    try:
        # Шаг 1: Получение access token (OAuth client_credentials)
        oauth_url = f"{cdek_api_base.rstrip('/')}/{cdek_oauth_path.lstrip('/')}"
        oauth_payload = {
            "grant_type": "client_credentials",
            "client_id": cdek_client_id,
            "client_secret": cdek_client_secret
        }
        # #region agent log
        try:
            from pathlib import Path
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent
            DEBUG_LOG_PATH = project_root / ".cursor" / ".cursor" / "debug.log"
            debug_log = {
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "C",
                "location": "lib_integrations.py:357",
                "message": "cdek_oauth_before",
                "data": {
                    "oauth_url": oauth_url,
                    "has_client_id": bool(cdek_client_id),
                    "has_client_secret": bool(cdek_client_secret),
                },
                "timestamp": int(time.time() * 1000)
            }
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(debug_log, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"DEBUG LOG ERROR: {e}")
        # #endregion
        
        oauth_response = requests.post(
            oauth_url,
            json=oauth_payload,
            timeout=10
        )
        # #region agent log
        try:
            from pathlib import Path
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent
            DEBUG_LOG_PATH = project_root / ".cursor" / ".cursor" / "debug.log"
            debug_log = {
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "C",
                "location": "lib_integrations.py:371",
                "message": "cdek_oauth_response",
                "data": {"status_code": oauth_response.status_code, "has_access_token": "access_token" in oauth_response.text},
                "timestamp": int(time.time() * 1000)
            }
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(debug_log, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"DEBUG LOG ERROR: {e}")
        # #endregion
        oauth_response.raise_for_status()
        oauth_data = oauth_response.json()
        access_token = oauth_data.get("access_token")
        
        if not access_token:
            return {
                "status": "error",
                "error": "CDEK OAuth failed: no access_token"
            }
        
        # Шаг 2: Создание накладной
        orders_url = f"{cdek_api_base.rstrip('/')}/{cdek_orders_path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        cdek_body = payload
        # #region agent log
        try:
            from pathlib import Path
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent
            DEBUG_LOG_PATH = project_root / ".cursor" / ".cursor" / "debug.log"
            debug_log = {
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "D",
                "location": "lib_integrations.py:381",
                "message": "cdek_shipment_before",
                "data": {"orders_url": orders_url, "has_access_token": bool(access_token), "payload_keys": list(payload.keys())},
                "timestamp": int(time.time() * 1000)
            }
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(debug_log, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"DEBUG LOG ERROR: {e}")
        # #endregion
        
        response = requests.post(
            orders_url,
            json=cdek_body,
            headers=headers,
            timeout=30
        )
        # #region agent log
        try:
            from pathlib import Path
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent
            DEBUG_LOG_PATH = project_root / ".cursor" / ".cursor" / "debug.log"
            debug_log = {
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "D",
                "location": "lib_integrations.py:395",
                "message": "cdek_shipment_response",
                "data": {"status_code": response.status_code, "response_preview": response.text[:200]},
                "timestamp": int(time.time() * 1000)
            }
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(debug_log, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"DEBUG LOG ERROR: {e}")
        # #endregion
        response.raise_for_status()
        result = response.json()
        
        return {
            "status": "success",
            "response": result
        }
    except requests.Timeout:
        return {
            "status": "error",
            "error": "CDEK Request timeout"
        }
    except requests.HTTPError as e:
        error_text = e.response.text[:500] if e.response else str(e)
        return {
            "status": "error",
            "error": f"CDEK HTTP {e.response.status_code}: {error_text}"
        }
    except requests.RequestException as e:
        return {
            "status": "error",
            "error": f"CDEK Request error: {str(e)}"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"CDEK Unexpected error: {str(e)}"
        }


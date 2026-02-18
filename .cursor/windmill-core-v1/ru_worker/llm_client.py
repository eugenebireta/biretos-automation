"""
RFQ Execution Core Business v1 - USA LLM Gateway Client
Placeholder клиент для вызова LLM API на USA-VPS

ВАЖНО: Это интерфейсный клиент на RU, который вызывает внешний endpoint.
USA-VPS не инициирует соединения к RU-VPS.
"""

from typing import Dict, Any, Optional

import httpx

from config import get_config

_CONFIG = get_config()

# Конфигурация
USA_LLM_BASE_URL = _CONFIG.usa_llm_base_url or "https://usa-llm-gateway.example.com"
USA_LLM_API_KEY = _CONFIG.usa_llm_api_key or ""
LLM_TIMEOUT = _CONFIG.llm_timeout_seconds or 30


def parse_rfq_with_llm(raw_text: str, language: str = "auto") -> Optional[Dict[str, Any]]:
    """
    Вызывает LLM API для парсинга RFQ текста
    
    Args:
        raw_text: Исходный текст для парсинга
        language: Язык текста (auto, eng, rus)
    
    Returns:
        Dict с результатами парсинга или None при ошибке
    """
    if not USA_LLM_API_KEY:
        return None
    
    try:
        client = httpx.Client(timeout=LLM_TIMEOUT)
        
        payload = {
            "text": raw_text,
            "language": language,
            "task": "rfq_parse"
        }
        
        headers = {
            "Authorization": f"Bearer {USA_LLM_API_KEY}",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            f"{USA_LLM_BASE_URL}/api/v1/parse",
            json=payload,
            headers=headers
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            # Логируем ошибку, но не падаем
            print(f"LLM API error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        # При любой ошибке возвращаем None (fallback на deterministic parser)
        print(f"LLM client error: {e}")
        return None
    finally:
        if 'client' in locals():
            client.close()























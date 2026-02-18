"""
HTTP forwarder для проксирования webhook в n8n
"""

import asyncio
import hmac
import hashlib
import base64
from typing import Dict, Any, Optional, Tuple
import aiohttp
from datetime import datetime
import uuid


class ForwarderError(Exception):
    """Ошибка при проксировании в n8n"""
    pass


class N8NForwarder:
    """Проксирование webhook в n8n с HMAC подписью"""
    
    def __init__(self, n8n_webhook_url: str, webhook_secret: str, timeout: int = 10):
        """
        Args:
            n8n_webhook_url: URL webhook n8n (полный путь)
            webhook_secret: Секрет для HMAC подписи
            timeout: Timeout запроса в секундах
        """
        self.n8n_webhook_url = n8n_webhook_url.rstrip("/")
        self.webhook_secret = webhook_secret
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        
    def _generate_signature(self, payload_body: str) -> str:
        """
        Генерация HMAC-SHA256 подписи для n8n webhook
        
        Args:
            payload_body: Тело запроса (JSON строка)
            
        Returns:
            Base64 encoded HMAC signature
        """
        signature = hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload_body.encode("utf-8"),
            hashlib.sha256
        ).digest()
        
        return base64.b64encode(signature).decode("utf-8")
    
    def _prepare_payload(self, raw_payload: Dict[str, Any], request_id: str, source_ip: str) -> Dict[str, Any]:
        """
        Подготовка нормализованного payload для n8n
        
        Args:
            raw_payload: Оригинальный payload от Т-Банка
            request_id: UUID запроса для трейсинга
            source_ip: IP адрес источника
            
        Returns:
            Нормализованный payload
        """
        return {
            "event_type": "invoice_paid",
            "source": "tbank",
            "invoice_id": raw_payload.get("invoice_id"),
            "status": raw_payload.get("status", "PAID"),
            "amount": raw_payload.get("amount"),
            "currency": raw_payload.get("currency", "RUB"),
            "timestamp": raw_payload.get("timestamp") or datetime.utcnow().isoformat() + "Z",
            "metadata": raw_payload.get("metadata", {}),
            "gateway": {
                "request_id": request_id,
                "received_at": datetime.utcnow().isoformat() + "Z",
                "source_ip": source_ip
            },
            "raw_payload": raw_payload
        }
    
    async def forward(
        self,
        raw_payload: Dict[str, Any],
        request_id: str,
        source_ip: str,
        max_retries: int = 2,
        retry_delays: list = None
    ) -> Tuple[int, Optional[str]]:
        """
        Проксирование webhook в n8n с retry
        
        Args:
            raw_payload: Оригинальный payload от Т-Банка
            request_id: UUID запроса
            source_ip: IP адрес источника
            max_retries: Максимальное количество попыток
            retry_delays: Задержки между попытками в секундах (по умолчанию [1, 3])
            
        Returns:
            (status_code, error_message)
            
        Raises:
            ForwarderError: При критических ошибках
        """
        if retry_delays is None:
            retry_delays = [1, 3]
        
        # Подготовка payload
        normalized_payload = self._prepare_payload(raw_payload, request_id, source_ip)
        
        # Сериализация в JSON
        import json
        payload_body = json.dumps(normalized_payload, ensure_ascii=False)
        
        # Генерация подписи
        signature = self._generate_signature(payload_body)
        
        # Подготовка headers
        headers = {
            "Content-Type": "application/json",
            "X-n8n-signature": signature,
            "X-Gateway-Request-ID": request_id,
            "X-Gateway-Source": "tbank-webhook-gateway"
        }
        
        # Выполнение запроса с retry
        last_error = None
        last_status = None
        
        for attempt in range(max_retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    async with session.post(
                        self.n8n_webhook_url,
                        data=payload_body,
                        headers=headers
                    ) as response:
                        status_code = response.status
                        last_status = status_code
                        
                        # 200-299: успех
                        if 200 <= status_code < 300:
                            return status_code, None
                        
                        # 400-499: ошибка клиента (не ретраить)
                        if 400 <= status_code < 500:
                            error_text = await response.text()
                            return status_code, f"Client error: {error_text[:200]}"
                        
                        # 500+: ошибка сервера (ретраить)
                        if attempt < max_retries:
                            delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                            await asyncio.sleep(delay)
                            continue
                        else:
                            error_text = await response.text()
                            return status_code, f"Server error after {max_retries} retries: {error_text[:200]}"
                            
            except asyncio.TimeoutError:
                last_error = "Timeout waiting for n8n response"
                if attempt < max_retries:
                    delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise ForwarderError(f"Timeout after {max_retries} retries: {last_error}")
                    
            except aiohttp.ClientError as e:
                last_error = str(e)
                if attempt < max_retries:
                    delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise ForwarderError(f"Client error after {max_retries} retries: {last_error}")
        
        # Если дошли сюда, значит все попытки исчерпаны
        return last_status or 0, last_error or "Unknown error"









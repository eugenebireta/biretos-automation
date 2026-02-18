"""
Клиент для обращения к Perplexity через OpenRouter.

Гарантирует, что метод lookup никогда не выбрасывает исключения и
возвращает безопасный словарь с данными и «raw»-ответом.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx


PROMPT_TEMPLATE = """You are a product identification AI.

Given BRAND and PART NUMBER:
Brand: {brand}
Part number: {part_number}

1. Correct the part number if incorrect.
2. Identify the exact model name.
3. Identify product type (e.g., softstarter, sensor, PLC module).
4. Provide ONE real product photo URL (jpg/png/webp).
   Requirements:
   * Real product photo
   * White or neutral background
   * No datasheets
   * No diagrams
   * No drawings
   * No renders
   * No packaging
   * Prefer HD image > 600px
5. Write a concise 1–2 sentence technical description.

Return STRICT JSON in this structure:
{{
  "corrected_part_number": "...",
  "model": "...",
  "product_type": "...",
  "image_url": "...",
  "description": "..."
}}
"""


DEFAULT_RESULT: Dict[str, Optional[str]] = {
    "corrected_part_number": None,
    "model": None,
    "product_type": None,
    "image_url": None,
    "description": None,
    "raw": None,
}


@dataclass(slots=True)
class PerplexityClient:
    """
    Легковесный клиент Perplexity, работающий поверх OpenRouter.
    """

    api_key: str
    model: str = "perplexity/sonar"
    timeout: float = 30.0
    _endpoint: str = field(
        default="https://openrouter.ai/api/v1/chat/completions", init=False, repr=False
    )

    async def lookup(self, brand: str, part_number: str) -> Dict[str, Any]:
        """
        Выполняет запрос идентификации продукта.

        Возвращает словарь с полями:
        corrected_part_number, model, product_type, image_url, description, raw.
        """

        result = dict(DEFAULT_RESULT)

        if not self.api_key:
            result["raw"] = {"error": "missing_api_key"}
            return result

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a reliable assistant that only returns valid JSON.",
                },
                {"role": "user", "content": PROMPT_TEMPLATE.format(brand=brand, part_number=part_number)},
            ],
            "temperature": 0.0,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self._endpoint, headers=headers, json=payload)
        except Exception as exc:  # noqa: BLE001
            result["raw"] = {"error": "request_failed", "detail": str(exc)}
            return result

        data: Dict[str, Any]
        try:
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            data = {"error": "invalid_json", "detail": str(exc), "text": response.text}

        result["raw"] = data

        content = self._extract_content(data)
        parsed = self._extract_json(content) if content else None

        if parsed:
            result.update(
                {
                    "corrected_part_number": self._safe_get(parsed, "corrected_part_number"),
                    "model": self._safe_get(parsed, "model"),
                    "product_type": self._safe_get(parsed, "product_type"),
                    "image_url": self._validate_image_url(self._safe_get(parsed, "image_url")),
                    "description": self._safe_get(parsed, "description"),
                }
            )
        return result

    @staticmethod
    def _safe_get(payload: Dict[str, Any], key: str) -> Optional[str]:
        value = payload.get(key)
        return value if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _extract_content(data: Dict[str, Any]) -> Optional[str]:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return None

        message = choices[0].get("message", {})
        content = message.get("content")

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        texts.append(text)
            return "\n".join(texts) if texts else None

        return None

    @staticmethod
    def _extract_json(content: str) -> Optional[Dict[str, Any]]:
        if not content:
            return None

        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", content):
            start = match.start()
            try:
                obj, _ = decoder.raw_decode(content[start:])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
        return None

    @staticmethod
    def _validate_image_url(image_url: Optional[str]) -> Optional[str]:
        if not image_url or not isinstance(image_url, str):
            return None

        pattern = re.compile(r"\.(?:jpe?g|png|webp)(?:\?.*)?$", re.IGNORECASE)
        return image_url if pattern.search(image_url.strip()) else None


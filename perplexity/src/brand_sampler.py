"""
Сборщик примеров товаров для указанного бренда через Perplexity (OpenRouter).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

from .perplexity_client import PerplexityClient

PROMPT_TEMPLATE = """You are a product sourcing AI.

Task: find {count} real products manufactured by the brand "{brand}".
For each product provide:
  - part_number: exact manufacturer part number
  - model: human-readable model or marketing name
  - product_type: short classification (e.g., softstarter, PLC module)
  - image_url: one URL to a real product photo (white/neutral background, no renders, HD > 500px, direct jpg/png/webp)
  - description: concise 1-2 sentence technical summary

Return STRICT JSON array using this schema (no markdown, no text outside JSON):
[
  {{
    "part_number": "...",
    "model": "...",
    "product_type": "...",
    "image_url": "...",
    "description": "..."
  }},
  ...
]
"""

_ENV_LOADED = False
_MIN_COUNT = 1
_MAX_COUNT = 25


def _ensure_env_loaded() -> None:
    global _ENV_LOADED  # noqa: PLW0603
    if not _ENV_LOADED:
        load_dotenv()
        _ENV_LOADED = True


async def sample_brand_products(brand: str, count: int) -> List[Dict[str, Optional[str]]]:
    """
    Возвращает список товаров бренда, найденных через Perplexity.
    """

    clean_brand = (brand or "").strip()
    if not clean_brand:
        return []

    desired_count = max(_MIN_COUNT, min(count or _MIN_COUNT, _MAX_COUNT))

    _ensure_env_loaded()
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return []

    client = PerplexityClient(api_key=api_key)

    payload = {
        "model": client.model,
        "messages": [
            {
                "role": "system",
                "content": "You are a precise sourcing assistant that only returns valid JSON arrays.",
            },
            {
                "role": "user",
                "content": PROMPT_TEMPLATE.format(brand=clean_brand, count=desired_count),
            },
        ],
        "temperature": 0.2,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=client.timeout) as http_client:
            response = await http_client.post(client._endpoint, headers=headers, json=payload)
    except Exception:  # noqa: BLE001
        return []

    try:
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        data = {"error": "invalid_json", "detail": str(exc), "text": response.text}

    content = PerplexityClient._extract_content(data)  # type: ignore[attr-defined]
    structure = _extract_json_structure(content)

    if isinstance(structure, list):
        normalized: List[Dict[str, Optional[str]]] = []
        for item in structure:
            normalized_item = _normalize_item(item)
            if normalized_item:
                normalized.append(normalized_item)
        return normalized[:desired_count]

    if isinstance(structure, dict):
        single = _normalize_item(structure)
        return [single] if single else []

    return []


def _extract_json_structure(content: Optional[str]) -> Optional[Any]:
    if not content:
        return None

    decoder = json.JSONDecoder()
    for idx, char in enumerate(content):
        if char not in "{[":
            continue
        try:
            obj, _ = decoder.raw_decode(content[idx:])
            if isinstance(obj, (dict, list)):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _normalize_item(item: Any) -> Optional[Dict[str, Optional[str]]]:
    if not isinstance(item, dict):
        return None

    part_number = _safe_str(item.get("part_number"))
    if not part_number:
        return None

    model = _safe_str(item.get("model"))
    product_type = _safe_str(item.get("product_type"))
    description = _safe_str(item.get("description"))
    image_url = PerplexityClient._validate_image_url(_safe_str(item.get("image_url")))  # type: ignore[attr-defined]

    return {
        "part_number": part_number,
        "model": model,
        "product_type": product_type,
        "image_url": image_url,
        "description": description,
    }


def _safe_str(value: Any) -> Optional[str]:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return None



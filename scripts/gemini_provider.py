"""gemini_provider.py — Gemini-first provider for the photo pipeline.

Replaces SerpAPI (search) and OpenAI (extraction + vision) with:
1. DuckDuckGo for page search (free, unlimited)
2. Gemini 2.5 Flash for price extraction (structured JSON output)
3. Gemini 2.5 Flash for vision verdict (multimodal image+text)
4. Gemini 2.5 Flash with Google Search grounding for identity confirmation

All calls go through an adaptive rate limiter (15 RPM free tier).
Raw responses cached to disk for debugging and replay.

Usage:
    from gemini_provider import (
        GeminiChatAdapter,
        GeminiSearchAdapter,
        create_gemini_adapters,
    )
    search_adapter, chat_adapter = create_gemini_adapters()
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_DOWNLOADS = _ROOT / "downloads"
_CACHE_DIR = _ROOT / "shadow_log" / "gemini_cache"

GEMINI_MODEL = "gemini-2.5-flash"

# Gemini free tier: 15 RPM, 500 RPD for grounded search, 1500 RPD for plain
_GEMINI_RPM = 15
_DEFAULT_SLEEP = 60.0 / _GEMINI_RPM  # ~4s between calls
_BACKOFF_SLEEP = 10.0  # on 429
_MAX_RETRIES = 3

# Price extraction structured output schema
# Gemini response_schema uses OpenAPI types, not JSON Schema arrays.
# Nullable fields use base type and are omitted from `required`.
PRICE_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "pn_found": {"type": "boolean"},
        "pn_exact_confirmed": {"type": "boolean"},
        "category_mismatch": {"type": "boolean"},
        "page_product_class": {"type": "string"},
        "price_per_unit": {"type": "number"},
        "currency": {"type": "string"},
        "offer_qty": {"type": "integer"},
        "offer_unit_basis": {
            "type": "string",
            "enum": ["piece", "pack", "kit", "unknown"],
        },
        "price_status": {
            "type": "string",
            "enum": ["public_price", "rfq_only", "hidden_price", "no_price_found"],
        },
        "stock_status": {
            "type": "string",
            "enum": ["in_stock", "backorder", "rfq", "unknown"],
        },
        "lead_time_detected": {"type": "boolean"},
        "quote_cta_url": {"type": "string"},
        "suffix_conflict": {"type": "boolean"},
        "price_confidence": {"type": "integer"},
        "source_type": {
            "type": "string",
            "enum": ["official", "authorized_distributor", "ru_b2b", "other"],
        },
    },
    "required": [
        "pn_found", "pn_exact_confirmed", "category_mismatch",
        "page_product_class",
        "offer_unit_basis", "price_status", "stock_status",
        "lead_time_detected", "suffix_conflict", "price_confidence",
        "source_type",
    ],
}

# Vision verdict structured output schema
VISION_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["KEEP", "REJECT"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
}


# ── Rate limiter ──────────────────────────────────────────────────────────────

class AdaptiveRateLimiter:
    """Simple adaptive rate limiter for Gemini free tier.

    Sleeps _DEFAULT_SLEEP between calls. On 429, sleeps _BACKOFF_SLEEP.
    Tracks RPD budget for grounded vs plain calls.
    """

    def __init__(
        self,
        rpm: int = _GEMINI_RPM,
        sleep_fn=time.sleep,
        monotonic_fn=time.monotonic,
    ):
        self._rpm = rpm
        self._min_interval = 60.0 / rpm
        self._sleep_fn = sleep_fn
        self._monotonic_fn = monotonic_fn
        self._last_call: float = 0.0
        self._daily_plain: int = 0
        self._daily_grounded: int = 0
        self._consecutive_429: int = 0

    @property
    def daily_plain(self) -> int:
        return self._daily_plain

    @property
    def daily_grounded(self) -> int:
        return self._daily_grounded

    def acquire(self, grounded: bool = False) -> None:
        """Wait until next call is safe."""
        now = self._monotonic_fn()
        elapsed = now - self._last_call
        wait = self._min_interval - elapsed
        if self._consecutive_429 > 0:
            wait = max(wait, _BACKOFF_SLEEP)
        if wait > 0:
            self._sleep_fn(wait)
        self._last_call = self._monotonic_fn()
        if grounded:
            self._daily_grounded += 1
        else:
            self._daily_plain += 1

    def report_429(self) -> None:
        """Report a 429 error."""
        self._consecutive_429 += 1
        log.warning(
            f"gemini_provider: 429 received (consecutive={self._consecutive_429}), "
            f"backing off {_BACKOFF_SLEEP}s"
        )
        self._sleep_fn(_BACKOFF_SLEEP * self._consecutive_429)

    def report_success(self) -> None:
        """Report a successful call, resetting 429 counter."""
        self._consecutive_429 = 0

    def get_stats(self) -> dict:
        return {
            "daily_plain": self._daily_plain,
            "daily_grounded": self._daily_grounded,
            "consecutive_429": self._consecutive_429,
        }


# Module-level rate limiter instance
_rate_limiter = AdaptiveRateLimiter()


def get_rate_limiter() -> AdaptiveRateLimiter:
    return _rate_limiter


# ── Response caching ──────────────────────────────────────────────────────────

def _cache_key(task_type: str, pn: str, content_hash: str) -> str:
    return hashlib.sha256(f"{task_type}:{pn}:{content_hash}".encode()).hexdigest()[:16]


def _save_to_cache(task_type: str, pn: str, content_hash: str, response: dict) -> None:
    """Save raw Gemini response to disk cache."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(task_type, pn, content_hash)
    path = _CACHE_DIR / f"{task_type}_{key}.json"
    try:
        path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        log.debug(f"gemini cache write failed: {exc}")


def _load_from_cache(task_type: str, pn: str, content_hash: str) -> dict | None:
    """Load cached response if exists."""
    key = _cache_key(task_type, pn, content_hash)
    path = _CACHE_DIR / f"{task_type}_{key}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


# ── DuckDuckGo search ─────────────────────────────────────────────────────────

def search_ddg(
    query: str,
    *,
    max_results: int = 8,
    region: str = "wt-wt",
) -> list[dict]:
    """Search DuckDuckGo and return candidate list compatible with step2.

    Returns list of {url, title, snippet, source_type, engine}.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            log.warning("gemini_provider: ddgs/duckduckgo-search not installed")
            return []

    results = []
    try:
        for r in DDGS().text(query, max_results=max_results, region=region):
            url = r.get("href", "")
            if not url:
                continue
            results.append({
                "url": url,
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "source_type": "other",
                "engine": "duckduckgo",
            })
    except Exception as exc:
        log.warning(f"gemini_provider: DDG search failed: {exc}")

    return results


def search_ddg_images(
    query: str,
    *,
    max_results: int = 10,
    region: str = "wt-wt",
) -> list[dict]:
    """Search DuckDuckGo for images. Returns list of {url, title, image_url, source}."""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            log.warning("gemini_provider: ddgs/duckduckgo-search not installed")
            return []

    results = []
    try:
        for r in DDGS().images(query, max_results=max_results, region=region):
            url = r.get("image", "")
            if not url:
                continue
            results.append({
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "image_url": url,
                "source": "duckduckgo_images",
            })
    except Exception as exc:
        log.warning(f"gemini_provider: DDG image search failed: {exc}")

    return results


# ── Gemini client ─────────────────────────────────────────────────────────────

def _get_gemini_client(api_key: str = ""):
    """Get or create Gemini client."""
    api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Add to downloads/.env or environment."
        )
    from google import genai
    return genai.Client(api_key=api_key)


def _is_429(exc: Exception) -> bool:
    """Check if exception is a rate limit error."""
    msg = str(exc).lower()
    return "429" in msg or "resource_exhausted" in msg or "rate" in msg


def _call_gemini_with_retry(
    client,
    *,
    model: str = GEMINI_MODEL,
    contents: Any,
    config: Any = None,
    task_type: str = "",
    pn: str = "",
    grounded: bool = False,
) -> Any:
    """Call Gemini with rate limiting and retry on 429."""
    for attempt in range(_MAX_RETRIES):
        _rate_limiter.acquire(grounded=grounded)
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            _rate_limiter.report_success()
            return response
        except Exception as exc:
            if _is_429(exc) and attempt < _MAX_RETRIES - 1:
                _rate_limiter.report_429()
                continue
            raise
    return None  # unreachable, but satisfies type checker


# ── Price extraction via Gemini ───────────────────────────────────────────────

def extract_price_gemini(
    page_text: str,
    pn: str,
    brand: str,
    expected_category: str = "",
    *,
    api_key: str = "",
) -> dict | None:
    """Extract price from page text using Gemini structured output.

    Returns parsed dict matching PRICE_EXTRACTION_SCHEMA, or None on failure.
    Uses response_mime_type="application/json" for guaranteed valid JSON.
    """
    from google.genai import types

    content_hash = hashlib.sha256(page_text[:2000].encode()).hexdigest()[:12]
    cached = _load_from_cache("price_extraction", pn, content_hash)
    if cached:
        log.debug(f"  gemini price cache hit: {pn}")
        return cached

    client = _get_gemini_client(api_key)

    prompt = f"""Ты — суровый B2B-аудитор. Извлеки коммерческие данные из текста страницы дистрибьютора.
Искомый товар: {brand} {pn}. Ожидаемый класс товара: {expected_category or "unknown"}.

Правила:
1. Игнорируй товары из блоков "Аналоги", "С этим покупают", "Похожие товары".
2. Найди точную цену и валюту. Если цена за упаковку — пересчитай за 1 штуку.
3. Проверь suffix_conflict: если на странице вариант с другим суффиксом — отметь true.
4. Определи статус цены: публичная / только RFQ / скрытая / нет цены.
5. Проверь соответствие класса товара: основной продукт должен совпадать с "{expected_category or "unknown"}".

ТЕКСТ СТРАНИЦЫ:
{page_text[:4000]}"""

    try:
        response = _call_gemini_with_retry(
            client,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PRICE_EXTRACTION_SCHEMA,
                temperature=0,
                max_output_tokens=512,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
            task_type="price_extraction",
            pn=pn,
        )

        text = response.text or ""
        parsed = json.loads(text)
        _save_to_cache("price_extraction", pn, content_hash, parsed)
        return parsed
    except json.JSONDecodeError:
        log.warning(f"  gemini price JSON parse failed for {pn}")
        return None
    except Exception as exc:
        log.warning(f"  gemini price extraction failed for {pn}: {exc}")
        return None


# ── Vision verdict via Gemini ─────────────────────────────────────────────────

def vision_verdict_gemini(
    image_path: str,
    pn: str,
    name: str,
    *,
    api_key: str = "",
) -> dict:
    """Evaluate product image using Gemini multimodal.

    Returns {"verdict": "KEEP"/"REJECT", "reason": "..."}.
    Falls back to KEEP on error (same as existing pipeline behavior).
    """
    from google.genai import types

    img_path = Path(image_path)
    if not img_path.exists():
        return {"verdict": "REJECT", "reason": "image file not found"}

    content_hash = hashlib.sha256(img_path.read_bytes()[:4096]).hexdigest()[:12]
    cached = _load_from_cache("vision_verdict", pn, content_hash)
    if cached:
        log.debug(f"  gemini vision cache hit: {pn}")
        return cached

    client = _get_gemini_client(api_key)

    img_bytes = img_path.read_bytes()
    b64_data = base64.b64encode(img_bytes).decode()

    # Detect mime type
    mime = "image/jpeg"
    suffix = img_path.suffix.lower()
    if suffix == ".png":
        mime = "image/png"
    elif suffix == ".webp":
        mime = "image/webp"

    prompt_text = (
        f"Товар: {name} | Артикул: {pn} | Бренд: Honeywell\n\n"
        "REJECT если: явно не тот товар (человек, интерьер, документ, скриншот, "
        "логотип без предмета) или полная нечитаемая каша.\n"
        "KEEP если товар угадывается — даже с водяным знаком, плохим фоном, низким качеством."
    )

    contents = [
        types.Part.from_text(text=prompt_text),
        types.Part.from_bytes(data=img_bytes, mime_type=mime),
    ]

    try:
        response = _call_gemini_with_retry(
            client,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VISION_VERDICT_SCHEMA,
                temperature=0,
                max_output_tokens=256,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
            task_type="vision_verdict",
            pn=pn,
        )

        text = response.text or ""
        parsed = json.loads(text)
        result = {
            "verdict": parsed.get("verdict", "KEEP"),
            "reason": parsed.get("reason", ""),
        }
        _save_to_cache("vision_verdict", pn, content_hash, result)
        return result
    except Exception as exc:
        log.warning(f"  gemini vision failed for {pn}: {exc}")
        return {"verdict": "KEEP", "reason": f"Gemini error: {exc}"}


# ── Identity confirmation via Gemini grounding ────────────────────────────────

def confirm_identity_gemini(
    pn: str,
    brand: str,
    product_name: str = "",
    *,
    api_key: str = "",
) -> dict:
    """Confirm product identity using Gemini with Google Search grounding.

    Returns {
        "confirmed": bool,
        "confidence": float 0-1,
        "product_class": str,
        "grounding_urls": list[str],
        "notes": str,
    }

    This uses grounded search (500 RPD limit) — reserve for weak-identity SKUs.
    """
    from google.genai import types

    cached = _load_from_cache("identity_confirm", pn, f"{brand}_{pn}")
    if cached:
        log.debug(f"  gemini identity cache hit: {pn}")
        return cached

    client = _get_gemini_client(api_key)

    prompt = (
        f"Find the industrial product: brand={brand}, part number={pn}."
    )
    if product_name:
        prompt += f" Product name: {product_name}."
    prompt += (
        "\n\nConfirm: is this a real product? What type/category is it? "
        "Return JSON: {\"confirmed\": true/false, \"confidence\": 0.0-1.0, "
        "\"product_class\": \"...\", \"notes\": \"brief description\"}"
    )

    try:
        response = _call_gemini_with_retry(
            client,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1,
                max_output_tokens=512,
            ),
            task_type="identity_confirm",
            pn=pn,
            grounded=True,
        )

        text = response.text or ""

        # Extract grounding URLs from metadata
        grounding_urls = _extract_grounding_urls(response)

        # Parse JSON from response
        parsed = _extract_json_from_text(text)
        if not parsed:
            parsed = {}

        result = {
            "confirmed": bool(parsed.get("confirmed", False)),
            "confidence": float(parsed.get("confidence", 0.0)),
            "product_class": str(parsed.get("product_class", "")),
            "grounding_urls": grounding_urls,
            "notes": str(parsed.get("notes", "")),
        }
        _save_to_cache("identity_confirm", pn, f"{brand}_{pn}", result)
        return result
    except Exception as exc:
        log.warning(f"  gemini identity confirmation failed for {pn}: {exc}")
        return {
            "confirmed": False,
            "confidence": 0.0,
            "product_class": "",
            "grounding_urls": [],
            "notes": f"error: {exc}",
        }


def _extract_grounding_urls(response) -> list[str]:
    """Extract URLs from Gemini grounding metadata.

    Tries groundingMetadata.groundingChunks first, falls back to regex on text.
    """
    urls = []

    # Method 1: structured grounding metadata
    try:
        candidates = getattr(response, "candidates", []) or []
        for cand in candidates:
            gm = getattr(cand, "grounding_metadata", None)
            if not gm:
                continue
            chunks = getattr(gm, "grounding_chunks", []) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if web:
                    url = getattr(web, "uri", "") or ""
                    if url:
                        urls.append(url)
            # Also check grounding_supports for source URLs
            supports = getattr(gm, "grounding_supports", []) or []
            for support in supports:
                seg = getattr(support, "segment", None)
                if seg:
                    refs = getattr(support, "grounding_chunk_indices", []) or []
                    # Already handled via chunks above
    except Exception as exc:
        log.debug(f"grounding metadata extraction error: {exc}")

    # Method 2: regex fallback on response text
    if not urls:
        text = ""
        try:
            text = response.text or ""
        except Exception:
            pass
        url_pattern = re.findall(r'https?://[^\s"\'<>\)]+', text)
        urls = url_pattern[:5]

    return list(dict.fromkeys(urls))  # dedupe preserving order


def _extract_json_from_text(text: str) -> dict | None:
    """Extract JSON object from LLM response text."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    elif not text.startswith("{"):
        brace = text.find("{")
        if brace >= 0:
            text = text[brace:]
    last_brace = text.rfind("}")
    if last_brace >= 0:
        text = text[: last_brace + 1]
    text = re.sub(r",\s*}", "}", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ── Pipeline adapters (match photo_pipeline.py Protocol interfaces) ───────────

class GeminiChatAdapter:
    """Gemini adapter that matches ChatCompletionAdapter protocol.

    Plugs into photo_pipeline.py's call_gpt() via the `adapter` parameter.
    Uses structured output for price extraction and vision verdict.
    """

    provider = "gemini"

    def __init__(self, api_key: str = ""):
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._client = None
        self.last_call_metadata: dict[str, Any] = {}

    def _get_client(self):
        if self._client is None:
            self._client = _get_gemini_client(self._api_key)
        return self._client

    def complete(self, *, model: str, messages: list[dict], **api_kwargs: Any) -> str:
        """Complete a chat request via Gemini.

        Translates OpenAI-style messages to Gemini format.
        Returns the response text (JSON string for structured tasks).
        """
        from google.genai import types

        start = time.monotonic()

        # Extract user message content
        user_parts = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                user_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            user_parts.append(block.get("text", ""))
                        elif block.get("type") == "image_url":
                            img_url = block.get("image_url", {})
                            if isinstance(img_url, dict):
                                img_url = img_url.get("url", "")
                            if isinstance(img_url, str) and img_url.startswith("data:"):
                                # Parse data URI for inline image
                                match = re.match(
                                    r"data:([\w.+/-]+);base64,(.+)",
                                    img_url,
                                    re.DOTALL,
                                )
                                if match:
                                    mime = match.group(1)
                                    b64 = match.group(2)
                                    img_bytes = base64.b64decode(b64)
                                    user_parts.append(
                                        types.Part.from_bytes(
                                            data=img_bytes, mime_type=mime
                                        )
                                    )

        # Build config
        temperature = api_kwargs.get("temperature", 0)
        max_tokens = api_kwargs.get(
            "max_completion_tokens",
            api_kwargs.get("max_tokens", 1024),
        )

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=int(max_tokens),
        )

        try:
            response = _call_gemini_with_retry(
                self._get_client(),
                contents=user_parts,
                config=config,
                task_type="chat",
                pn="",
            )

            text = response.text or ""
            latency_ms = int((time.monotonic() - start) * 1000)
            self.last_call_metadata = {
                "provider": self.provider,
                "model_alias": model,
                "model_resolved": GEMINI_MODEL,
                "latency_ms": latency_ms,
                "error_class": None,
            }
            return text
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            self.last_call_metadata = {
                "provider": self.provider,
                "model_alias": model,
                "model_resolved": GEMINI_MODEL,
                "latency_ms": latency_ms,
                "error_class": exc.__class__.__name__,
            }
            raise


class GeminiSearchAdapter:
    """DuckDuckGo-based search adapter matching SearchProviderAdapter protocol.

    Plugs into photo_pipeline.py's run_search_query() via the `adapter` parameter.
    Translates SerpAPI-style params to DDG queries.
    """

    provider = "duckduckgo"

    def search(self, *, params: dict[str, Any]) -> dict[str, Any]:
        """Execute search, returning SerpAPI-compatible result dict."""
        engine = params.get("engine", "google")
        query = params.get("q") or params.get("text", "")
        num = int(params.get("num", 5))

        if not query:
            return {"organic_results": []}

        # Map SerpAPI region params to DDG region
        gl = params.get("gl", "")
        region = "wt-wt"  # worldwide default
        if gl == "ru":
            region = "ru-ru"
        elif gl == "us":
            region = "us-en"

        ddg_results = search_ddg(query, max_results=num, region=region)

        # Convert to SerpAPI-compatible format
        organic_results = []
        for r in ddg_results:
            organic_results.append({
                "link": r["url"],
                "title": r.get("title", ""),
                "snippet": r.get("snippet", ""),
            })

        return {"organic_results": organic_results}


# ── Factory ───────────────────────────────────────────────────────────────────

def create_gemini_adapters(
    api_key: str = "",
) -> tuple[GeminiSearchAdapter, GeminiChatAdapter]:
    """Create search and chat adapters for the Gemini-first pipeline.

    Returns (search_adapter, chat_adapter).
    """
    return GeminiSearchAdapter(), GeminiChatAdapter(api_key=api_key)

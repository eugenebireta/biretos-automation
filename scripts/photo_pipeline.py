"""
photo_pipeline.py — Фото + Цена + Характеристики + GPT Vision отбраковка.

v1.5:
  - JSON-LD extraction (JSON-LD first, og:image last)
  - Word boundary PN regex (confirm_pn_exact / detect_suffix_conflict)
  - Trafilatura + GPT-4o-mini price extraction (step2b_extract_from_pages)
  - Yandex Organic как второй контур поиска
  - Google Dorks query templates (build_search_queries)
  - Perceptual hash dedupe + stock_photo_flag
  - Shadow Logger (JSONL per task_type, shadow_log/)
  - call_gpt() — единая обёртка с автоматическим shadow_log
  - pn_match.py — strong numeric PN guard (strict body + structured)
  - trust.py — domain trust table + source_tier in candidates
  - fx.py — FX normalization (RUB conversion, pluggable provider)
  - datasheet_pipeline.py — optional PDF search + parse (--datasheets flag)
  - export_pipeline.py — evidence bundles + InSales CSV + audit report
"""

from __future__ import annotations

import base64, datetime, hashlib, json, logging, os, re, sys, time
from pathlib import Path
from typing import Any, Callable, Optional, Protocol
from urllib.parse import urljoin, urlparse

import imagehash
import pandas as pd
import requests
import trafilatura
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image as PILImage
from serpapi import GoogleSearch

# ── Local pipeline modules ──────────────────────────────────────────────────────
import sys as _sys
_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in _sys.path:
    _sys.path.insert(0, str(_scripts_dir))

from pn_match import confirm_pn_body, match_pn, is_numeric_pn, check_brand_cooccurrence, extract_structured_pn_flags  # noqa: E402
from trust import get_source_trust, get_source_tier             # noqa: E402
from fx import convert_to_rub, fx_meta                         # noqa: E402
from pn_variants import generate_variants                       # noqa: E402
from export_pipeline import (                                   # noqa: E402
    build_evidence_bundle,
    write_evidence_bundles,
    write_insales_export,
    write_audit_report,
)
from deterministic_false_positive_controls import (             # noqa: E402
    apply_numeric_keep_guard,
    tighten_public_price_result,
)
from price_evidence_cache import (                             # noqa: E402
    CURRENT_PRICE_POLICY_VERSION,
    select_cached_price_fallback,
)
from no_price_coverage import (                                # noqa: E402
    choose_better_no_price_candidate,
    materialize_no_price_coverage,
)
from providers import (                                        # noqa: E402
    ClaudeChatAdapter,
    get_enrichment_model_alias,
    reset_batch_usage,
    get_batch_usage_summary,
)
from enrichment_experience_log import append_batch_experience   # noqa: E402
from catalog_seed import build_content_seed_from_row           # noqa: E402
from price_lineage import (                                     # noqa: E402
    choose_better_price_lineage_candidate,
    materialize_pre_llm_price_lineage,
)
from price_source_replacement import (                          # noqa: E402
    choose_better_replacement_candidate,
    materialize_source_replacement_surface,
)
from price_source_surface_stability import (                    # noqa: E402
    materialize_source_surface_stability,
    select_prior_admissible_surface_candidate,
    should_reuse_prior_admissible_surface,
)
from catalog_shadow_runtime import (                            # noqa: E402
    allow_external_source_attempt,
    allow_external_source_candidate,
    allow_next_sku,
    check_wallclock_budget,
    get_shadow_runtime_summary,
    record_completed_sku,
    record_skipped_due_to_budget,
    record_source_failure,
    record_source_success,
    shadow_runtime_active,
)
from price_sanity import apply_sanity_to_price_info             # noqa: E402


# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ── Пути ───────────────────────────────────────────────────────────────────────
ROOT           = Path(__file__).resolve().parent.parent
DOWNLOADS      = ROOT / "downloads"
PHOTOS_DIR     = DOWNLOADS / "photos"
INPUT_FILE     = DOWNLOADS / "honeywell_insales_import.csv"
VERDICT_FILE   = DOWNLOADS / "photo_verdict.json"
DATA_FILE      = DOWNLOADS / "product_data.json"
GPT_CACHE           = DOWNLOADS / "_gpt_cache.json"
ARTIFACT_CACHE_FILE = DOWNLOADS / "artifact_verdict_cache.json"
PRICE_EVIDENCE_CACHE_FILE = DOWNLOADS / "price_evidence_cache.json"
PRICE_SOURCE_SURFACE_CACHE_FILE = DOWNLOADS / "price_source_surface_cache.json"
SHADOW_LOG_DIR      = ROOT / "shadow_log"
EVIDENCE_DIR        = DOWNLOADS / "evidence"
EXPORT_DIR          = DOWNLOADS / "export"
LAST_RUN_META: dict = {}
_provider_errors: list[dict] = []

CHECKPOINT_FILE = DOWNLOADS / "checkpoint.json"
SHADOW_LOG_SCHEMA_VERSION = "photo_pipeline_shadow_log_record_v1"
QUEUE_SCHEMA_VERSION = "followup_queue_v2"
INPUT_COL_PN = "Параметр: Партномер"
INPUT_COL_NAME = "Название товара или услуги"
INPUT_COL_OUR_PRICE = "Цена продажи"
INPUT_COL_CATEGORY = "Параметр: Тип товара"
INPUT_COL_BRAND = "Параметр: Бренд"

PHOTOS_DIR.mkdir(exist_ok=True)
SHADOW_LOG_DIR.mkdir(exist_ok=True)
EVIDENCE_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)


# ── Checkpoint / resume helpers ─────────────────────────────────────────────

def load_checkpoint() -> dict:
    """Load checkpoint state: {pn → bundle} for already-processed SKUs."""
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_checkpoint(checkpoint: dict) -> None:
    """Persist checkpoint to disk. Called after each SKU completes."""
    try:
        CHECKPOINT_FILE.write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        log.warning(f"checkpoint save failed: {e}")


def clear_checkpoint() -> None:
    """Remove checkpoint file at end of successful full run."""
    try:
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
    except Exception:
        pass
load_dotenv(DOWNLOADS / ".env")

serpapi_key = str(os.getenv("SERPAPI_KEY", "")).strip()
client = None


# ── Константы ──────────────────────────────────────────────────────────────────
BRAND                 = "Honeywell"
DELAY                 = 0.4
MIN_BYTES             = 4000
MIN_DIM               = 150
PRICE_LLM_MODEL       = get_enrichment_model_alias("text")
VISION_MODEL          = get_enrichment_model_alias("vision")
STOCK_PHOTO_THRESHOLD = 5  # phash у N+ SKU → stock_photo_flag


class ChatCompletionAdapter(Protocol):
    """Minimal chat-completion contract for provider-safe injection."""

    def complete(self, *, model: str, messages: list[dict], **api_kwargs: Any) -> str:
        ...


class SearchProviderAdapter(Protocol):
    """Minimal search-provider contract for SerpAPI-safe injection."""

    def search(self, *, params: dict[str, Any]) -> dict[str, Any]:
        ...


def get_openai_client() -> OpenAI:
    """Resolve the OpenAI client lazily so import-time does not require API keys."""
    global client
    if client is not None:
        return client
    api_key = str(os.getenv("OPENAI_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    client = OpenAI(api_key=api_key)
    return client


class OpenAIChatCompletionsAdapter:
    """Legacy provider adapter backed by OpenAI chat completions."""

    def __init__(self, client_loader: Callable[[], Any] | None = None):
        self._client_loader = client_loader or get_openai_client
        self.last_call_metadata: dict[str, Any] = {}

    def complete(self, *, model: str, messages: list[dict], **api_kwargs: Any) -> str:
        started_at = time.perf_counter()
        try:
            response = self._client_loader().chat.completions.create(
                model=model,
                messages=messages,
                **api_kwargs,
            )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            self.last_call_metadata = {
                "provider": "openai",
                "model_alias": model,
                "model_resolved": model,
                "latency_ms": latency_ms,
                "error_class": None,
            }
            return response.choices[0].message.content or ""
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            self.last_call_metadata = {
                "provider": "openai",
                "model_alias": model,
                "model_resolved": model,
                "latency_ms": latency_ms,
                "error_class": exc.__class__.__name__,
            }
            raise


class SerpAPISearchAdapter:
    """Default search adapter backed by SerpAPI GoogleSearch."""

    def __init__(self, search_factory: Callable[[dict[str, Any]], Any] | None = None):
        self._search_factory = search_factory

    def search(self, *, params: dict[str, Any]) -> dict[str, Any]:
        search_factory = self._search_factory or GoogleSearch
        resolved_params = dict(params)
        resolved_params["api_key"] = resolved_params.get("api_key") or get_serpapi_key()
        return search_factory(resolved_params).get_dict()


chat_completion_adapter: ChatCompletionAdapter = ClaudeChatAdapter()
search_provider_adapter: SearchProviderAdapter = SerpAPISearchAdapter()


def set_chat_completion_adapter(adapter: ChatCompletionAdapter) -> None:
    global chat_completion_adapter
    chat_completion_adapter = adapter


def reset_chat_completion_adapter() -> None:
    global chat_completion_adapter
    chat_completion_adapter = ClaudeChatAdapter()


def set_search_provider_adapter(adapter: SearchProviderAdapter) -> None:
    global search_provider_adapter
    search_provider_adapter = adapter


def reset_search_provider_adapter() -> None:
    global search_provider_adapter
    search_provider_adapter = SerpAPISearchAdapter()


def get_serpapi_key() -> str:
    """Resolve SerpAPI key lazily so local deterministic work can run without it."""
    key = str(serpapi_key or os.getenv("SERPAPI_KEY", "")).strip()
    if not key:
        raise RuntimeError("SERPAPI_KEY is not configured")
    return key


def run_search_query(
    params: dict[str, Any],
    *,
    adapter: SearchProviderAdapter | None = None,
) -> dict[str, Any]:
    """Execute a search-provider request with runtime-only SerpAPI key resolution."""
    return (adapter or search_provider_adapter).search(params=dict(params))

# ── Шаблоны поисковых запросов (Google Dorks) ──────────────────────────────────
Q_GOOGLE_ORGANIC = 'intitle:"{pn}" "{brand}"'
Q_YANDEX_ORGANIC = '"{pn}" "{brand}"'
Q_RU_B2B_PRICE   = (
    '"{pn}" site:.ru '
    '(intext:"руб" OR intext:"цена" OR intext:"в наличии") '
    '-site:avito.ru -site:ozon.ru -site:wildberries.ru'
)
Q_DATASHEET      = (
    '"{pn}" '
    '(datasheet OR specification OR "техническое описание" OR "паспорт") '
    'filetype:pdf'
)
Q_DISTRIBUTORS   = (
    '"{pn}" '
    '(distributor OR "официальный дилер" OR "в наличии на складе") '
    '-forum -blog'
)
Q_GOOGLE_IMAGES  = '"{pn}" "{brand}" -used -refurbished -repair'

# ── Промпт для LLM-извлечения цены ────────────────────────────────────────────
PRICE_EXTRACTION_PROMPT_TMPL = """\
Ты — суровый B2B-аудитор. Извлеки коммерческие данные из текста страницы дистрибьютора.
Искомый товар: {brand} {pn}. Ожидаемый класс товара: {expected_category}.

Правила:
1. Игнорируй товары из блоков "Аналоги", "С этим покупают", "Похожие товары".
2. Найди точную цену и валюту. Если цена за упаковку (Pack of 10, lot of 5) —
   пересчитай за 1 штуку и укажи offer_qty.
3. Проверь suffix_conflict: если на странице обсуждается вариант с другим суффиксом
   ({pn}-EU, {pn}/A и т.д.) — отметь suffix_conflict: true.
4. Определи статус цены: публичная цена / только RFQ / скрытая / нет цены.
5. Зафикси наличие: in_stock / backorder / RFQ / lead_time_detected.
6. Проверь соответствие класса товара: основной продукт на странице должен совпадать
   с ожидаемым классом "{expected_category}". Если PN найден, но страница явно про
   другой тип товара (например, ожидается temperature sensor, а страница про
   electrical cover frame или socket) — это false positive, отметь category_mismatch: true.

Верни ТОЛЬКО валидный JSON без комментариев и markdown:
{{
  "pn_found": bool,
  "pn_exact_confirmed": bool,
  "category_mismatch": bool,
  "page_product_class": string,
  "price_per_unit": float or null,
  "currency": string or null,
  "offer_qty": int or null,
  "offer_unit_basis": "piece or pack or kit or unknown",
  "price_status": "public_price or rfq_only or hidden_price or no_price_found",
  "stock_status": "in_stock or backorder or rfq or unknown",
  "lead_time_detected": bool,
  "quote_cta_url": string or null,
  "suffix_conflict": bool,
  "price_confidence": int 0-100,
  "source_type": "official or authorized_distributor or ru_b2b or other"
}}"""

# ── Промпт для GPT Vision ──────────────────────────────────────────────────────
VISION_PROMPT = """\
Товар: {name} | Артикул: {pn} | Бренд: Honeywell

Ответь ТОЛЬКО JSON: {{"verdict": "KEEP" или "REJECT", "reason": "фраза"}}

REJECT если: явно не тот товар (человек, интерьер, документ, скриншот, логотип без предмета) \
или полная нечитаемая каша.
KEEP если товар угадывается — даже с водяным знаком, плохим фоном, низким качеством."""

# ── Домены ─────────────────────────────────────────────────────────────────────
US_PRICE_DOMAINS  = [
    "grainger.com", "newark.com", "mouser.com", "digikey.com",
    "rs-online.com", "automation24.com", "honeywellstore.com",
]
SKIP_DOMAINS      = {"serpapi.com", "google.com", "gstatic.com"}
SKIP_EXTS         = {".svg", ".gif", ".ico"}
SKIP_PAGE_DOMAINS = {"avito.ru", "youla.ru", "drom.ru", "irr.ru"}
NON_PRODUCT_IMAGE_TOKENS = {
    "banner",
    "logo",
    "icon",
    "flag",
    "footer",
    "social",
    "payment",
    "rollleft",
    "rollright",
    "qrcode",
    "qr-code",
    "sprite",
}

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.google.com/",
    "Accept": "text/html,application/xhtml+xml,image/webp,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ══════════════════════════════════════════════════════════════════════════════
# Модуль 0 — PN нормализация и валидация
# ══════════════════════════════════════════════════════════════════════════════

def confirm_pn_exact(pn: str, text: str) -> bool:
    """Word boundary match с numeric guard.

    Делегирует в pn_match.confirm_pn_body:
    - Для числовых PN (00020211, 010130.10): strict mode — блокирует и дефис.
      Предотвращает совпадение '00020211' внутри 'SL22-020211-K6'.
    - Для буквенно-цифровых PN: стандартный word boundary.
    """
    matched, _ = confirm_pn_body(pn, text)
    return matched


def detect_suffix_conflict(pn: str, found_pns: list[str]) -> bool:
    """True если среди found_pns есть суффикс-варианты pn.

    Конфликт: pn=XLS-123, found=XLS-123/A или XLS-123-EU.
    Не конфликт: pn=XLS-123, found=XLS-1234 (другой продукт).
    """
    conflicts = [
        p for p in found_pns
        if p != pn and (
            p.startswith(pn + "/") or
            p.startswith(pn + "-") or
            pn.startswith(p + "/") or
            pn.startswith(p + "-")
        )
    ]
    return len(conflicts) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# Shadow Logger + call_gpt — единая обёртка
# ══════════════════════════════════════════════════════════════════════════════

def shadow_log(
    task_type: str,
    pn: str,
    brand: str,
    model: str,
    provider: str,
    model_alias: str,
    model_resolved: str,
    prompt: str,
    response_raw: str,
    response_parsed: dict,
    parse_success: bool,
    latency_ms: int | None = None,
    error_class: str | None = None,
    source_url: str = None,
    source_type: str = None,
) -> None:
    """Пишет пару prompt/response в JSONL для будущего дообучения локальных моделей.

    Файл: shadow_log/{task_type}_YYYY-MM.jsonl
    Не блокирует основной пайплайн при ошибке записи.
    """
    try:
        month = datetime.datetime.utcnow().strftime("%Y-%m")
        path = SHADOW_LOG_DIR / f"{task_type}_{month}.jsonl"
        record = {
            "schema_version": SHADOW_LOG_SCHEMA_VERSION,
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "pn": pn,
            "brand": brand,
            "task_type": task_type,
            "provider": provider,
            "model": model,
            "model_alias": model_alias,
            "model_resolved": model_resolved,
            "prompt": prompt,
            "response_raw": response_raw,
            "response_parsed": response_parsed,
            "parse_success": parse_success,
            "latency_ms": latency_ms,
            "error_class": error_class,
            "human_correction": None,
            "correction_ts": None,
            "source_url": source_url,
            "source_type": source_type,
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning(f"shadow_log write failed: {e}")


def _redact_messages_for_log(messages: list[dict]) -> str:
    """Извлекает текстовые части messages для лога, заменяя base64-изображения на метку."""
    parts = []
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            parts.append(content[:2000])
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    parts.append(block.get("text", "")[:2000])
                elif block.get("type") == "image_url":
                    parts.append("[IMAGE_REDACTED]")
    return " | ".join(parts)


def call_gpt(
    task_type: str,
    pn: str,
    brand: str,
    messages: list[dict],
    model: str = PRICE_LLM_MODEL,
    source_url: str = None,
    source_type: str = None,
    adapter: ChatCompletionAdapter | None = None,
    **api_kwargs,
) -> str:
    """Единая обёртка над provider chat completions.

    Вызывает configured provider adapter, автоматически пишет запись в shadow_log.
    Возвращает content строку ответа. При ошибке API — пробрасывает исключение.
    """
    active_adapter = adapter or chat_completion_adapter
    try:
        content = active_adapter.complete(
            model=model,
            messages=messages,
            **api_kwargs,
        )
    except Exception as exc:
        adapter_meta = dict(getattr(active_adapter, "last_call_metadata", {}) or {})
        error_class = str(adapter_meta.get("error_class") or exc.__class__.__name__)
        _provider_errors.append({
            "pn": pn,
            "task_type": task_type,
            "error_class": error_class,
            "model": str(adapter_meta.get("model_alias", model)),
            "latency_ms": adapter_meta.get("latency_ms"),
        })
        shadow_log(
            task_type=task_type,
            pn=pn,
            brand=brand,
            provider=str(adapter_meta.get("provider", "unknown")),
            model=str(adapter_meta.get("model_alias", model)),
            model_alias=str(adapter_meta.get("model_alias", model)),
            model_resolved=str(adapter_meta.get("model_resolved", model)),
            prompt=_redact_messages_for_log(messages),
            response_raw="",
            response_parsed={},
            parse_success=False,
            latency_ms=adapter_meta.get("latency_ms"),
            error_class=error_class,
            source_url=source_url,
            source_type=source_type,
        )
        raise

    # Пробуем распарсить JSON для поля response_parsed в логе
    parse_success = False
    response_parsed: dict = {}
    try:
        clean = content.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1].lstrip("json").strip()
        response_parsed = json.loads(clean)
        parse_success = True
    except Exception:
        pass

    adapter_meta = dict(getattr(active_adapter, "last_call_metadata", {}) or {})
    shadow_log(
        task_type=task_type,
        pn=pn,
        brand=brand,
        provider=str(adapter_meta.get("provider", "unknown")),
        model=str(adapter_meta.get("model_alias", model)),
        model_alias=str(adapter_meta.get("model_alias", model)),
        model_resolved=str(adapter_meta.get("model_resolved", model)),
        prompt=_redact_messages_for_log(messages),
        response_raw=content,
        response_parsed=response_parsed,
        parse_success=parse_success,
        latency_ms=adapter_meta.get("latency_ms"),
        error_class=adapter_meta.get("error_class"),
        source_url=source_url,
        source_type=source_type,
    )
    return content


# ══════════════════════════════════════════════════════════════════════════════
# Модуль 1, Stage D — JSON-LD extraction
# ══════════════════════════════════════════════════════════════════════════════

def extract_jsonld_image(html: str, pn: str) -> dict | None:
    """Ищет Product schema в JSON-LD блоках страницы.

    Проверяет mpn/sku на совпадение с pn через confirm_pn_exact.

    Returns:
        dict(image_url, price, currency, mpn_confirmed) или None если не найдено.
    """
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") not in ("Product", "ProductGroup"):
                continue

            mpn = str(item.get("mpn") or item.get("sku") or "")
            mpn_confirmed = confirm_pn_exact(pn, mpn) if mpn else False

            # Извлекаем image URL
            image = item.get("image")
            image_url: Optional[str] = None
            if isinstance(image, str):
                image_url = image
            elif isinstance(image, list) and image:
                first = image[0]
                image_url = first if isinstance(first, str) else first.get("url")
            elif isinstance(image, dict):
                image_url = image.get("url") or image.get("contentUrl")

            if not image_url:
                continue

            # Цена из offers
            price: Optional[float] = None
            currency: Optional[str] = None
            offers = item.get("offers")
            if isinstance(offers, dict):
                try:
                    price = float(str(offers.get("price") or "").replace(",", "")) or None
                    currency = offers.get("priceCurrency")
                except (ValueError, TypeError):
                    pass
            elif isinstance(offers, list) and offers:
                try:
                    price = float(str(offers[0].get("price") or "").replace(",", "")) or None
                    currency = offers[0].get("priceCurrency")
                except (ValueError, TypeError):
                    pass

            return {
                "image_url": image_url,
                "price": price,
                "currency": currency,
                "mpn_confirmed": mpn_confirmed,
            }
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Query Builder
# ══════════════════════════════════════════════════════════════════════════════

def build_search_queries(pn: str, brand: str) -> dict:
    """Возвращает словарь Google Dorks запросов для разных целей поиска."""
    return {
        "google_organic":  Q_GOOGLE_ORGANIC.format(pn=pn, brand=brand),
        "yandex_organic":  Q_YANDEX_ORGANIC.format(pn=pn, brand=brand),
        "ru_b2b_price":    Q_RU_B2B_PRICE.format(pn=pn),
        "datasheet":       Q_DATASHEET.format(pn=pn),
        "distributors":    Q_DISTRIBUTORS.format(pn=pn),
        "google_images":   Q_GOOGLE_IMAGES.format(pn=pn, brand=brand),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Perceptual Hash
# ══════════════════════════════════════════════════════════════════════════════

def compute_phash(image_path: str) -> str:
    """Вычисляет perceptual hash изображения для дедупликации.

    Returns пустую строку при ошибке — caller должен обработать.
    """
    try:
        with PILImage.open(image_path) as img:
            return str(imagehash.phash(img))
    except Exception as e:
        log.warning(f"phash failed for {image_path}: {e}")
        return ""


def is_stock_photo(phash: str, phash_cache: dict[str, list[str]], pn: str) -> bool:
    """True если этот phash уже встречается у STOCK_PHOTO_THRESHOLD+ других SKU.

    Побочный эффект: добавляет pn в phash_cache[phash].
    """
    if not phash:
        return False
    existing = phash_cache.setdefault(phash, [])
    if pn not in existing:
        existing.append(pn)
    return len(existing) >= STOCK_PHOTO_THRESHOLD


# ══════════════════════════════════════════════════════════════════════════════
# Artifact verdict cache — персистентный кэш на уровне артефакта (не PN)
# ══════════════════════════════════════════════════════════════════════════════

def compute_sha1(path: Path) -> str:
    """SHA1 содержимого файла — content-based ключ для artifact cache.

    Returns пустую строку при ошибке.
    """
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except Exception as e:
        log.warning(f"sha1 failed for {path}: {e}")
        return ""


def lookup_artifact(sha1: str, artifact_cache: dict) -> dict | None:
    """Возвращает запись artifact cache по sha1 или None если не найдено.

    Ключ кэша — sha1 содержимого изображения (не путь, не PN).
    Один и тот же артефакт из разных источников даёт одну запись.
    """
    if not sha1:
        return None
    return artifact_cache.get(sha1)


# ══════════════════════════════════════════════════════════════════════════════
# Утилиты
# ══════════════════════════════════════════════════════════════════════════════

def safe_fn(pn: str) -> str:
    """Безопасное имя файла из PN."""
    return re.sub(r'[\\/:*?"<>|]', "_", pn)


def is_bad_url(url: str) -> bool:
    """True если URL явно не является ссылкой на реальное изображение."""
    if not url or url.startswith(("x-raw-image", "data:")):
        return True
    if "serpapi.com/searches/" in url:
        return True
    parsed = urlparse(url)
    if any(d in (parsed.netloc or "") for d in SKIP_DOMAINS):
        return True
    if any(parsed.path.lower().endswith(e) for e in SKIP_EXTS):
        return True
    return False


def download_image(url: str, dest: Path) -> bool:
    """Скачивает изображение по URL в dest. Возвращает True при успехе."""
    if is_bad_url(url):
        return False
    try:
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=12, stream=True)
        if r.status_code != 200:
            return False
        ct = r.headers.get("content-type", "")
        if "image" not in ct and "octet" not in ct:
            return False
        data = r.content
        if len(data) < MIN_BYTES:
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def get_size(path: Path) -> tuple[int, int]:
    """Возвращает (width, height) изображения или (0, 0) при ошибке."""
    try:
        with PILImage.open(path) as im:
            return im.size
    except Exception:
        return (0, 0)


def absolutize_url(raw_url: str, page_url: str) -> str:
    """Resolve a candidate asset URL against the page URL."""
    return urljoin(page_url, (raw_url or "").strip())


def _safe_int(raw_value: Any) -> int:
    try:
        return int(str(raw_value).strip())
    except (TypeError, ValueError):
        return 0


def _parse_srcset(srcset: str) -> list[str]:
    candidates: list[str] = []
    for chunk in str(srcset or "").split(","):
        url = chunk.strip().split(" ")[0].strip()
        if url:
            candidates.append(url)
    return candidates


def _contains_exact_pn(pn: str, text: str) -> bool:
    return bool(pn and text and confirm_pn_exact(pn, text))


def _is_probable_non_product_image(url: str, alt: str = "", title: str = "") -> bool:
    hay = " ".join((url or "", alt or "", title or "")).lower()
    return any(token in hay for token in NON_PRODUCT_IMAGE_TOKENS)


def _score_image_candidate(
    *,
    url: str,
    pn: str,
    alt: str = "",
    title: str = "",
    width: int = 0,
    height: int = 0,
    source_hint: str = "",
) -> int:
    if not url or is_bad_url(url) or _is_probable_non_product_image(url, alt, title):
        return -1000

    score = 0
    hay = " ".join((url, alt, title, source_hint)).lower()

    if source_hint == "jsonld":
        score += 70
    elif source_hint in {"itemprop", "product:image", "og:image"}:
        score += 35

    if _contains_exact_pn(pn, alt) or _contains_exact_pn(pn, title) or _contains_exact_pn(pn, url):
        score += 90

    if alt or title:
        score += 15

    if any(token in hay for token in ("product", "catalog/product", "/artikel/", "big.jpg", "/file/big.", "gallery")):
        score += 15

    if any(token in hay for token in ("brand/", "siteimages/", "/icons/", "payment/", "footer")):
        score -= 40

    max_dim = max(width, height)
    if max_dim >= MIN_DIM:
        score += 20
    elif max_dim >= 96:
        score += 8
    elif max_dim and max_dim < 48:
        score -= 20

    return score


def _add_image_candidate(
    bucket: list[dict[str, Any]],
    *,
    raw_url: str,
    page_url: str,
    pn: str,
    source_hint: str,
    alt: str = "",
    title: str = "",
    width: int = 0,
    height: int = 0,
) -> None:
    resolved_url = absolutize_url(raw_url, page_url)
    if not resolved_url:
        return
    score = _score_image_candidate(
        url=resolved_url,
        pn=pn,
        alt=alt,
        title=title,
        width=width,
        height=height,
        source_hint=source_hint,
    )
    if score <= -1000:
        return
    bucket.append({"url": resolved_url, "score": score, "source_hint": source_hint})


# ══════════════════════════════════════════════════════════════════════════════
# Парсинг страницы товара (JSON-LD first)
# ══════════════════════════════════════════════════════════════════════════════

def parse_product_page(url: str, pn: str = "") -> dict:
    """Заходит на страницу товара, вытаскивает фото + описание + характеристики.

    Иерархия извлечения изображений (план v1.4, Stage D):
    1. JSON-LD Product.image + mpn confirmation
    2. <img itemprop="image">
    3. <meta property="product:image">
    4. og:image
    5. Первая подходящая <img> на странице
    """
    result: dict = {
        "image_url": None,
        "description": None,
        "specs": {},
        "page_url": url,
        "mpn_confirmed": False,
        "jsonld_price": None,
        "jsonld_currency": None,
        "exact_jsonld_pn_match": False,
        "exact_title_pn_match": False,
        "exact_h1_pn_match": False,
        "exact_product_context_pn_match": False,
        "exact_structured_pn_match": False,
        "structured_pn_match_location": "",
    }
    try:
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=12)
        if r.status_code != 200:
            return result
        html = r.text
        soup = BeautifulSoup(html, "html.parser")
        image_candidates: list[dict[str, Any]] = []
        if pn:
            result.update(extract_structured_pn_flags(pn, html))

        # 1. JSON-LD (самый надёжный источник)
        if pn:
            jsonld = extract_jsonld_image(html, pn)
            if jsonld and jsonld.get("image_url"):
                _add_image_candidate(
                    image_candidates,
                    raw_url=jsonld["image_url"],
                    page_url=url,
                    pn=pn,
                    source_hint="jsonld",
                )
                result["mpn_confirmed"] = jsonld["mpn_confirmed"]
                result["jsonld_price"] = jsonld.get("price")
                result["jsonld_currency"] = jsonld.get("currency")

        # 2. itemprop="image"
        tag = soup.find("img", itemprop="image")
        if tag:
            for raw_url in [
                tag.get("src"),
                tag.get("data-src"),
                tag.get("data-original"),
                tag.get("data-image"),
                tag.get("data-zoom-image"),
                *(_parse_srcset(tag.get("data-srcset", ""))),
            ]:
                _add_image_candidate(
                    image_candidates,
                    raw_url=raw_url or "",
                    page_url=url,
                    pn=pn,
                    source_hint="itemprop",
                    alt=tag.get("alt", ""),
                    title=tag.get("title", ""),
                    width=_safe_int(tag.get("width")),
                    height=_safe_int(tag.get("height")),
                )

        # 3. product:image
        tag = soup.find("meta", property="product:image")
        if tag and tag.get("content"):
            _add_image_candidate(
                image_candidates,
                raw_url=tag["content"],
                page_url=url,
                pn=pn,
                source_hint="product:image",
            )

        # 4. og:image
        tag = soup.find("meta", property="og:image")
        if tag and tag.get("content"):
            _add_image_candidate(
                image_candidates,
                raw_url=tag["content"],
                page_url=url,
                pn=pn,
                source_hint="og:image",
            )

        # 5. Первая подходящая <img>
        for img in soup.find_all("img"):
            raw_urls = [
                img.get("src"),
                img.get("data-src"),
                img.get("data-original"),
                img.get("data-image"),
                img.get("data-zoom-image"),
                *(_parse_srcset(img.get("data-srcset", ""))),
            ]
            for raw_url in raw_urls:
                _add_image_candidate(
                    image_candidates,
                    raw_url=raw_url or "",
                    page_url=url,
                    pn=pn,
                    source_hint="img",
                    alt=img.get("alt", ""),
                    title=img.get("title", ""),
                    width=_safe_int(img.get("width")),
                    height=_safe_int(img.get("height")),
                )

        if image_candidates:
            best = max(image_candidates, key=lambda item: item["score"])
            result["image_url"] = best["url"]

        # Описание
        for attr, prop in [("property", "og:description"), ("name", "description")]:
            tag = soup.find("meta", {attr: prop})
            if tag and tag.get("content"):
                result["description"] = tag["content"][:500]
                break

        # Характеристики — таблицы
        specs: dict = {}
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) == 2:
                    k, v = cells[0].get_text(strip=True), cells[1].get_text(strip=True)
                    if k and v and len(k) < 60 and len(v) < 200:
                        specs[k] = v
        # dl/dt/dd
        for dl in soup.find_all("dl"):
            for k_tag, v_tag in zip(dl.find_all("dt"), dl.find_all("dd")):
                k, v = k_tag.get_text(strip=True), v_tag.get_text(strip=True)
                if k and v and len(k) < 60:
                    specs[k] = v
        if specs:
            result["specs"] = dict(list(specs.items())[:20])

    except Exception as e:
        result["error"] = str(e)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Шаг 1 — поиск фото (Google Dorks + Yandex Organic)
# ══════════════════════════════════════════════════════════════════════════════

def step1_find_and_download(pn: str, ru_name: str, artifact_cache: dict) -> dict:
    """Ищет страницу товара через Google + Yandex Organic, скачивает лучшее фото.

    Fast Pass: Google Organic → Yandex Organic → Google Images fallback.

    Artifact cache logic:
    - sha1 в кэше с KEEP → reuse (пропускаем GPT повторно)
    - sha1 в кэше с REJECT → удалить файл, продолжить поиск следующего кандидата
    - Один REJECT по одному source_url не блокирует весь PN
    """
    dest = PHOTOS_DIR / f"{safe_fn(pn)}.jpg"

    # Проверяем уже скачанный файл через artifact cache
    if dest.exists() and dest.stat().st_size > MIN_BYTES:
        sha1 = compute_sha1(dest)
        av = lookup_artifact(sha1, artifact_cache)
        if av and av.get("verdict") == "REJECT":
            log.info(f"  artifact REJECT (cached sha1={sha1[:8]}), удаляем и ищем заново")
            dest.unlink()
        else:
            w, h = get_size(dest)
            if w >= MIN_DIM or h >= MIN_DIM:
                return {
                    "path": str(dest), "size_kb": dest.stat().st_size // 1024,
                    "width": w, "height": h, "source": "cached",
                    "specs": {}, "description": None, "sha1": sha1,
                }
            dest.unlink()

    queries = build_search_queries(pn, BRAND)

    # Fast Pass: Google Organic + Yandex Organic
    web_attempts = [
        {
            "engine": "google", "q": queries["google_organic"],
            "num": 5, "gl": "ru", "hl": "ru",
        },
        {
            "engine": "yandex", "text": queries["yandex_organic"],
            "num": 5, "lang": "ru",
        },
    ]

    for attempt in web_attempts:
        engine = attempt["engine"]
        try:
            results = run_search_query(attempt).get("organic_results", [])
            time.sleep(DELAY)
            for res in results:
                page_url = res.get("link", "")
                if not page_url:
                    continue
                if any(d in page_url for d in SKIP_PAGE_DOMAINS):
                    continue
                if not allow_external_source_candidate(page_url):
                    continue
                parsed = parse_product_page(page_url, pn=pn)
                img_url = parsed.get("image_url")
                if not img_url or is_bad_url(img_url) or not download_image(img_url, dest):
                    continue
                sha1 = compute_sha1(dest)
                av = lookup_artifact(sha1, artifact_cache)
                if av and av.get("verdict") == "REJECT":
                    log.info(f"  artifact REJECT (sha1={sha1[:8]}), пропускаем {page_url[:60]}")
                    dest.unlink()
                    continue
                w, h = get_size(dest)
                src_tag = "jsonld" if parsed.get("mpn_confirmed") else engine
                return {
                    "path": str(dest), "size_kb": dest.stat().st_size // 1024,
                    "width": w, "height": h,
                    "source": f"{src_tag}:{page_url[:80]}",
                    "specs": parsed.get("specs", {}),
                    "description": parsed.get("description"),
                    "sha1": sha1,
                    "exact_jsonld_pn_match": bool(parsed.get("exact_jsonld_pn_match")),
                    "exact_title_pn_match": bool(parsed.get("exact_title_pn_match")),
                    "exact_h1_pn_match": bool(parsed.get("exact_h1_pn_match")),
                    "exact_product_context_pn_match": bool(parsed.get("exact_product_context_pn_match")),
                    "exact_structured_pn_match": bool(parsed.get("exact_structured_pn_match")),
                    "structured_pn_match_location": parsed.get("structured_pn_match_location", ""),
                }
        except Exception as e:
            log.warning(f"step1 {engine} error: {e}")

    # Fallback: Google Images
    try:
        imgs = run_search_query({
            "engine": "google_images", "q": queries["google_images"],
            "num": 10, "safe": "active", "api_key": get_serpapi_key(),
        }).get("images_results", [])
        time.sleep(DELAY)
        for img in imgs:
            orig = img.get("original", "")
            if img.get("original_width", 0) < MIN_DIM or not download_image(orig, dest):
                continue
            sha1 = compute_sha1(dest)
            av = lookup_artifact(sha1, artifact_cache)
            if av and av.get("verdict") == "REJECT":
                log.info(f"  artifact REJECT (sha1={sha1[:8]}), пропускаем img")
                dest.unlink()
                continue
            w, h = get_size(dest)
            return {
                "path": str(dest), "size_kb": dest.stat().st_size // 1024,
                "width": w, "height": h, "source": f"img:{orig[:80]}",
                "specs": {}, "description": None, "sha1": sha1,
            }
    except Exception as e:
        log.warning(f"step1 google_images fallback error: {e}")

    return {
        "path": "", "size_kb": 0, "width": 0, "height": 0,
        "source": "not_found", "specs": {}, "description": None, "sha1": "",
    }


# ══════════════════════════════════════════════════════════════════════════════
# Шаг 2 — поиск URL кандидатов (SerpAPI только)
# ══════════════════════════════════════════════════════════════════════════════

def step2_us_price(pn: str, ru_name: str) -> list[dict]:
    """Ищет кандидатов-дистрибьюторов через Google + Yandex Organic.

    Не заходит на страницы — только SerpAPI.

    Returns:
        Список dict: {url, snippet, title, source_type, engine}
    """
    queries = build_search_queries(pn, BRAND)
    candidates: list[dict] = []

    search_attempts = [
        {
            "label": "google_us",
            "engine": "google", "q": queries["google_organic"],
            "num": 5, "gl": "us", "hl": "en",
        },
        {
            "label": "yandex",
            "engine": "yandex", "text": queries["yandex_organic"],
            "num": 5, "lang": "ru",
        },
        {
            "label": "google_ru_b2b",
            "engine": "google", "q": queries["ru_b2b_price"],
            "num": 5, "gl": "ru", "hl": "ru",
        },
    ]
    if shadow_runtime_active():
        search_attempts = [attempt for attempt in search_attempts if attempt["label"] != "google_ru_b2b"]

    for attempt in search_attempts:
        label = attempt.pop("label")
        try:
            results = run_search_query(attempt).get("organic_results", [])
            time.sleep(DELAY)
            for res in results:
                url = res.get("link", "")
                if not url or any(d in url for d in SKIP_PAGE_DOMAINS):
                    continue
                if not allow_external_source_candidate(url):
                    continue
                trust = get_source_trust(url)
                source_type = (
                    "authorized_distributor" if any(d in url for d in US_PRICE_DOMAINS)
                    else "ru_b2b" if ".ru" in urlparse(url).netloc
                    else "other"
                )
                candidates.append({
                    "url": url,
                    "snippet": res.get("snippet", ""),
                    "title": res.get("title", ""),
                    "source_type": source_type,
                    "source_tier": trust["tier"],
                    "source_weight": trust.get("weight", 0.4),
                    "engine": label,
                })
        except Exception as e:
            log.warning(f"step2 {label} error: {e}")

    return candidates


# ══════════════════════════════════════════════════════════════════════════════
# Шаг 2b — извлечение цены из страниц кандидатов
# ══════════════════════════════════════════════════════════════════════════════

def step2b_extract_from_pages(
    candidates: list[dict],
    pn: str,
    brand: str,
    expected_category: str = "",
    *,
    price_cache_payload: dict | None = None,
    source_surface_cache_payload: dict | None = None,
) -> dict:
    """Обходит страницы кандидатов, извлекает цену через Trafilatura + GPT.

    Возвращает результат с наибольшим price_confidence среди валидных страниц.
    Кандидаты с category_mismatch=True получают принудительный confidence=20 и
    не попадают в publishable median (флаг category_mismatch сохраняется в результате).

    Returns:
        dict с полями: price_usd, currency, price_status, price_confidence,
                       source_url, source_type, stock_status, offer_unit_basis,
                       offer_qty, lead_time_detected, suffix_conflict,
                       category_mismatch, page_product_class.
    """
    empty: dict = {
        "price_usd": None, "currency": None, "source_url": None,
        "source_type": None, "source_tier": None,
        "source_engine": "",
        "price_status": "no_price_found",
        "price_confidence": 0, "stock_status": "unknown",
        "offer_unit_basis": "unknown", "offer_qty": None,
        "lead_time_detected": False, "suffix_conflict": False,
        "category_mismatch": False, "page_product_class": "",
        "brand_mismatch": False,
        "quote_cta_url": None,
        "rub_price": None, "fx_rate_used": None, "fx_provider": None,
        "pn_exact_confirmed": False,
        "page_context_clean": True,
        "public_price_rejection_reasons": [],
        "cache_fallback_used": False,
        "cache_fallback_reason": "",
        "cache_schema_version": "",
        "cache_policy_version": "",
        "cache_source_run_id": "",
        "cache_bundle_ref": "",
        "transient_failure_detected": False,
        "transient_failure_codes": [],
    }

    best: dict = {}           # только валидные кандидаты (mismatch=False)
    best_confidence = 0
    best_no_price: dict | None = None
    best_observed_candidate: dict | None = None
    best_lineage_candidate: dict | None = None
    best_admissible_replacement_candidate: dict | None = None
    best_mismatch: dict = {}  # mismatch-кандидаты — fallback, не publishable
    best_mismatch_confidence = 0
    transient_failure_codes: set[str] = set()

    def _apply_surface_stability(price_result: dict) -> dict:
        return materialize_source_surface_stability(
            price_result,
            pn=pn,
            surface_cache_payload=source_surface_cache_payload,
            observed_candidate=best_observed_candidate,
        )

    def _resolve_replacement_candidate(price_result: dict[str, Any]) -> dict[str, Any] | None:
        if best_admissible_replacement_candidate is not None:
            return best_admissible_replacement_candidate
        if price_result.get("price_status") not in {"no_price_found", "hidden_price"}:
            return None
        if not should_reuse_prior_admissible_surface(
            price_result,
            transient_failure_detected=bool(transient_failure_codes),
        ):
            return None
        return select_prior_admissible_surface_candidate(
            pn=pn,
            current_price_result=price_result,
            surface_cache_payload=source_surface_cache_payload,
            expected_policy_version=CURRENT_PRICE_POLICY_VERSION,
        )

    for cand in candidates[:6]:  # не более 6 страниц
        url = cand["url"]
        source_type = cand["source_type"]
        if check_wallclock_budget():
            break
        allowed, reason = allow_external_source_attempt(pn, url)
        if not allowed:
            if reason == "weak_marketplace_disabled" or reason.startswith("max_external_source_attempts_per_sku_reached"):
                continue
            break

        # Быстрый pre-filter: PN в snippet (word boundary)
        snippet_text = cand.get("snippet", "") + " " + cand.get("title", "")
        if snippet_text.strip() and not confirm_pn_exact(pn, snippet_text):
            log.debug(f"  skip snippet-nomatch: {url[:70]}")
            continue
        if best_observed_candidate is None:
            best_observed_candidate = dict(cand)

        try:
            r = requests.get(url, headers=BROWSER_HEADERS, timeout=12)
            trust = get_source_trust(url)
            pre_llm_candidate = materialize_pre_llm_price_lineage(
                pn=pn,
                price_result={
                    "price_status": "no_price_found",
                    "source_url": url,
                    "source_type": source_type,
                    "source_tier": trust["tier"],
                    "source_engine": cand.get("engine", ""),
                    "quote_cta_url": cand.get("quote_cta_url"),
                },
                html=r.text,
                source_url=url,
                source_type=source_type,
                source_tier=trust["tier"],
                source_engine=cand.get("engine", ""),
                content_type=r.headers.get("Content-Type", ""),
                status_code=r.status_code,
            )
            best_lineage_candidate = choose_better_price_lineage_candidate(
                best_lineage_candidate,
                pre_llm_candidate,
            )
            if (
                pre_llm_candidate.get("price_source_exact_product_lineage_confirmed")
                and pre_llm_candidate.get("price_source_tier") in {"official", "authorized", "industrial"}
            ):
                best_admissible_replacement_candidate = choose_better_replacement_candidate(
                    best_admissible_replacement_candidate,
                    pre_llm_candidate,
                )
            if r.status_code != 200:
                record_source_failure(url, timed_out=False, channel="external_source")
                continue

            # Trafilatura: HTML → чистый текст
            clean_text = trafilatura.extract(r.text, include_tables=True) or ""
            if not clean_text:
                log.debug(f"  trafilatura empty: {url[:70]}")
                record_source_failure(url, timed_out=False, channel="external_source")
                continue

            # Word boundary check на полном тексте страницы
            if not confirm_pn_exact(pn, clean_text):
                log.debug(f"  skip page-nomatch: {url[:70]}")
                record_source_failure(url, timed_out=False, channel="external_source")
                continue

            # GPT extraction через call_gpt (shadow_log автоматически)
            user_content = (
                PRICE_EXTRACTION_PROMPT_TMPL.format(
                    brand=brand, pn=pn,
                    expected_category=expected_category or "unknown",
                )
                + f"\n\n---\nТЕКСТ СТРАНИЦЫ:\n{clean_text[:4000]}"
            )
            messages = [{"role": "user", "content": user_content}]

            raw = call_gpt(
                task_type="price_extraction",
                pn=pn,
                brand=brand,
                messages=messages,
                model=PRICE_LLM_MODEL,
                source_url=url,
                source_type=source_type,
                temperature=0,
            )

            # Парсинг ответа
            try:
                clean_raw = raw.strip()
                if clean_raw.startswith("```"):
                    clean_raw = clean_raw.split("```")[1].lstrip("json").strip()
                parsed = json.loads(clean_raw)
            except Exception:
                log.warning(f"  price JSON parse failed: {url[:70]}")
                record_source_failure(url, timed_out=False, channel="external_source")
                continue

            if not parsed.get("pn_exact_confirmed"):
                log.debug(f"  LLM: pn_exact_confirmed=false: {url[:70]}")
                record_source_failure(url, timed_out=False, channel="external_source")
                continue

            category_mismatch = bool(parsed.get("category_mismatch"))
            page_product_class = parsed.get("page_product_class", "")
            confidence = int(parsed.get("price_confidence") or 0)

            # Category mismatch guard: принудительно снижаем confidence
            # FX normalization
            raw_price = parsed.get("price_per_unit")
            raw_currency = parsed.get("currency")
            rub_price = convert_to_rub(raw_price, raw_currency)
            _fx = fx_meta(raw_currency)

            candidate = {
                "price_usd": raw_price,
                "currency": raw_currency,
                "rub_price": rub_price,
                "fx_rate_used": _fx.get("fx_rate_stub"),
                "fx_provider": _fx.get("fx_provider"),
                "source_url": url,
                "source_type": source_type,
                "source_tier": trust["tier"],
                "source_engine": cand.get("engine", ""),
                "source_weight": trust.get("weight", 0.4),
                "price_status": parsed.get("price_status", "no_price_found"),
                "price_confidence": confidence,
                "stock_status": parsed.get("stock_status", "unknown"),
                "offer_unit_basis": parsed.get("offer_unit_basis", "unknown"),
                "offer_qty": parsed.get("offer_qty"),
                "lead_time_detected": bool(parsed.get("lead_time_detected")),
                "quote_cta_url": parsed.get("quote_cta_url"),
                "suffix_conflict": bool(parsed.get("suffix_conflict")),
                "category_mismatch": category_mismatch,
                "page_product_class": page_product_class,
                "brand_mismatch": False,  # reserved — future brand guard
                "pn_exact_confirmed": bool(parsed.get("pn_exact_confirmed")),
            }
            candidate = materialize_pre_llm_price_lineage(
                pn=pn,
                price_result=tighten_public_price_result(candidate),
                html=r.text,
                source_url=url,
                source_type=source_type,
                source_tier=trust["tier"],
                source_engine=cand.get("engine", ""),
                content_type=r.headers.get("Content-Type", ""),
                status_code=r.status_code,
            )

            if category_mismatch:
                # Баг B fix: mismatch-кандидат не участвует в основном выборе.
                # Сохраняем отдельно как fallback с явным статусом.
                log.warning(
                    f"  category_mismatch! ожидалось='{expected_category}', "
                    f"на странице='{page_product_class}' conf={confidence} {url[:55]}"
                )
                if confidence > best_mismatch_confidence:
                    best_mismatch_confidence = confidence
                    best_mismatch = {**candidate, "price_status": "category_mismatch_only"}
            else:
                record_source_success()
                log.info(
                    f"  price candidate [{parsed.get('price_status')}] "
                    f"conf={confidence} {url[:60]}"
                )
                if confidence > best_confidence:
                    best_confidence = confidence
                    best = candidate
                if candidate.get("price_status") in {"hidden_price", "no_price_found"}:
                    best_no_price = choose_better_no_price_candidate(best_no_price, candidate)

        except Exception as e:
            error_text = str(e).lower()
            timed_out = "timeout" in error_text or "timed out" in error_text
            if "insufficient_quota" in error_text or ("429" in error_text and "quota" in error_text):
                transient_failure_codes.add("llm_quota")
            elif "rate limit" in error_text or "rate_limit" in error_text:
                transient_failure_codes.add("llm_rate_limit")
            elif timed_out:
                transient_failure_codes.add("llm_timeout")
            elif any(token in error_text for token in ("temporary", "temporarily", "502", "503", "504", "connection reset")):
                transient_failure_codes.add("llm_temporary_failure")
            record_source_failure(url, timed_out=timed_out, channel="external_source")
            log.warning(f"  step2b error {url[:70]}: {e}")

    # Возвращаем только валидного best; mismatch-fallback только если совсем ничего нет
    if best:
        best = _apply_surface_stability(best)
        best = materialize_source_replacement_surface(
            best,
            admissible_replacement_candidate=_resolve_replacement_candidate(best),
        )
        best.setdefault("cache_fallback_used", False)
        best.setdefault("cache_fallback_reason", "")
        best.setdefault("cache_schema_version", "")
        best.setdefault("cache_policy_version", "")
        best.setdefault("cache_source_run_id", "")
        best.setdefault("cache_bundle_ref", "")
        best["transient_failure_detected"] = bool(transient_failure_codes)
        best["transient_failure_codes"] = sorted(transient_failure_codes)
        return best
    if best_mismatch:
        log.warning(
            f"  step2b: только mismatch-кандидаты найдены, возвращаем с price_status=category_mismatch_only"
        )
        best_mismatch = _apply_surface_stability(best_mismatch)
        best_mismatch = materialize_source_replacement_surface(
            best_mismatch,
            admissible_replacement_candidate=_resolve_replacement_candidate(best_mismatch),
        )
        best_mismatch.setdefault("cache_fallback_used", False)
        best_mismatch.setdefault("cache_fallback_reason", "")
        best_mismatch.setdefault("cache_schema_version", "")
        best_mismatch.setdefault("cache_policy_version", "")
        best_mismatch.setdefault("cache_source_run_id", "")
        best_mismatch.setdefault("cache_bundle_ref", "")
        best_mismatch["transient_failure_detected"] = bool(transient_failure_codes)
        best_mismatch["transient_failure_codes"] = sorted(transient_failure_codes)
        return best_mismatch

    if best_no_price:
        best_no_price = _apply_surface_stability(best_no_price)
        best_no_price = materialize_source_replacement_surface(
            best_no_price,
            admissible_replacement_candidate=_resolve_replacement_candidate(best_no_price),
        )
        best_no_price.setdefault("cache_fallback_used", False)
        best_no_price.setdefault("cache_fallback_reason", "")
        best_no_price.setdefault("cache_schema_version", "")
        best_no_price.setdefault("cache_policy_version", "")
        best_no_price.setdefault("cache_source_run_id", "")
        best_no_price.setdefault("cache_bundle_ref", "")
        best_no_price["transient_failure_detected"] = bool(transient_failure_codes)
        best_no_price["transient_failure_codes"] = sorted(transient_failure_codes)
        return best_no_price

    if shadow_runtime_active() and transient_failure_codes:
        cached = select_cached_price_fallback(
            pn=pn,
            candidates=candidates,
            cache_payload=price_cache_payload,
            failure_codes=sorted(transient_failure_codes),
            expected_policy_version=CURRENT_PRICE_POLICY_VERSION,
        )
        if cached:
            log.warning(
                "  step2b cache fallback reused admissible price evidence "
                f"for {pn} from {cached.get('cache_source_run_id', '')}"
            )
            cached = materialize_no_price_coverage(cached)
            cached = _apply_surface_stability(cached)
            cached = materialize_source_replacement_surface(
                cached,
                admissible_replacement_candidate=_resolve_replacement_candidate(cached),
            )
            cached["transient_failure_detected"] = True
            cached["transient_failure_codes"] = sorted(transient_failure_codes)
            return cached

    fallback = {**empty, **dict(best_lineage_candidate or {})}
    if not fallback:
        fallback = materialize_no_price_coverage(empty, observed_candidate=best_observed_candidate)
    fallback = _apply_surface_stability(fallback)
    fallback = materialize_source_replacement_surface(
        fallback,
        admissible_replacement_candidate=_resolve_replacement_candidate(fallback),
    )
    fallback.setdefault("price_source_seen", bool(best_observed_candidate))
    fallback.setdefault("price_source_url", (best_observed_candidate or {}).get("url", ""))
    fallback.setdefault("price_source_type", (best_observed_candidate or {}).get("source_type", ""))
    fallback.setdefault("price_source_tier", (best_observed_candidate or {}).get("source_tier", ""))
    fallback.setdefault("price_source_engine", (best_observed_candidate or {}).get("engine", ""))
    fallback.setdefault("cache_fallback_used", False)
    fallback.setdefault("cache_fallback_reason", "")
    fallback.setdefault("cache_schema_version", "")
    fallback.setdefault("cache_policy_version", "")
    fallback.setdefault("cache_source_run_id", "")
    fallback.setdefault("cache_bundle_ref", "")
    fallback["transient_failure_detected"] = bool(transient_failure_codes)
    fallback["transient_failure_codes"] = sorted(transient_failure_codes)
    return fallback


# ══════════════════════════════════════════════════════════════════════════════
# Шаг 3 — GPT Vision отбраковка фото
# ══════════════════════════════════════════════════════════════════════════════

def step3_vision(pn: str, name: str, img_path: str, w: int, h: int) -> dict:
    """GPT Vision: KEEP / REJECT для фото. Использует call_gpt → shadow_log автоматически."""
    if w and h and (w < 80 or h < 80):
        return {"verdict": "REJECT", "reason": f"баннер/шапка сайта {w}x{h}px"}
    try:
        b64 = base64.b64encode(Path(img_path).read_bytes()).decode()
        messages = [{"role": "user", "content": [
            {"type": "text", "text": VISION_PROMPT.format(name=name, pn=pn)},
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}},
        ]}]

        content = call_gpt(
            task_type="image_validation",
            pn=pn,
            brand=BRAND,
            messages=messages,
            model=VISION_MODEL,
            max_completion_tokens=80,
            temperature=0,
        )

        clean = content.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1].lstrip("json").strip()
        return json.loads(clean)
    except Exception as e:
        return {"verdict": "KEEP", "reason": f"GPT error: {e}"}


# ══════════════════════════════════════════════════════════════════════════════
# Главная функция
# ══════════════════════════════════════════════════════════════════════════════

def load_queue_part_numbers(
    queue_path: Path | str,
    *,
    allowed_action_codes: set[str],
) -> list[str]:
    rows = [
        json.loads(line)
        for line in Path(queue_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    part_numbers: list[str] = []
    for row in rows:
        schema_version = str(row.get("queue_schema_version", "") or "").strip()
        if schema_version != QUEUE_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported queue schema version: {schema_version or '<missing>'}"
            )
        action_code = str(row.get("action_code", "") or "").strip()
        if not action_code:
            raise ValueError("Queue row missing action_code")
        if action_code not in allowed_action_codes:
            continue
        pn = str(row.get("pn") or row.get("part_number") or "").strip()
        if not pn:
            raise ValueError("Queue row missing pn/part_number")
        part_numbers.append(pn)
    return part_numbers


def load_run_dataframe(
    *,
    input_file: Path = INPUT_FILE,
    limit: int | None = None,
    queue_path: Path | str | None = None,
) -> pd.DataFrame:
    df = pd.read_csv(input_file, sep="\t", encoding="utf-16", dtype=str).fillna("")
    if queue_path:
        queue_pns = load_queue_part_numbers(
            queue_path,
            allowed_action_codes={"photo_recovery"},
        )
        if queue_pns:
            order_map = {pn: index for index, pn in enumerate(queue_pns)}
            df = df.assign(__queue_pn=df[INPUT_COL_PN].astype(str).str.strip())
            df = df[df["__queue_pn"].isin(order_map)].copy()
            df["__queue_order"] = df["__queue_pn"].map(order_map)
            df = df.sort_values("__queue_order", kind="stable").drop(
                columns=["__queue_pn", "__queue_order"]
            )
        else:
            df = df.head(0)
    if limit:
        df = df.head(limit)
    return df


def run(
    limit: int = None,
    show_results: bool = False,
    datasheets: bool = False,
    export: bool = True,
    base_photo_url: str = "",
    queue_path: Path | str | None = None,
    force_reprocess: bool = False,
):
    """Запускает пайплайн для всех SKU из INPUT_FILE."""
    df = load_run_dataframe(limit=limit, queue_path=queue_path)

    verdicts       = json.loads(VERDICT_FILE.read_text(encoding="utf-8")) if VERDICT_FILE.exists() else {}
    data           = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else {}
    gpt_cache      = json.loads(GPT_CACHE.read_text(encoding="utf-8")) if GPT_CACHE.exists() else {}
    artifact_cache = json.loads(ARTIFACT_CACHE_FILE.read_text(encoding="utf-8")) if ARTIFACT_CACHE_FILE.exists() else {}
    price_evidence_cache = (
        json.loads(PRICE_EVIDENCE_CACHE_FILE.read_text(encoding="utf-8"))
        if PRICE_EVIDENCE_CACHE_FILE.exists() else {}
    )
    source_surface_cache = (
        json.loads(PRICE_SOURCE_SURFACE_CACHE_FILE.read_text(encoding="utf-8"))
        if PRICE_SOURCE_SURFACE_CACHE_FILE.exists() else {}
    )
    phash_cache: dict[str, list[str]] = {}  # phash → [pn1, pn2, ...]
    checkpoint     = load_checkpoint()

    global LAST_RUN_META, _provider_errors
    reset_batch_usage()
    _provider_errors = []
    keep = reject = no_photo = skipped_checkpoint = 0
    all_results = []
    evidence_bundles: list[dict] = []
    run_ts = datetime.datetime.utcnow().isoformat() + "Z"
    early_stop_reason = ""

    for i, (_, row) in enumerate(df.iterrows()):
        pn                = row["Параметр: Партномер"].strip()
        name              = row["Название товара или услуги"].strip()
        our_price         = row["Цена продажи"].strip()
        expected_category = row.get("Параметр: Тип товара", "").strip() if "Параметр: Тип товара" in row else ""

        # ── Checkpoint resume: skip already-processed PNs ─────────────────────
        content_seed      = build_content_seed_from_row(row)

        if pn in checkpoint:
            bundle = checkpoint[pn]
            evidence_bundles.append(bundle)
            v_cached = bundle.get("photo", {}).get("verdict", "NO_PHOTO")
            if v_cached == "KEEP":
                keep += 1
            elif v_cached == "NO_PHOTO":
                no_photo += 1
            else:
                reject += 1
            skipped_checkpoint += 1
            print(f"[{i+1}/{len(df)}] {pn} — CHECKPOINT (skip)")
            continue

        # ── Evidence-first skip: protect bundles written by other pipelines ───
        if not force_reprocess:
            pn_safe = re.sub(r'[\\/:*?"<>|]', "_", pn)
            evidence_path = EVIDENCE_DIR / f"evidence_{pn_safe}.json"
            if evidence_path.exists():
                try:
                    existing_bundle = json.loads(evidence_path.read_text(encoding="utf-8"))
                    evidence_bundles.append(existing_bundle)
                    checkpoint[pn] = existing_bundle
                    save_checkpoint(checkpoint)
                    v_cached = existing_bundle.get("photo", {}).get("verdict", "NO_PHOTO")
                    if v_cached == "KEEP":
                        keep += 1
                    elif v_cached == "NO_PHOTO":
                        no_photo += 1
                    else:
                        reject += 1
                    skipped_checkpoint += 1
                    print(f"[{i+1}/{len(df)}] {pn} — EVIDENCE_EXISTS (skip)")
                    continue
                except Exception:
                    pass  # Corrupted file — fall through to normal processing

        allowed, reason = allow_next_sku(pn)
        if not allowed:
            early_stop_reason = reason
            print(f"[{i+1}/{len(df)}] {pn} — EARLY_STOP ({reason})")
            for j in range(i + 1, len(df)):
                remaining_pn = df.iloc[j]["Параметр: Партномер"].strip()
                if remaining_pn != pn:
                    record_skipped_due_to_budget(remaining_pn, reason)
            break

        # ── PN variants generation ─────────────────────────────────────────────
        pn_var = generate_variants(pn)
        if pn_var.is_short:
            log.warning(f"  SHORT PN ({len(pn)} chars) — high collision risk: {pn}")

        print(f"\n[{i+1}/{len(df)}] {pn} — {name[:50]}")

        # ── Шаг 1: фото ───────────────────────────────────────────────────────
        dl = step1_find_and_download(pn, name, artifact_cache)

        if not dl["path"]:
            print("  Фото: НЕ НАЙДЕНО")
            verdicts[pn] = {"verdict": "NO_PHOTO", "reason": "не найдено", "path": ""}
            data[pn] = {
                "specs": {}, "description": None,
                "price_usd": None, "price_source": None,
                "price_status": "no_price_found",
            }
            no_photo += 1
            VERDICT_FILE.write_text(json.dumps(verdicts, ensure_ascii=False, indent=2), encoding="utf-8")
            DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            _no_photo_bundle = build_evidence_bundle(
                pn=pn, name=name, brand=BRAND,
                photo_result=dl,
                vision_verdict={"verdict": "NO_PHOTO", "reason": "не найдено"},
                price_result={"price_status": "no_price_found"},
                datasheet_result={"datasheet_status": "skipped"},
                run_ts=run_ts,
                our_price_raw=our_price,
                pn_variants=pn_var.variants,
                expected_category=expected_category,
                content_seed=content_seed,
            )
            _no_photo_content = _no_photo_bundle.get("content", {})
            data[pn] = {
                "specs": {},
                "description": _no_photo_content.get("description"),
                "description_source": _no_photo_content.get("description_source", ""),
                "site_placement": _no_photo_content.get("site_placement", ""),
                "product_type": _no_photo_content.get("product_type", ""),
                "seed_name": _no_photo_content.get("seed_name", ""),
                "price_usd": None,
                "price_source": None,
                "price_status": "no_price_found",
            }
            VERDICT_FILE.write_text(json.dumps(verdicts, ensure_ascii=False, indent=2), encoding="utf-8")
            DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            evidence_bundles.append(_no_photo_bundle)
            checkpoint[pn] = _no_photo_bundle
            save_checkpoint(checkpoint)
            record_completed_sku(pn)
            all_results.append({
                "pn": pn, "name": name, "verdict": "NO_PHOTO",
                "our_price": our_price, "price_status": "no_price_found",
                "description": (_no_photo_content.get("description") or "")[:200],
            })
            if check_wallclock_budget():
                early_stop_reason = get_shadow_runtime_summary().get("reason_for_early_stop", "")
                for j in range(i + 1, len(df)):
                    remaining_pn = df.iloc[j]["Параметр: Партномер"].strip()
                    record_skipped_due_to_budget(remaining_pn, early_stop_reason or "wallclock_budget_reached")
                break
            continue

        # Perceptual hash dedupe
        ph = compute_phash(dl["path"])
        stock_flag = is_stock_photo(ph, phash_cache, pn)
        if stock_flag:
            log.warning(f"  stock_photo_flag=True для {pn} (phash у 5+ SKU)")

        cached_mark = "(cached)" if dl["source"] == "cached" else ""
        print(f"  Фото: {dl['width']}x{dl['height']}px {dl['size_kb']}KB {cached_mark}")
        print(f"  Источник: {dl['source'][:85]}")

        # ── Шаг 2: поиск URL кандидатов ───────────────────────────────────────
        candidates = step2_us_price(pn, name)

        # ── Шаг 2b: извлечение цены ────────────────────────────────────────────
        price_info = tighten_public_price_result(
            step2b_extract_from_pages(
                candidates,
                pn,
                BRAND,
                expected_category,
                price_cache_payload=price_evidence_cache,
                source_surface_cache_payload=source_surface_cache,
            )
        )
        if price_info["price_usd"]:
            fallback_mark = " [cache_fallback]" if price_info.get("cache_fallback_used") else ""
            print(
                f"  Цена: {price_info['currency']} {price_info['price_usd']:,.2f} "
                f"[{price_info['price_status']}] ({price_info['source_url'][:55]}){fallback_mark}"
            )
        else:
            print(f"  Цена: {price_info['price_status']}")

        # ── Price Sanity Check ────────────────────────────────────────────────
        if price_info.get("price_usd") is not None:
            price_info = apply_sanity_to_price_info(
                price_info=price_info,
                pn=pn,
                brand=BRAND,
            )
            if price_info.get("price_sanity_status") != "PASS":
                _sanity_flags = price_info.get("price_sanity_flags", [])
                print(
                    f"  [PRICE_SANITY] {price_info['price_sanity_status']}: "
                    + "; ".join(_sanity_flags)
                )
                if price_info.get("price_sanity_status") == "REJECT":
                    print(f"  [PRICE_SANITY] Цена отклонена → price_status=rejected_sanity_check")

        # ── Шаг 3: GPT Vision ─────────────────────────────────────────────────
        sha1 = dl.get("sha1", "")
        gpt_key = f"{pn}:{dl['path']}"

        # Проверяем artifact cache по sha1 — KEEP позволяет пропустить GPT
        av = lookup_artifact(sha1, artifact_cache) if sha1 else None
        if av:
            v = {"verdict": av["verdict"], "reason": av.get("reason", "artifact_cache")}
            print(f"  Вердикт: {v['verdict']} (artifact_cache sha1={sha1[:8]}) — {v['reason']}")
        elif gpt_key in gpt_cache:
            v = gpt_cache[gpt_key]
            # Баг A fix: сохраняем в artifact cache и из gpt_cache ветки
            if sha1 and sha1 not in artifact_cache:
                artifact_cache[sha1] = {
                    "pn": pn,
                    "source_url": dl.get("source", ""),
                    "phash": ph,
                    "verdict": v["verdict"],
                    "reason": v.get("reason", ""),
                    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                }
                ARTIFACT_CACHE_FILE.write_text(
                    json.dumps(artifact_cache, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            print(f"  Вердикт: {v['verdict']} (gpt_cache) — {v['reason']}")
        else:
            v = step3_vision(pn, name, dl["path"], dl["width"], dl["height"])
            gpt_cache[gpt_key] = v
            GPT_CACHE.write_text(json.dumps(gpt_cache, ensure_ascii=False, indent=2), encoding="utf-8")
            # Сохраняем в artifact cache по sha1
            if sha1:
                artifact_cache[sha1] = {
                    "pn": pn,
                    "source_url": dl.get("source", ""),
                    "phash": ph,
                    "verdict": v["verdict"],
                    "reason": v.get("reason", ""),
                    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                }
                ARTIFACT_CACHE_FILE.write_text(
                    json.dumps(artifact_cache, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            print(f"  Вердикт: {v['verdict']} — {v['reason']}")

        v = apply_numeric_keep_guard(
            pn=pn,
            photo_result=dl,
            vision_verdict=v,
            price_result=price_info,
        )
        if v.get("numeric_keep_guard_applied"):
            print(f"  deterministic_keep_guard: {', '.join(v.get('numeric_keep_guard_reasons', []))}")

        # ── Datasheet (optional) ────────────────────────────────────────────────
        ds_result: dict = {"datasheet_status": "skipped"}
        if datasheets:
            from datasheet_pipeline import find_datasheet
            ds_result = find_datasheet(pn, BRAND, get_serpapi_key())

        # ── Brand co-occurrence check ──────────────────────────────────────────
        page_text_for_cooc = dl.get("description") or ""
        brand_cooc = check_brand_cooccurrence(BRAND, page_text_for_cooc)

        # ── Evidence bundle ─────────────────────────────────────────────────────
        _dl_with_flags = {
            **dl,
            "phash": ph,
            "stock_photo_flag": stock_flag,
            "brand_cooccurrence": brand_cooc,
        }
        bundle = build_evidence_bundle(
            pn=pn, name=name, brand=BRAND,
            photo_result=_dl_with_flags,
            vision_verdict=v,
            price_result=price_info,
            datasheet_result=ds_result,
            run_ts=run_ts,
            our_price_raw=our_price,
            pn_variants=pn_var.variants,
            expected_category=expected_category,
            content_seed=content_seed,
        )
        evidence_bundles.append(bundle)
        checkpoint[pn] = bundle
        save_checkpoint(checkpoint)
        bundle_content = bundle.get("content", {})

        verdicts[pn] = {
            **v,
            "path": dl["path"],
            "width": dl["width"],
            "height": dl["height"],
            "stock_photo_flag": stock_flag,
        }
        data[pn] = {
            "specs": dl.get("specs", {}),
            "description": bundle_content.get("description"),
            "description_source": bundle_content.get("description_source", ""),
            "site_placement": bundle_content.get("site_placement", ""),
            "product_type": bundle_content.get("product_type", ""),
            "seed_name": bundle_content.get("seed_name", ""),
            "price_usd": price_info["price_usd"],
            "price_source": price_info["source_url"],
            "price_status": price_info["price_status"],
            "price_confidence": price_info["price_confidence"],
            "price_currency": price_info["currency"],
            "stock_status": price_info["stock_status"],
            "suffix_conflict": price_info["suffix_conflict"],
            "category_mismatch": price_info["category_mismatch"],
            "page_product_class": price_info["page_product_class"],
            "price_source_seen": bool(price_info.get("price_source_seen")),
            "price_source_url": price_info.get("price_source_url"),
            "price_source_tier": price_info.get("price_source_tier"),
            "price_source_lineage_confirmed": bool(price_info.get("price_source_lineage_confirmed")),
            "price_source_exact_product_lineage_confirmed": bool(price_info.get("price_source_exact_product_lineage_confirmed")),
            "price_source_lineage_reason_code": price_info.get("price_source_lineage_reason_code", ""),
            "price_source_admissible_replacement_confirmed": bool(price_info.get("price_source_admissible_replacement_confirmed")),
            "price_source_terminal_weak_lineage": bool(price_info.get("price_source_terminal_weak_lineage")),
            "price_source_replacement_reason_code": price_info.get("price_source_replacement_reason_code", ""),
            "price_source_replacement_url": price_info.get("price_source_replacement_url", ""),
            "price_source_replacement_tier": price_info.get("price_source_replacement_tier", ""),
            "price_reviewable_no_price_candidate": bool(price_info.get("price_reviewable_no_price_candidate")),
            "price_no_price_reason_code": price_info.get("price_no_price_reason_code", ""),
            "cache_fallback_used": bool(price_info.get("cache_fallback_used")),
            "cache_source_run_id": price_info.get("cache_source_run_id"),
            "transient_failure_codes": price_info.get("transient_failure_codes", []),
        }
        VERDICT_FILE.write_text(json.dumps(verdicts, ensure_ascii=False, indent=2), encoding="utf-8")
        DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        if v["verdict"] == "KEEP":
            keep += 1
        else:
            reject += 1

        record_completed_sku(pn)
        all_results.append({
            "pn": pn, "name": name, "verdict": v["verdict"],
            "photo": f"{dl['width']}x{dl['height']}px {dl['size_kb']}KB",
            "our_price": our_price,
            "price_usd": price_info["price_usd"],
            "price_status": price_info["price_status"],
            "price_source": price_info["source_url"],
            "description": (bundle_content.get("description") or "")[:200],
            "specs": dl.get("specs", {}),
            "photo_source": dl["source"][:80],
            "stock_photo_flag": stock_flag,
            "suffix_conflict": price_info["suffix_conflict"],
            "category_mismatch": price_info["category_mismatch"],
            "page_product_class": price_info["page_product_class"],
            "price_source_seen": bool(price_info.get("price_source_seen")),
            "price_source_lineage_confirmed": bool(price_info.get("price_source_lineage_confirmed")),
            "price_source_exact_product_lineage_confirmed": bool(price_info.get("price_source_exact_product_lineage_confirmed")),
            "price_source_lineage_reason_code": price_info.get("price_source_lineage_reason_code", ""),
            "price_source_admissible_replacement_confirmed": bool(price_info.get("price_source_admissible_replacement_confirmed")),
            "price_source_terminal_weak_lineage": bool(price_info.get("price_source_terminal_weak_lineage")),
            "price_source_replacement_reason_code": price_info.get("price_source_replacement_reason_code", ""),
            "price_source_replacement_url": price_info.get("price_source_replacement_url", ""),
            "price_source_replacement_tier": price_info.get("price_source_replacement_tier", ""),
            "price_reviewable_no_price_candidate": bool(price_info.get("price_reviewable_no_price_candidate")),
            "price_no_price_reason_code": price_info.get("price_no_price_reason_code", ""),
        })
        if check_wallclock_budget():
            early_stop_reason = get_shadow_runtime_summary().get("reason_for_early_stop", "")
            for j in range(i + 1, len(df)):
                remaining_pn = df.iloc[j]["Параметр: Партномер"].strip()
                record_skipped_due_to_budget(remaining_pn, early_stop_reason or "wallclock_budget_reached")
            break

    print(f"\n{'='*55}")
    print(f"KEEP: {keep}  REJECT: {reject}  NO_PHOTO: {no_photo}  CHECKPOINT_SKIP: {skipped_checkpoint}")

    # ── Export ──────────────────────────────────────────────────────────────────
    if export and evidence_bundles:
        write_evidence_bundles(evidence_bundles, EVIDENCE_DIR)

        insales_path = EXPORT_DIR / "insales_export.csv"
        exported_count = write_insales_export(
            evidence_bundles, insales_path, base_photo_url=base_photo_url
        )

        run_meta = {
            "run_ts": run_ts,
            "limit": limit,
            "total_processed": len(evidence_bundles),
            "datasheets_enabled": datasheets,
        }
        audit_path = EXPORT_DIR / "audit_report.json"
        summary = write_audit_report(evidence_bundles, audit_path, run_meta)

        auto_pub = summary["cards"]["auto_publish"]
        review   = summary["cards"]["review_required"]
        draft    = summary["cards"]["draft_only"]
        print(f"\n{'='*55}")
        print(f"EXPORT: AUTO_PUBLISH={auto_pub}  REVIEW_REQUIRED={review}  DRAFT_ONLY={draft}")
        print(f"InSales CSV → {insales_path} ({exported_count} rows)")
        print(f"Audit      → {audit_path}")
        print(f"Evidence   → {EVIDENCE_DIR} ({len(evidence_bundles)} bundles)")

    shadow_summary = get_shadow_runtime_summary()
    cost_summary = get_batch_usage_summary()

    # Experience log — one record per finalized bundle
    try:
        append_batch_experience(
            shadow_log_dir=SHADOW_LOG_DIR,
            bundles=evidence_bundles,
            batch_id=run_ts,
        )
    except Exception as _exp_exc:
        log.warning(f"experience_log flush failed: {_exp_exc}")

    # Cost + provider error summary
    print(f"\n{'='*55}")
    print(
        f"COST:  calls={cost_summary['calls']}  "
        f"in={cost_summary['input_tokens']}tok  "
        f"out={cost_summary['output_tokens']}tok  "
        f"~${cost_summary['estimated_cost_usd']:.4f}"
        + ("  ⚠ COST_ANOMALY" if cost_summary.get("cost_anomaly") else "")
    )
    if _provider_errors:
        print(f"PROVIDER_ERRORS: {len(_provider_errors)} — " + ", ".join(
            f"{e['error_class']}({e['pn']})" for e in _provider_errors[:5]
        ) + ("…" if len(_provider_errors) > 5 else ""))
    else:
        print("PROVIDER_ERRORS: 0")

    LAST_RUN_META = {
        "run_ts": run_ts,
        "limit": limit,
        "queue_path": str(queue_path) if queue_path else "",
        "selected_input_rows": len(df),
        "processed_results": len(all_results),
        "evidence_bundles": len(evidence_bundles),
        "early_stop_reason": early_stop_reason or shadow_summary.get("reason_for_early_stop", ""),
        "shadow_runtime_summary": shadow_summary,
        "cost_summary": cost_summary,
        "provider_errors": len(_provider_errors),
    }

    # Clear checkpoint only on full (unlimited) successful run
    if not limit and not queue_path and export and not shadow_summary.get("early_stop"):
        clear_checkpoint()
        log.info("checkpoint cleared after full run")

    if show_results:
        print("\n" + "=" * 55)
        print("РЕЗУЛЬТАТЫ:")
        print("=" * 55)
        for r in all_results:
            print(f"\n{'─'*55}")
            print(f"Артикул:    {r['pn']}")
            print(f"Название:   {r['name']}")
            print(f"Фото:       {r.get('photo', '')}  [{r['verdict']}]")
            print(f"Фото URL:   {r.get('photo_source', '')}")
            if r.get("stock_photo_flag"):
                print("  ⚠ stock_photo_flag=True")
            if r.get("suffix_conflict"):
                print("  ⚠ suffix_conflict=True")
            print(f"Наша цена:  {r['our_price']} руб")
            if r.get("price_usd"):
                print(
                    f"Цена:       {r['price_usd']:,.2f} {r.get('price_status', '')} "
                    f"({r.get('price_source', '')[:55]})"
                )
            else:
                print(f"Цена:       {r.get('price_status', 'no_price_found')}")
            if r.get("description"):
                print(f"Описание:   {r['description'][:200]}")
            if r.get("specs"):
                print("Характеристики:")
                for k, v_val in list(r["specs"].items())[:8]:
                    print(f"  {k}: {v_val}")

    return all_results


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Honeywell enrichment pipeline v1.5")
    p.add_argument("--limit",       type=int,  default=None,  help="Ограничить кол-во SKU")
    p.add_argument("--show",        action="store_true",       help="Показать результаты в консоли")
    p.add_argument("--datasheets",  action="store_true",       help="Искать и парсить PDF datasheet")
    p.add_argument("--no-export",   action="store_true",       help="Не писать export/evidence")
    p.add_argument("--photo-base-url", default="",             help="Базовый URL для фото (InSales)")
    p.add_argument("--queue", default="", help="JSONL queue file from build_catalog_followup_queues.py")
    p.add_argument("--force-reprocess", action="store_true",
                   help="Ignore existing evidence bundles and reprocess from scratch")
    args = p.parse_args()
    run(
        limit=args.limit,
        show_results=args.show,
        datasheets=args.datasheets,
        export=not args.no_export,
        base_photo_url=args.photo_base_url,
        queue_path=Path(args.queue) if args.queue else None,
        force_reprocess=args.force_reprocess,
    )

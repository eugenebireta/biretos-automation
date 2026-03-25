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
from typing import Optional
from urllib.parse import urlparse

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

from pn_match import confirm_pn_body, match_pn, is_numeric_pn, check_brand_cooccurrence  # noqa: E402
from trust import get_source_trust, get_source_tier             # noqa: E402
from fx import convert_to_rub, fx_meta                         # noqa: E402
from pn_variants import generate_variants                       # noqa: E402
from export_pipeline import (                                   # noqa: E402
    build_evidence_bundle,
    write_evidence_bundles,
    write_insales_export,
    write_audit_report,
)


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
SHADOW_LOG_DIR      = ROOT / "shadow_log"
EVIDENCE_DIR        = DOWNLOADS / "evidence"
EXPORT_DIR          = DOWNLOADS / "export"

CHECKPOINT_FILE = DOWNLOADS / "checkpoint.json"

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

serpapi_key = os.environ["SERPAPI_KEY"]
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


# ── Константы ──────────────────────────────────────────────────────────────────
BRAND                 = "Honeywell"
DELAY                 = 0.4
MIN_BYTES             = 4000
MIN_DIM               = 150
PRICE_LLM_MODEL       = "gpt-4o-mini"
VISION_MODEL          = "gpt-5.4-mini"
STOCK_PHOTO_THRESHOLD = 5  # phash у N+ SKU → stock_photo_flag

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
    prompt: str,
    response_raw: str,
    response_parsed: dict,
    parse_success: bool,
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
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "pn": pn,
            "brand": brand,
            "task_type": task_type,
            "model": model,
            "prompt": prompt,
            "response_raw": response_raw,
            "response_parsed": response_parsed,
            "parse_success": parse_success,
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
    **api_kwargs,
) -> str:
    """Единая обёртка над client.chat.completions.create.

    Вызывает OpenAI API, автоматически пишет запись в shadow_log.
    Возвращает content строку ответа. При ошибке API — пробрасывает исключение.
    """
    response = client.chat.completions.create(
        model=model, messages=messages, **api_kwargs
    )
    content = response.choices[0].message.content or ""

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

    shadow_log(
        task_type=task_type,
        pn=pn,
        brand=brand,
        model=model,
        prompt=_redact_messages_for_log(messages),
        response_raw=content,
        response_parsed=response_parsed,
        parse_success=parse_success,
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
    }
    try:
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=12)
        if r.status_code != 200:
            return result
        html = r.text
        soup = BeautifulSoup(html, "html.parser")

        # 1. JSON-LD (самый надёжный источник)
        if pn:
            jsonld = extract_jsonld_image(html, pn)
            if jsonld and jsonld.get("image_url") and not is_bad_url(jsonld["image_url"]):
                result["image_url"] = jsonld["image_url"]
                result["mpn_confirmed"] = jsonld["mpn_confirmed"]
                result["jsonld_price"] = jsonld.get("price")
                result["jsonld_currency"] = jsonld.get("currency")

        # 2. itemprop="image"
        if not result["image_url"]:
            tag = soup.find("img", itemprop="image")
            if tag:
                src = tag.get("src") or tag.get("data-src") or ""
                if src.startswith("/"):
                    src = f"{urlparse(url).scheme}://{urlparse(url).netloc}{src}"
                if src and not is_bad_url(src):
                    result["image_url"] = src

        # 3. product:image
        if not result["image_url"]:
            tag = soup.find("meta", property="product:image")
            if tag and tag.get("content"):
                result["image_url"] = tag["content"]

        # 4. og:image
        if not result["image_url"]:
            tag = soup.find("meta", property="og:image")
            if tag and tag.get("content"):
                result["image_url"] = tag["content"]

        # 5. Первая подходящая <img>
        if not result["image_url"]:
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src") or ""
                if src.startswith("/"):
                    src = f"{urlparse(url).scheme}://{urlparse(url).netloc}{src}"
                w = int(img.get("width") or 0)
                if not is_bad_url(src) and (w >= MIN_DIM or not w):
                    result["image_url"] = src
                    break

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
            params = {**attempt, "api_key": serpapi_key}
            results = GoogleSearch(params).get_dict().get("organic_results", [])
            time.sleep(DELAY)
            for res in results:
                page_url = res.get("link", "")
                if not page_url:
                    continue
                if any(d in page_url for d in SKIP_PAGE_DOMAINS):
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
                }
        except Exception as e:
            log.warning(f"step1 {engine} error: {e}")

    # Fallback: Google Images
    try:
        params = {
            "engine": "google_images", "q": queries["google_images"],
            "num": 10, "safe": "active", "api_key": serpapi_key,
        }
        imgs = GoogleSearch(params).get_dict().get("images_results", [])
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

    for attempt in search_attempts:
        label = attempt.pop("label")
        try:
            params = {**attempt, "api_key": serpapi_key}
            results = GoogleSearch(params).get_dict().get("organic_results", [])
            time.sleep(DELAY)
            for res in results:
                url = res.get("link", "")
                if not url or any(d in url for d in SKIP_PAGE_DOMAINS):
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
        "price_status": "no_price_found",
        "price_confidence": 0, "stock_status": "unknown",
        "offer_unit_basis": "unknown", "offer_qty": None,
        "lead_time_detected": False, "suffix_conflict": False,
        "category_mismatch": False, "page_product_class": "",
        "brand_mismatch": False,
        "rub_price": None, "fx_rate_used": None, "fx_provider": None,
    }

    best: dict = {}           # только валидные кандидаты (mismatch=False)
    best_confidence = 0
    best_mismatch: dict = {}  # mismatch-кандидаты — fallback, не publishable
    best_mismatch_confidence = 0

    for cand in candidates[:6]:  # не более 6 страниц
        url = cand["url"]
        source_type = cand["source_type"]

        # Быстрый pre-filter: PN в snippet (word boundary)
        snippet_text = cand.get("snippet", "") + " " + cand.get("title", "")
        if snippet_text.strip() and not confirm_pn_exact(pn, snippet_text):
            log.debug(f"  skip snippet-nomatch: {url[:70]}")
            continue

        try:
            r = requests.get(url, headers=BROWSER_HEADERS, timeout=12)
            if r.status_code != 200:
                continue

            # Trafilatura: HTML → чистый текст
            clean_text = trafilatura.extract(r.text, include_tables=True) or ""
            if not clean_text:
                log.debug(f"  trafilatura empty: {url[:70]}")
                continue

            # Word boundary check на полном тексте страницы
            if not confirm_pn_exact(pn, clean_text):
                log.debug(f"  skip page-nomatch: {url[:70]}")
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
                continue

            if not parsed.get("pn_exact_confirmed"):
                log.debug(f"  LLM: pn_exact_confirmed=false: {url[:70]}")
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

            trust = get_source_trust(url)
            candidate = {
                "price_usd": raw_price,
                "currency": raw_currency,
                "rub_price": rub_price,
                "fx_rate_used": _fx.get("fx_rate_stub"),
                "fx_provider": _fx.get("fx_provider"),
                "source_url": url,
                "source_type": source_type,
                "source_tier": trust["tier"],
                "source_weight": trust.get("weight", 0.4),
                "price_status": parsed.get("price_status", "no_price_found"),
                "price_confidence": confidence,
                "stock_status": parsed.get("stock_status", "unknown"),
                "offer_unit_basis": parsed.get("offer_unit_basis", "unknown"),
                "offer_qty": parsed.get("offer_qty"),
                "lead_time_detected": bool(parsed.get("lead_time_detected")),
                "suffix_conflict": bool(parsed.get("suffix_conflict")),
                "category_mismatch": category_mismatch,
                "page_product_class": page_product_class,
                "brand_mismatch": False,  # reserved — future brand guard
            }

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
                log.info(
                    f"  price candidate [{parsed.get('price_status')}] "
                    f"conf={confidence} {url[:60]}"
                )
                if confidence > best_confidence:
                    best_confidence = confidence
                    best = candidate

        except Exception as e:
            log.warning(f"  step2b error {url[:70]}: {e}")

    # Возвращаем только валидного best; mismatch-fallback только если совсем ничего нет
    if best:
        return best
    if best_mismatch:
        log.warning(
            f"  step2b: только mismatch-кандидаты найдены, возвращаем с price_status=category_mismatch_only"
        )
        return best_mismatch
    return empty


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

def run(
    limit: int = None,
    show_results: bool = False,
    datasheets: bool = False,
    export: bool = True,
    base_photo_url: str = "",
):
    """Запускает пайплайн для всех SKU из INPUT_FILE."""
    df = pd.read_csv(INPUT_FILE, sep="\t", encoding="utf-16", dtype=str).fillna("")
    if limit:
        df = df.head(limit)

    verdicts       = json.loads(VERDICT_FILE.read_text(encoding="utf-8")) if VERDICT_FILE.exists() else {}
    data           = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else {}
    gpt_cache      = json.loads(GPT_CACHE.read_text(encoding="utf-8")) if GPT_CACHE.exists() else {}
    artifact_cache = json.loads(ARTIFACT_CACHE_FILE.read_text(encoding="utf-8")) if ARTIFACT_CACHE_FILE.exists() else {}
    phash_cache: dict[str, list[str]] = {}  # phash → [pn1, pn2, ...]
    checkpoint     = load_checkpoint()

    keep = reject = no_photo = skipped_checkpoint = 0
    all_results = []
    evidence_bundles: list[dict] = []
    run_ts = datetime.datetime.utcnow().isoformat() + "Z"

    for i, (_, row) in enumerate(df.iterrows()):
        pn                = row["Параметр: Партномер"].strip()
        name              = row["Название товара или услуги"].strip()
        our_price         = row["Цена продажи"].strip()
        expected_category = row.get("Параметр: Тип товара", "").strip() if "Параметр: Тип товара" in row else ""

        # ── Checkpoint resume: skip already-processed PNs ─────────────────────
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
            )
            evidence_bundles.append(_no_photo_bundle)
            checkpoint[pn] = _no_photo_bundle
            save_checkpoint(checkpoint)
            all_results.append({
                "pn": pn, "name": name, "verdict": "NO_PHOTO",
                "our_price": our_price, "price_status": "no_price_found",
            })
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
        price_info = step2b_extract_from_pages(candidates, pn, BRAND, expected_category)
        if price_info["price_usd"]:
            print(
                f"  Цена: {price_info['currency']} {price_info['price_usd']:,.2f} "
                f"[{price_info['price_status']}] ({price_info['source_url'][:55]})"
            )
        else:
            print(f"  Цена: {price_info['price_status']}")

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

        # ── Datasheet (optional) ────────────────────────────────────────────────
        ds_result: dict = {"datasheet_status": "skipped"}
        if datasheets:
            from datasheet_pipeline import find_datasheet
            ds_result = find_datasheet(pn, BRAND, serpapi_key)

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
        )
        evidence_bundles.append(bundle)
        checkpoint[pn] = bundle
        save_checkpoint(checkpoint)

        verdicts[pn] = {
            **v,
            "path": dl["path"],
            "width": dl["width"],
            "height": dl["height"],
            "stock_photo_flag": stock_flag,
        }
        data[pn] = {
            "specs": dl.get("specs", {}),
            "description": dl.get("description"),
            "price_usd": price_info["price_usd"],
            "price_source": price_info["source_url"],
            "price_status": price_info["price_status"],
            "price_confidence": price_info["price_confidence"],
            "price_currency": price_info["currency"],
            "stock_status": price_info["stock_status"],
            "suffix_conflict": price_info["suffix_conflict"],
            "category_mismatch": price_info["category_mismatch"],
            "page_product_class": price_info["page_product_class"],
        }
        VERDICT_FILE.write_text(json.dumps(verdicts, ensure_ascii=False, indent=2), encoding="utf-8")
        DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        if v["verdict"] == "KEEP":
            keep += 1
        else:
            reject += 1

        all_results.append({
            "pn": pn, "name": name, "verdict": v["verdict"],
            "photo": f"{dl['width']}x{dl['height']}px {dl['size_kb']}KB",
            "our_price": our_price,
            "price_usd": price_info["price_usd"],
            "price_status": price_info["price_status"],
            "price_source": price_info["source_url"],
            "description": (dl.get("description") or "")[:200],
            "specs": dl.get("specs", {}),
            "photo_source": dl["source"][:80],
            "stock_photo_flag": stock_flag,
            "suffix_conflict": price_info["suffix_conflict"],
            "category_mismatch": price_info["category_mismatch"],
            "page_product_class": price_info["page_product_class"],
        })

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

    # Clear checkpoint only on full (unlimited) successful run
    if not limit and export:
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
    args = p.parse_args()
    run(
        limit=args.limit,
        show_results=args.show,
        datasheets=args.datasheets,
        export=not args.no_export,
        base_photo_url=args.photo_base_url,
    )

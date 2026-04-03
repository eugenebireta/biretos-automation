"""Browser-vision second-pass price scout for bot-blocked and JS-rendered pages.

This is NOT the Anthropic Computer Use tool / beta agent loop.
This is a browser + vision second-pass scout that uses:

  * Playwright (real Chromium / Edge / Chrome) for page rendering and screenshots
  * Anthropic Messages API with image input for vision-based price extraction
    and part-number lineage confirmation

Designed as an additive fallback for URLs where price_manual_scout.py returns
403/401/498, or 200 without usable price/lineage (JS-rendered content).

Emits the same manifest JSONL schema as price_manual_scout.py with additive
browser-vision-specific fields.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from deterministic_false_positive_controls import tighten_public_price_result  # noqa: E402
from fx import convert_to_rub, fx_meta  # noqa: E402
from no_price_coverage import materialize_no_price_coverage  # noqa: E402
from photo_pipeline import BRAND  # noqa: E402
from price_manual_scout import (  # noqa: E402
    AUDITS_DIR,
    DOWNLOADS,
    SCOUT_CACHE_DIR,
    _coerce_float,
    _derive_source_type,
    _fx_status_for,
    _normalize_source_role,
    discover_prior_run_dirs,
    load_seed_records,
)
from price_source_surface_stability import (  # noqa: E402
    build_source_surface_cache_payload_from_run_dirs,
    materialize_source_surface_stability,
)
from source_trust import get_source_role, is_denied  # noqa: E402
from trust import get_source_trust  # noqa: E402

try:
    from playwright.sync_api import (
        Browser,
        Page,
        Playwright,
        TimeoutError as PlaywrightTimeout,
        sync_playwright,
    )

    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    import anthropic

    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    from captcha_solver import CaptchaSolverChain, CaptchaSolution  # noqa: E402

    HAS_CAPTCHA_SOLVER = True
except ImportError:
    HAS_CAPTCHA_SOLVER = False


log = logging.getLogger(__name__)

# ── Defaults ─────────────────────────────────────────────────────────────────

DEFAULT_BVS_SEED_FILE = SCOUT_CACHE_DIR / "browser_vision_seed.jsonl"
DEFAULT_BVS_MANIFEST_FILE = SCOUT_CACHE_DIR / "browser_vision_manifest.jsonl"
SCREENSHOT_BASE_DIR = DOWNLOADS / "browser_vision_screenshots"

DEFAULT_VISION_MODEL = "claude-sonnet-4-6"
ESCALATION_MODEL = "claude-opus-4-6"
ESCALATION_CONFIDENCE_THRESHOLD = 80
DEFAULT_BROWSER_TIMEOUT_MS = 30_000
DEFAULT_PAGE_WAIT_MS = 3_000

# HTTP status codes that trigger second-pass by default
BLOCKED_STATUS_CODES = {401, 403, 498}

# ── Vision prompt ────────────────────────────────────────────────────────────

_VISION_PROMPT_TEMPLATE = """\
You are analyzing a screenshot of a product webpage.
Extract the following information precisely.

Target part number: {pn}
Target brand: {brand}

Instructions:
1. **Part number**: Does the exact part number "{pn}" appear on this page?
   Look in product titles, descriptions, SKU/MPN fields, breadcrumbs, or any text.
   Must be an EXACT match, not a substring of a longer code.

2. **Price**: What is the listed price for this specific product?
   Extract the numeric value. Remove thousands separators.
   If multiple prices (wholesale/retail), take the primary/default price.
   If price is not visible or behind a login wall, return null.

3. **Currency**: Identify the currency.
   "₽" or "руб" or "руб." → "RUB"
   "€" → "EUR"
   "$" → "USD"
   If unclear, return null.

4. **Stock status**: in_stock / out_of_stock / pre_order / unknown

5. **Page classification**:
   - "normal_product_page" — standard product detail page
   - "blocked_ui" — captcha, access denied, 403 page, anti-bot screen
   - "login_required" — login form, authentication wall
   - "search_results" — list of products, not a single product page
   - "error_page" — server error, 404, etc.

Return ONLY valid JSON (no markdown, no commentary):
{{"pn_confirmed": true, "pn_match_context": "title", "price": 4314.0, "currency": "RUB", "stock_status": "in_stock", "page_class": "normal_product_page", "confidence": 95, "notes": ""}}
"""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _generate_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"bvs_{ts}_{uuid.uuid4().hex[:6]}"


def _generate_trace_id(record: dict[str, Any]) -> str:
    return str(record.get("trace_id") or f"bvs-{uuid.uuid4().hex[:12]}")


def _generate_idempotency_key(pn: str, page_url: str, run_id: str) -> str:
    return f"bvs:{pn}:{page_url}:{run_id}"


# ── Browser channel detection ────────────────────────────────────────────────

def _resolve_browser_channel(preference: str = "auto") -> str | None:
    """Resolve browser channel for Playwright.

    auto → try msedge, then chrome, then bundled Chromium.
    bundled → always use Playwright's bundled Chromium.
    msedge/chrome → use that specific channel.
    """
    if preference == "bundled":
        return None
    if preference != "auto":
        return preference

    import shutil

    for channel in ("msedge", "chrome"):
        if shutil.which(channel) is not None:
            return channel
        # Windows: browsers may not be on PATH but still installed
        if sys.platform == "win32":
            program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
            if channel == "msedge":
                exe = Path(program_files) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            else:
                exe = Path(program_files) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if exe.exists():
                return channel
    return None


# ── Cookie banner helper (benign only) ───────────────────────────────────────

_COOKIE_SELECTORS = [
    "button:has-text('Принять')",
    "button:has-text('Accept')",
    "button:has-text('Понятно')",
    "button:has-text('OK')",
    "button:has-text('Согласен')",
    "[class*='cookie'] button:visible",
    "[id*='cookie'] button:visible",
]


def _dismiss_cookie_banner(page: Any, timeout_ms: int = 2000) -> None:
    """Try to dismiss a cookie consent banner. Benign helper only."""
    for selector in _COOKIE_SELECTORS:
        try:
            loc = page.locator(selector).first
            if loc.is_visible(timeout=timeout_ms):
                loc.click(timeout=timeout_ms)
                page.wait_for_timeout(500)
                return
        except Exception:
            continue


# ── BrowserFetcher ───────────────────────────────────────────────────────────

class BrowserFetcher:
    """Manages Playwright browser lifecycle and page screenshots."""

    def __init__(
        self,
        *,
        headless: bool = True,
        browser_channel: str = "auto",
        timeout_ms: int = DEFAULT_BROWSER_TIMEOUT_MS,
        page_wait_ms: int = DEFAULT_PAGE_WAIT_MS,
    ) -> None:
        if not HAS_PLAYWRIGHT:
            raise RuntimeError(
                "playwright is required: pip install playwright && playwright install chromium"
            )
        self._headless = headless
        self._channel = _resolve_browser_channel(browser_channel)
        self._timeout_ms = timeout_ms
        self._page_wait_ms = page_wait_ms
        self._pw: Playwright | None = None
        self._browser: Browser | None = None

    def __enter__(self) -> BrowserFetcher:
        self._pw = sync_playwright().start()
        launch_kwargs: dict[str, Any] = {"headless": self._headless}
        if self._channel:
            launch_kwargs["channel"] = self._channel
        self._browser = self._pw.chromium.launch(**launch_kwargs)
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def fetch_screenshot(self, url: str) -> dict[str, Any]:
        """Navigate to URL and capture screenshot.

        Returns dict with: screenshot_bytes, final_url, page_title,
        browser_http_status, error.
        """
        assert self._browser is not None, "BrowserFetcher must be used as context manager"

        result: dict[str, Any] = {
            "screenshot_bytes": None,
            "final_url": url,
            "page_title": "",
            "browser_http_status": 0,
            "error": None,
        }

        page: Page | None = None
        try:
            context = self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="ru-RU",
            )
            page = context.new_page()

            response = page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
            result["browser_http_status"] = response.status if response else 0
            result["final_url"] = page.url

            # Wait for dynamic content to render
            page.wait_for_timeout(self._page_wait_ms)
            _dismiss_cookie_banner(page)

            result["page_title"] = page.title() or ""
            result["screenshot_bytes"] = page.screenshot(full_page=False, type="png")

        except Exception as exc:
            error_class = "TRANSIENT"
            if "playwright" in type(exc).__module__.lower():
                error_class = "TRANSIENT"
            result["error"] = {
                "error_class": error_class,
                "severity": "WARNING",
                "retriable": True,
                "message": f"{type(exc).__name__}: {exc}",
            }
            log.warning(
                "browser_fetch_failed",
                extra={
                    "url": url,
                    "error_class": error_class,
                    "error": str(exc),
                },
            )
        finally:
            if page:
                try:
                    page.context.close()
                except Exception:
                    pass

        return result


# ── CdpBrowserFetcher ────────────────────────────────────────────────────────

_EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
_CDP_PORT = 9222
_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
window.chrome = {runtime: {}};
"""


def _find_edge_exe() -> str | None:
    for p in _EDGE_PATHS:
        if Path(p).exists():
            return p
    return None


def _cdp_is_ready(port: int = _CDP_PORT) -> bool:
    import urllib.request
    try:
        r = urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2)
        return r.status == 200
    except Exception:
        return False


def _launch_edge_cdp(port: int = _CDP_PORT) -> Any:
    """Kill existing Edge processes and relaunch with CDP debugging port."""
    import subprocess, time
    subprocess.run(["taskkill", "/F", "/IM", "msedge.exe"],
                   capture_output=True, timeout=10)
    time.sleep(2)
    edge_exe = _find_edge_exe()
    if not edge_exe:
        raise RuntimeError("Edge not found in Program Files")
    proc = subprocess.Popen(
        [edge_exe, f"--remote-debugging-port={port}",
         "--no-first-run", "--disable-background-timer-throttling"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        time.sleep(1)
        if _cdp_is_ready(port):
            log.info("cdp_edge_ready", extra={"port": port, "pid": proc.pid})
            return proc
    raise RuntimeError(f"Edge CDP not ready on port {port} after 20s")


class CdpBrowserFetcher:
    """Connects to a running browser via CDP — undetectable by anti-bot systems.

    If --cdp-auto is set, automatically kills Edge and relaunches with CDP port.
    Otherwise connects to an already-running CDP instance.
    """

    def __init__(
        self,
        *,
        auto_launch: bool = True,
        port: int = _CDP_PORT,
        page_wait_ms: int = DEFAULT_PAGE_WAIT_MS,
        timeout_ms: int = DEFAULT_BROWSER_TIMEOUT_MS,
    ) -> None:
        if not HAS_PLAYWRIGHT:
            raise RuntimeError("playwright is required")
        self._auto_launch = auto_launch
        self._port = port
        self._page_wait_ms = page_wait_ms
        self._timeout_ms = timeout_ms
        self._pw: Any = None
        self._browser: Any = None
        self._edge_proc: Any = None
        self._page: Any = None
        # Public attrs for manifest compatibility
        self._headless = False
        self._channel = "cdp"

    def __enter__(self) -> CdpBrowserFetcher:
        if self._auto_launch and not _cdp_is_ready(self._port):
            self._edge_proc = _launch_edge_cdp(self._port)
        elif not _cdp_is_ready(self._port):
            raise RuntimeError(
                f"No CDP endpoint on port {self._port}. "
                "Launch Edge with: msedge.exe --remote-debugging-port=9222"
            )
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(
            f"http://127.0.0.1:{self._port}"
        )
        ctx = self._browser.contexts[0]
        self._page = ctx.new_page()
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass

    def fetch_screenshot(self, url: str) -> dict[str, Any]:
        """Navigate to URL in user's browser and capture screenshot."""
        result: dict[str, Any] = {
            "screenshot_bytes": None,
            "final_url": url,
            "page_title": "",
            "browser_http_status": 0,
            "error": None,
        }
        try:
            resp = self._page.goto(url, wait_until="networkidle", timeout=self._timeout_ms)
            self._page.wait_for_timeout(self._page_wait_ms)
            result["browser_http_status"] = resp.status if resp else 0
            result["final_url"] = self._page.url
            _dismiss_cookie_banner(self._page)
            try:
                result["page_title"] = self._page.title() or ""
            except Exception:
                result["page_title"] = "(nav error)"
            result["screenshot_bytes"] = self._page.screenshot(full_page=False, type="png")
        except Exception as exc:
            result["error"] = {
                "error_class": "TRANSIENT",
                "severity": "WARNING",
                "retriable": True,
                "message": f"{type(exc).__name__}: {exc}",
            }
            log.warning("cdp_fetch_failed", extra={"url": url, "error": str(exc)})
        return result


# ── CAPTCHA retry logic ──────────────────────────────────────────────────────

def _is_blocked_result(browser_result: dict[str, Any], vision_result: dict[str, Any] | None) -> bool:
    """Check if the page load was blocked by anti-bot / CAPTCHA."""
    status = browser_result.get("browser_http_status", 0)
    final_url = browser_result.get("final_url", "")
    if status in (403, 401, 498):
        return True
    if "xpvnsulc" in final_url:  # DDoS-Guard challenge redirect
        return True
    if vision_result and vision_result.get("page_class") in ("blocked_ui", "login_required"):
        return True
    return False


def _try_captcha_solve_and_retry(
    url: str,
    browser: Any,
    solver: CaptchaSolverChain,
    browser_result: dict[str, Any],
) -> dict[str, Any]:
    """Attempt CAPTCHA solve and retry page load with new cookies."""
    log.info("captcha_solve_attempt", extra={"url": url})
    solution = solver.solve(
        url,
        screenshot_bytes=browser_result.get("screenshot_bytes"),
    )
    if not solution.solved:
        log.info("captcha_solve_failed", extra={"url": url, "error": solution.error})
        return browser_result  # return original blocked result

    # Inject cookies into browser and retry
    log.info(
        "captcha_solved_retrying",
        extra={
            "url": url,
            "solver": solution.solver_used,
            "cookies_count": len(solution.cookies),
            "solve_time": solution.solve_time_sec,
        },
    )

    if hasattr(browser, '_page') and browser._page:
        # CDP mode — inject cookies and re-navigate
        page = browser._page
        ctx = page.context
        if solution.cookies:
            try:
                ctx.add_cookies(solution.cookies)
            except Exception as exc:
                log.warning("cookie_inject_failed", extra={"error": str(exc)})
        return browser.fetch_screenshot(url)
    else:
        # Standard BrowserFetcher — return cookies in result for later use
        browser_result["captcha_cookies"] = solution.cookies
        return browser.fetch_screenshot(url)


# ── VisionExtractor ──────────────────────────────────────────────────────────

class VisionExtractor:
    """Extracts price and PN lineage from screenshots via Claude Vision API."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_VISION_MODEL,
        escalation_model: str = ESCALATION_MODEL,
        enable_escalation: bool = True,
        escalation_threshold: int = ESCALATION_CONFIDENCE_THRESHOLD,
    ) -> None:
        if not HAS_ANTHROPIC:
            raise RuntimeError("anthropic is required: pip install anthropic")
        self._client = anthropic.Anthropic()
        self._model = model
        self._escalation_model = escalation_model
        self._enable_escalation = enable_escalation
        self._escalation_threshold = escalation_threshold

    def extract(
        self,
        screenshot_bytes: bytes,
        pn: str,
        brand: str = BRAND,
    ) -> dict[str, Any]:
        """Extract price and PN lineage from screenshot.

        Returns dict with: pn_confirmed, price, currency, stock_status,
        page_class, confidence, notes, vision_model, escalated.
        """
        result = self._call_vision(screenshot_bytes, pn, brand, model=self._model)
        result["escalated_to_opus"] = False
        result["vision_model"] = self._model

        # Auto-escalation: if primary model is not the escalation model and
        # result is low-confidence or PN not confirmed
        should_escalate = (
            self._enable_escalation
            and self._model != self._escalation_model
            and (
                not result.get("pn_confirmed")
                or (result.get("confidence") or 0) < self._escalation_threshold
            )
        )

        if should_escalate:
            log.info(
                "vision_escalating",
                extra={
                    "from_model": self._model,
                    "to_model": self._escalation_model,
                    "reason": "low_confidence_or_pn_not_confirmed",
                    "original_confidence": result.get("confidence"),
                    "original_pn_confirmed": result.get("pn_confirmed"),
                },
            )
            escalated = self._call_vision(
                screenshot_bytes, pn, brand, model=self._escalation_model
            )
            escalated["escalated_to_opus"] = True
            escalated["vision_model"] = self._escalation_model
            return escalated

        return result

    def _call_vision(
        self,
        screenshot_bytes: bytes,
        pn: str,
        brand: str,
        *,
        model: str,
    ) -> dict[str, Any]:
        """Single vision API call."""
        b64 = base64.standard_b64encode(screenshot_bytes).decode("ascii")
        prompt = _VISION_PROMPT_TEMPLATE.format(pn=pn, brand=brand)

        try:
            response = self._client.messages.create(
                model=model,
                max_tokens=512,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
            )
            raw_text = response.content[0].text.strip()
            return _parse_vision_response(raw_text)

        except Exception as exc:
            log.error(
                "vision_api_failed",
                extra={
                    "model": model,
                    "error_class": "TRANSIENT",
                    "severity": "ERROR",
                    "retriable": True,
                    "error": str(exc),
                },
            )
            return {
                "pn_confirmed": False,
                "pn_match_context": "",
                "price": None,
                "currency": None,
                "stock_status": "unknown",
                "page_class": "error_page",
                "confidence": 0,
                "notes": f"vision_api_error: {type(exc).__name__}",
                "extraction_failed": True,
            }


def _parse_vision_response(raw_text: str) -> dict[str, Any]:
    """Parse Claude vision JSON response with fallback."""
    defaults: dict[str, Any] = {
        "pn_confirmed": False,
        "pn_match_context": "",
        "price": None,
        "currency": None,
        "stock_status": "unknown",
        "page_class": "error_page",
        "confidence": 0,
        "notes": "",
        "extraction_failed": False,
    }
    # Strip markdown fences if present
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("response is not a JSON object")
        return {
            "pn_confirmed": bool(parsed.get("pn_confirmed", False)),
            "pn_match_context": str(parsed.get("pn_match_context", "")),
            "price": _coerce_float(parsed.get("price")),
            "currency": str(parsed.get("currency") or "").upper() or None,
            "stock_status": str(parsed.get("stock_status", "unknown")),
            "page_class": str(parsed.get("page_class", "normal_product_page")),
            "confidence": int(parsed.get("confidence", 0)),
            "notes": str(parsed.get("notes", "")),
            "extraction_failed": False,
        }
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        log.warning(
            "vision_parse_failed",
            extra={"raw_text": raw_text[:500], "error": str(exc)},
        )
        defaults["notes"] = f"parse_error: {exc}"
        defaults["extraction_failed"] = True
        return defaults


# ── Screenshot saving ────────────────────────────────────────────────────────

def _should_save_screenshot(
    vision_result: dict[str, Any],
    *,
    save_all: bool = False,
) -> bool:
    """Decide whether to save screenshot to disk."""
    if save_all:
        return True
    # Save on: lineage confirmed, price found, blocked UI, errors
    if vision_result.get("pn_confirmed"):
        return True
    if vision_result.get("price") is not None:
        return True
    page_class = vision_result.get("page_class", "")
    if page_class in ("blocked_ui", "login_required", "error_page"):
        return True
    if vision_result.get("extraction_failed"):
        return True
    return False


def _save_screenshot(
    screenshot_bytes: bytes,
    *,
    run_id: str,
    pn: str,
    domain: str,
) -> Path:
    """Save screenshot to disk and return path."""
    out_dir = SCREENSHOT_BASE_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_pn = pn.replace("/", "_").replace("\\", "_")
    safe_domain = domain.replace("/", "_").replace("\\", "_")
    filename = f"{safe_pn}_{safe_domain}.png"
    path = out_dir / filename
    path.write_bytes(screenshot_bytes)
    return path


# ── Lineage reason code mapping ──────────────────────────────────────────────

def _derive_bvs_lineage_reason_code(
    vision_result: dict[str, Any],
    browser_result: dict[str, Any],
) -> str:
    """Map vision + browser results to a lineage reason code."""
    if browser_result.get("error"):
        return "cu_browser_load_failed"
    if vision_result.get("extraction_failed"):
        return "cu_extraction_failed"

    page_class = vision_result.get("page_class", "")
    if page_class in ("blocked_ui", "login_required"):
        return "cu_vision_blocked_page"

    if vision_result.get("pn_confirmed"):
        return "cu_vision_pn_confirmed"

    return "cu_vision_pn_not_found"


# ── Main record materializer ────────────────────────────────────────────────

def materialize_bvs_record(
    record: dict[str, Any],
    *,
    browser: BrowserFetcher | CdpBrowserFetcher,
    extractor: VisionExtractor,
    surface_cache_payload: dict[str, Any] | None,
    run_id: str,
    save_all_screenshots: bool = False,
    captcha_solver: CaptchaSolverChain | None = None,
) -> dict[str, Any]:
    """Materialize a single seed record using browser + vision.

    Analogous to price_manual_scout.materialize_seed_record() but uses
    Playwright for page rendering and Claude Vision for extraction.
    If captcha_solver is provided, will attempt CAPTCHA solve + retry on blocked pages.
    """
    page_url = record["page_url"]
    pn = record["part_number"]
    trace_id = _generate_trace_id(record)
    idempotency_key = _generate_idempotency_key(pn, page_url, run_id)
    domain = (urlparse(page_url).netloc or "").lower().removeprefix("www.")

    log.info(
        "bvs_record_start",
        extra={"trace_id": trace_id, "pn": pn, "url": page_url, "domain": domain},
    )

    # ── Step 1: Browser fetch ────────────────────────────────────────────────
    browser_result = browser.fetch_screenshot(page_url)

    # ── Step 1b: CAPTCHA solve + retry if blocked ────────────────────────
    if captcha_solver and _is_blocked_result(browser_result, None):
        log.info("bvs_blocked_trying_captcha", extra={"trace_id": trace_id, "url": page_url})
        browser_result = _try_captcha_solve_and_retry(
            page_url, browser, captcha_solver, browser_result,
        )

    # ── Step 2: Vision extraction (if screenshot available) ──────────────────
    vision_result: dict[str, Any]
    if browser_result["screenshot_bytes"] is not None:
        vision_result = extractor.extract(
            browser_result["screenshot_bytes"],
            pn=pn,
            brand=record.get("brand", BRAND),
        )
    else:
        vision_result = {
            "pn_confirmed": False,
            "pn_match_context": "",
            "price": None,
            "currency": None,
            "stock_status": "unknown",
            "page_class": "error_page",
            "confidence": 0,
            "notes": "no_screenshot_available",
            "extraction_failed": True,
            "escalated_to_opus": False,
            "vision_model": "",
        }

    # ── Step 3: Screenshot saving ────────────────────────────────────────────
    screenshot_path: str = ""
    screenshot_taken = browser_result["screenshot_bytes"] is not None
    if screenshot_taken and _should_save_screenshot(vision_result, save_all=save_all_screenshots):
        saved = _save_screenshot(
            browser_result["screenshot_bytes"],
            run_id=run_id,
            pn=pn,
            domain=domain,
        )
        screenshot_path = str(saved)

    # ── Step 4: Reuse existing trust/role/fx infrastructure ──────────────────
    trust = get_source_trust(page_url)
    source_role = get_source_role(page_url)
    if source_role == "organic_discovery" and trust.get("domain"):
        source_role = get_source_role(str(trust["domain"]))
    source_role = _normalize_source_role(page_url, source_role, trust)
    source_type = _derive_source_type(page_url, source_role)

    # Use vision-extracted price if available, fall back to seed price
    effective_price = vision_result.get("price")
    effective_currency = vision_result.get("currency")
    if effective_price is None:
        effective_price = record.get("price_per_unit")
        effective_currency = record.get("currency") or None

    rub_price = None
    fx_rate_used = None
    fx_provider = None
    if effective_price is not None and effective_currency:
        rub_price = convert_to_rub(effective_price, effective_currency)
        fx = fx_meta(effective_currency)
        fx_rate_used = fx.get("fx_rate_stub")
        fx_provider = fx.get("fx_provider")

    fx_normalization_status, fx_gap_reason_code = _fx_status_for(
        effective_price, effective_currency, rub_price,
    )

    # ── Step 5: Lineage / coverage / surface stability ───────────────────────
    lineage_confirmed = bool(vision_result.get("pn_confirmed"))
    lineage_reason_code = _derive_bvs_lineage_reason_code(vision_result, browser_result)

    price_status = record.get("price_status", "no_price_found")
    if effective_price is not None and lineage_confirmed:
        price_status = "public_price"
    elif effective_price is None and lineage_confirmed:
        price_status = "no_price_found"

    price_result: dict[str, Any] = {
        "price_usd": effective_price,
        "currency": effective_currency,
        "rub_price": rub_price,
        "source_url": page_url,
        "source_type": source_type,
        "source_tier": trust.get("tier", "unknown"),
        "source_engine": "browser_vision_scout",
        "price_status": price_status,
        "price_confidence": int(vision_result.get("confidence") or 0),
        "stock_status": vision_result.get("stock_status", "unknown"),
        "offer_unit_basis": record.get("offer_unit_basis", "piece"),
        "offer_qty": int(record.get("offer_qty", 1) or 1),
        "lead_time_detected": bool(record.get("lead_time_detected")),
        "quote_cta_url": record.get("quote_cta_url") or None,
        "suffix_conflict": False,
        "category_mismatch": bool(record.get("category_mismatch")),
        "page_product_class": record.get("page_product_class", ""),
        "brand_mismatch": bool(record.get("brand_mismatch")),
        "pn_exact_confirmed": lineage_confirmed,
        "price_source_exact_product_lineage_confirmed": lineage_confirmed,
        "price_source_lineage_reason_code": lineage_reason_code,
        "price_source_seen": screenshot_taken,
    }

    price_result = materialize_no_price_coverage(price_result)
    price_result = tighten_public_price_result(price_result)
    price_result = materialize_source_surface_stability(
        price_result,
        pn=pn,
        surface_cache_payload=surface_cache_payload,
        observed_candidate={
            "url": page_url,
            "source_type": source_type,
            "engine": "browser_vision_scout",
            "source_tier": trust.get("tier", "unknown"),
        },
    )

    # ── Step 6: Review decision ──────────────────────────────────────────────
    review_required = any((
        is_denied(page_url),
        not lineage_confirmed,
        bool(price_result.get("price_source_surface_conflict_detected")),
        vision_result.get("page_class") in ("blocked_ui", "login_required", "search_results"),
        vision_result.get("extraction_failed"),
    ))

    # ── Step 7: Assemble manifest row ────────────────────────────────────────
    manifest_row = {
        # ── Standard fields (backward-compatible with price_manual_scout) ────
        "part_number": pn,
        "brand": record.get("brand", BRAND),
        "product_name": record.get("product_name", ""),
        "expected_category": record.get("expected_category", ""),
        "source_provider": record.get("source_provider", "codex_manual"),
        "page_url": page_url,
        "source_domain": domain,
        "source_role": source_role,
        "source_type": source_type,
        "source_tier": trust.get("tier", "unknown"),
        "source_weight": trust.get("weight", 0.4),
        "http_status": browser_result["browser_http_status"],
        "price_status": price_result.get("price_status", "no_price_found"),
        "price_per_unit": effective_price,
        "currency": effective_currency,
        "rub_price": rub_price,
        "fx_normalization_status": fx_normalization_status,
        "fx_gap_reason_code": fx_gap_reason_code,
        "fx_provider": fx_provider,
        "fx_rate_used": fx_rate_used,
        "offer_qty": price_result.get("offer_qty"),
        "offer_unit_basis": price_result.get("offer_unit_basis"),
        "stock_status": price_result.get("stock_status"),
        "lead_time_detected": bool(price_result.get("lead_time_detected")),
        "quote_cta_url": price_result.get("quote_cta_url"),
        "page_product_class": price_result.get("page_product_class", ""),
        "price_confidence": int(price_result.get("price_confidence") or 0),
        "price_source_seen": bool(price_result.get("price_source_seen")),
        "price_source_exact_product_lineage_confirmed": lineage_confirmed,
        "price_source_lineage_reason_code": lineage_reason_code,
        "price_source_surface_stable": bool(price_result.get("price_source_surface_stable")),
        "price_source_surface_conflict_detected": bool(price_result.get("price_source_surface_conflict_detected")),
        "price_source_surface_conflict_reason_code": price_result.get("price_source_surface_conflict_reason_code", ""),
        "source_price_value": record.get("source_price_value"),
        "source_price_currency": record.get("source_price_currency"),
        "source_offer_qty": record.get("source_offer_qty"),
        "source_offer_unit_basis": record.get("source_offer_unit_basis"),
        "price_basis_note": record.get("price_basis_note", ""),
        "notes": record.get("notes", ""),
        "transient_failure_codes": [],
        "cache_fallback_used": False,
        "review_required": review_required,
        # ── Additive browser-vision fields ───────────────────────────────────
        "browser_vision_source": True,
        "browser_mode": "headless" if browser._headless else "headed",
        "browser_channel": browser._channel or "bundled",
        "screenshot_taken": screenshot_taken,
        "screenshot_path": screenshot_path,
        "vision_model": vision_result.get("vision_model", ""),
        "vision_confidence": int(vision_result.get("confidence") or 0),
        "blocked_ui_detected": vision_result.get("page_class") in ("blocked_ui", "login_required"),
        "final_url": browser_result["final_url"],
        "page_title": browser_result["page_title"],
        "escalated_to_opus": bool(vision_result.get("escalated_to_opus")),
        "trace_id": trace_id,
        "idempotency_key": idempotency_key,
    }

    if browser_result.get("error"):
        manifest_row["transient_failure_codes"].append(
            browser_result["error"].get("message", "browser_error")
        )

    log.info(
        "bvs_record_done",
        extra={
            "trace_id": trace_id,
            "pn": pn,
            "lineage": lineage_confirmed,
            "price": effective_price,
            "currency": effective_currency,
            "reason_code": lineage_reason_code,
            "vision_model": vision_result.get("vision_model", ""),
            "escalated": vision_result.get("escalated_to_opus", False),
        },
    )

    return manifest_row


# ── First-pass manifest filter ───────────────────────────────────────────────

def load_first_pass_candidates(
    manifest_path: Path,
    status_filter: set[int] | None = None,
) -> set[str]:
    """Load first-pass manifest and return page_urls that need second pass.

    A URL qualifies if:
    - http_status in status_filter (default: 401, 403, 498)  OR
    - http_status == 200 but no public_price or no lineage confirmed
    """
    if status_filter is None:
        status_filter = BLOCKED_STATUS_CODES

    candidates: set[str] = set()
    if not manifest_path.exists():
        return candidates

    for raw_line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue

        http_status = int(row.get("http_status", 0))
        price_status = str(row.get("price_status", ""))
        lineage = bool(row.get("price_source_exact_product_lineage_confirmed", False))

        if http_status in status_filter:
            candidates.add(row.get("page_url", ""))
        elif http_status == 200 and (price_status != "public_price" or not lineage):
            candidates.add(row.get("page_url", ""))

    candidates.discard("")
    return candidates


# ── Batch runner ─────────────────────────────────────────────────────────────

def run(
    seed_path: Path,
    manifest_path: Path,
    *,
    first_pass_manifest: Path | None = None,
    limit: int | None = None,
    headless: bool = True,
    browser_channel: str = "auto",
    vision_model: str = DEFAULT_VISION_MODEL,
    enable_escalation: bool = True,
    save_all_screenshots: bool = False,
    use_cdp: bool = False,
    capsolver_api_key: str | None = None,
    enable_captcha_solver: bool = False,
) -> list[dict[str, Any]]:
    """Run browser-vision scout on seed records."""
    records = load_seed_records(seed_path)

    # Filter to second-pass candidates if first-pass manifest provided
    if first_pass_manifest is not None:
        candidate_urls = load_first_pass_candidates(first_pass_manifest)
        if candidate_urls:
            records = [r for r in records if r["page_url"] in candidate_urls]
            log.info(
                "bvs_filtered",
                extra={
                    "total_seed": len(load_seed_records(seed_path)),
                    "candidates": len(candidate_urls),
                    "matched": len(records),
                },
            )

    if limit is not None:
        records = records[:limit]

    if not records:
        log.info("bvs_no_records")
        return []

    run_id = _generate_run_id()
    prior_run_dirs = discover_prior_run_dirs(AUDITS_DIR)
    surface_cache_payload = build_source_surface_cache_payload_from_run_dirs(prior_run_dirs)

    # Set up CAPTCHA solver chain if requested
    captcha_solver: CaptchaSolverChain | None = None
    if enable_captcha_solver and HAS_CAPTCHA_SOLVER:
        captcha_solver = CaptchaSolverChain(
            capsolver_api_key=capsolver_api_key,
        )
        log.info("captcha_solver_enabled")

    # Choose browser backend
    if use_cdp:
        browser_ctx = CdpBrowserFetcher(auto_launch=True)
    else:
        browser_ctx = BrowserFetcher(headless=headless, browser_channel=browser_channel)

    results: list[dict[str, Any]] = []
    with browser_ctx as browser:
        extractor = VisionExtractor(
            model=vision_model,
            enable_escalation=enable_escalation,
        )
        for record in records:
            row = materialize_bvs_record(
                record,
                browser=browser,
                extractor=extractor,
                surface_cache_payload=surface_cache_payload,
                run_id=run_id,
                save_all_screenshots=save_all_screenshots,
                captcha_solver=captcha_solver,
            )
            results.append(row)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        for row in results:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    return results


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description=(
            "Browser-vision second-pass price scout. "
            "NOT Anthropic Computer Use — uses Playwright + Claude Vision API."
        ),
    )
    parser.add_argument("--seed", default=str(DEFAULT_BVS_SEED_FILE))
    parser.add_argument("--manifest", default=str(DEFAULT_BVS_MANIFEST_FILE))
    parser.add_argument(
        "--first-pass-manifest",
        default=None,
        help="Path to first-pass manifest for candidate filtering",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed (visible) mode",
    )
    parser.add_argument(
        "--browser-channel",
        default="auto",
        choices=["auto", "msedge", "chrome", "chromium", "bundled"],
        help="Browser channel (default: auto = try msedge, chrome, then bundled)",
    )
    parser.add_argument(
        "--vision-model",
        default=DEFAULT_VISION_MODEL,
        help=f"Claude model for vision extraction (default: {DEFAULT_VISION_MODEL})",
    )
    parser.add_argument(
        "--no-escalation",
        action="store_true",
        help="Disable auto-escalation to Opus on low confidence",
    )
    parser.add_argument(
        "--save-all-screenshots",
        action="store_true",
        help="Save screenshots for all records, not just noteworthy ones",
    )
    parser.add_argument(
        "--cdp-auto",
        action="store_true",
        help="Use CDP mode: auto-launch Edge with debugging port for anti-bot bypass",
    )
    parser.add_argument(
        "--captcha-solver",
        action="store_true",
        help="Enable CAPTCHA solver chain (FlareSolverr -> CapSolver)",
    )
    parser.add_argument(
        "--capsolver-key",
        default=None,
        help="CapSolver API key (or set CAPSOLVER_API_KEY env var)",
    )

    args = parser.parse_args()

    results = run(
        Path(args.seed),
        Path(args.manifest),
        first_pass_manifest=Path(args.first_pass_manifest) if args.first_pass_manifest else None,
        limit=args.limit,
        headless=not args.headed,
        browser_channel=args.browser_channel,
        vision_model=args.vision_model,
        enable_escalation=not args.no_escalation,
        save_all_screenshots=args.save_all_screenshots,
        use_cdp=args.cdp_auto,
        capsolver_api_key=args.capsolver_key,
        enable_captcha_solver=args.captcha_solver,
    )

    print(f"seed_records={len(results)} manifest={args.manifest}")
    for row in results:
        esc = " [ESCALATED]" if row.get("escalated_to_opus") else ""
        blk = " [BLOCKED_UI]" if row.get("blocked_ui_detected") else ""
        print(
            f"  {row['part_number']}: status={row['price_status']} "
            f"price={row['price_per_unit']} {row['currency']} "
            f"tier={row['source_tier']} lineage={row['price_source_exact_product_lineage_confirmed']} "
            f"vision_conf={row['vision_confidence']} "
            f"model={row['vision_model']}{esc}{blk}"
        )


if __name__ == "__main__":
    main()

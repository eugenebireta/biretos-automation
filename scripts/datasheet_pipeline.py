"""datasheet_pipeline.py — Official datasheet / PDF search and extraction.

Phase A: SerpAPI search + PyMuPDF / pdfplumber parse.
Phase B (GPU, feature-flagged): PaddleOCR-VL for scanned/image PDFs.

Search priority:
  1. Official manufacturer PDF (honeywell.com, esser-systems.com, etc.)
  2. Authorized distributor PDF (mouser, newark, etc.)
  3. Industrial B2B
  4. Datasheet aggregators (last resort — low price trust, ok for specs)

PN confirmation is required inside the PDF text.
"""
from __future__ import annotations

import io
import logging
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from serpapi import GoogleSearch

# Local imports — same package directory
_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from pn_match import confirm_pn_body
from trust import get_source_tier, get_source_weight

log = logging.getLogger(__name__)

# ── Optional PDF parsers ─────────────────────────────────────────────────────────

try:
    import fitz  # PyMuPDF — preferred: fast, accurate
    _PYMUPDF = True
except ImportError:
    _PYMUPDF = False

try:
    import pdfplumber  # fallback
    _PDFPLUMBER = True
except ImportError:
    _PDFPLUMBER = False

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,text/html,*/*;q=0.8",
}

# Official manufacturer domains — highest search priority
_OFFICIAL_DOMAINS = frozenset({
    "honeywell.com", "honeywellprocess.com", "honeywellsensing.com",
    "esser-systems.com", "esser.de", "intermec.com",
    "sperian.com", "sperian-protection.com", "uvex-safety.com",
})

# Authorized distributor domains
_AUTHORIZED_DOMAINS = frozenset({
    "grainger.com", "newark.com", "mouser.com", "digikey.com",
    "rs-online.com", "element14.com", "farnell.com",
    "automation24.com", "igs-hagen.de",
})


# ── Internal helpers ─────────────────────────────────────────────────────────────

def _pdf_url_score(url: str) -> int:
    """Score PDF URL by source trust. 0-100 (higher = better)."""
    netloc = urlparse(url).netloc.lower()
    if any(d in netloc for d in _OFFICIAL_DOMAINS):
        return 100
    if any(d in netloc for d in _AUTHORIZED_DOMAINS):
        return 75
    weight = get_source_weight(url)
    return int(weight * 60)


def _search_pdfs(pn: str, brand: str, serpapi_key: str) -> list[dict]:
    query = (
        f'"{pn}" "{brand}" '
        f'(datasheet OR "product specification" OR "technical specification" '
        f'OR "техническое описание" OR "паспорт изделия") '
        f'filetype:pdf'
    )
    try:
        params = {
            "engine": "google",
            "q": query,
            "num": 10,
            "gl": "us",
            "hl": "en",
            "api_key": serpapi_key,
        }
        results = GoogleSearch(params).get_dict().get("organic_results", [])
        time.sleep(0.4)
        return results
    except Exception as e:
        log.warning(f"datasheet search error [{pn}]: {e}")
        return []


def _fetch_pdf(url: str) -> Optional[bytes]:
    """Download PDF bytes. Returns None on any failure."""
    try:
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=20, stream=True)
        if r.status_code != 200:
            return None
        ct = r.headers.get("content-type", "")
        if "pdf" not in ct and not url.lower().split("?")[0].endswith(".pdf"):
            return None
        data = r.content
        # Minimum valid PDF size + magic bytes check
        if len(data) < 4096 or not data.startswith(b"%PDF"):
            return None
        return data
    except Exception as e:
        log.debug(f"pdf fetch error [{url[:60]}]: {e}")
        return None


def _parse_pymupdf(pdf_bytes: bytes) -> dict:
    """Extract text and structure from PDF via PyMuPDF (fitz)."""
    result: dict = {
        "title": "", "text_pages": [], "specs": {},
        "num_pages": 0, "parse_method": "pymupdf", "parse_ok": False,
    }
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        result["num_pages"] = len(doc)
        for page_num in range(min(6, len(doc))):
            result["text_pages"].append(doc[page_num].get_text("text"))
        doc.close()
        result["parse_ok"] = True
    except Exception as e:
        result["parse_error"] = str(e)
    return result


def _parse_pdfplumber(pdf_bytes: bytes) -> dict:
    """Extract text via pdfplumber (fallback)."""
    result: dict = {
        "title": "", "text_pages": [], "specs": {},
        "num_pages": 0, "parse_method": "pdfplumber", "parse_ok": False,
    }
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            result["num_pages"] = len(pdf.pages)
            for page in pdf.pages[:6]:
                result["text_pages"].append(page.extract_text() or "")
        result["parse_ok"] = True
    except Exception as e:
        result["parse_error"] = str(e)
    return result


_SPEC_RE = re.compile(r"^(.{3,50}?)[\s:\.]{2,}(.{1,100})\s*$", re.MULTILINE)


def _extract_specs(full_text: str) -> dict:
    """Extract key-value specs from PDF text using heuristic pattern."""
    specs: dict = {}
    for m in _SPEC_RE.finditer(full_text[:10000]):
        k, v = m.group(1).strip(), m.group(2).strip()
        if (k and v and len(k) < 55 and len(v) < 120
                and not k.startswith(("#", "*", "-"))
                and any(c.isalpha() for c in k)):
            specs[k] = v
    return dict(list(specs.items())[:35])


def _title_from_first_page(text_pages: list[str]) -> str:
    if not text_pages:
        return ""
    lines = [l.strip() for l in text_pages[0].split("\n") if l.strip()]
    return lines[0][:200] if lines else ""


# ── Phase B adapter (GPU, feature-flagged) ───────────────────────────────────────

def _phase_b_ocr_available() -> bool:
    """True if PaddleOCR-VL is installed and enabled (Phase B GPU stage)."""
    import os
    if os.environ.get("LOCAL_OCR_ENABLED", "").lower() not in ("1", "true", "yes"):
        return False
    try:
        import paddleocr  # noqa: F401
        return True
    except ImportError:
        return False


def _parse_with_ocr_fallback(pdf_bytes: bytes) -> dict:
    """Phase B: PaddleOCR-VL for scanned/image PDFs. Stub — not implemented."""
    log.info("  datasheet: Phase B OCR requested but not implemented yet")
    return {"text_pages": [], "parse_ok": False, "parse_method": "ocr_stub"}


# ── Public API ───────────────────────────────────────────────────────────────────

def find_datasheet(
    pn: str,
    brand: str,
    serpapi_key: str,
    output_dir: Optional[Path] = None,
    phase_b_ocr: bool = False,
) -> dict:
    """Find, download, and parse the best available datasheet for a product.

    Args:
        pn:           Part number.
        brand:        Brand (Honeywell / Esser / etc.).
        serpapi_key:  SerpAPI key.
        output_dir:   If set, saves PDF file to this directory.
        phase_b_ocr:  If True, attempt GPU OCR on parse failure (Phase B, stub).

    Returns:
        Evidence dict with keys:
          datasheet_status: "found" | "not_found" | "no_parser" | "no_pn_confirm"
          pdf_url, pdf_source_tier, pdf_title, pdf_specs, pdf_text_excerpt,
          num_pages, parse_method, pn_confirmed_in_pdf
    """
    empty: dict = {
        "datasheet_status": "not_found",
        "pdf_url": None,
        "pdf_source_tier": None,
        "pdf_title": None,
        "pdf_specs": {},
        "pdf_text_excerpt": None,
        "num_pages": 0,
        "parse_method": None,
        "pn_confirmed_in_pdf": False,
    }

    if not _PYMUPDF and not _PDFPLUMBER:
        log.warning("datasheet: no PDF parser (install pymupdf or pdfplumber)")
        return {**empty, "datasheet_status": "no_parser"}

    raw_results = _search_pdfs(pn, brand, serpapi_key)
    if not raw_results:
        return empty

    candidates = sorted(
        [{"url": r.get("link", ""), "title": r.get("title", ""),
          "score": _pdf_url_score(r.get("link", ""))}
         for r in raw_results if r.get("link")],
        key=lambda x: x["score"],
        reverse=True,
    )

    for cand in candidates[:5]:
        url = cand["url"]
        log.info(f"  datasheet trying [{cand['score']}]: {url[:70]}")

        pdf_bytes = _fetch_pdf(url)
        if not pdf_bytes:
            continue

        # Parse — PyMuPDF preferred
        if _PYMUPDF:
            parsed = _parse_pymupdf(pdf_bytes)
        else:
            parsed = _parse_pdfplumber(pdf_bytes)

        # Phase B fallback: GPU OCR for image-only PDFs
        if not parsed.get("parse_ok") and phase_b_ocr and _phase_b_ocr_available():
            parsed = _parse_with_ocr_fallback(pdf_bytes)

        if not parsed.get("parse_ok"):
            log.debug(f"  datasheet parse failed: {url[:60]}")
            continue

        full_text = "\n".join(parsed["text_pages"])

        # PN confirmation inside PDF
        pn_ok, _ = confirm_pn_body(pn, full_text)

        # Title from first page
        title = _title_from_first_page(parsed["text_pages"]) or cand["title"][:200]

        # Specs
        specs = _extract_specs(full_text)

        # Excerpt for description seed
        excerpt = full_text[:600].replace("\n", " ").strip() or None

        # Optionally save PDF
        if output_dir and output_dir.exists():
            safe_pn = re.sub(r'[\\/:*?"<>|]', "_", pn)
            pdf_path = output_dir / f"{safe_pn}_datasheet.pdf"
            try:
                pdf_path.write_bytes(pdf_bytes)
                log.info(f"  datasheet saved: {pdf_path.name}")
            except Exception as e:
                log.warning(f"  datasheet save failed: {e}")

        return {
            "datasheet_status": "found" if pn_ok else "no_pn_confirm",
            "pdf_url": url,
            "pdf_source_tier": get_source_tier(url),
            "pdf_title": title,
            "pdf_specs": specs,
            "pdf_text_excerpt": excerpt,
            "num_pages": parsed.get("num_pages", 0),
            "parse_method": parsed.get("parse_method"),
            "pn_confirmed_in_pdf": pn_ok,
        }

    return empty

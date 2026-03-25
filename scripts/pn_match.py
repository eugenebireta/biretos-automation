"""pn_match.py — Strong exact-PN matching with numeric guard.

Precision-first design:
- Numeric / dotted-numeric PNs use STRICT mode: also blocks dash-adjacent tokens.
  Prevents '00020211' matching inside 'SL22-020211-K6'.
- Structured contexts (JSON-LD mpn/sku, title, h1, product DOM) always trusted.
- body-only numeric match → low confidence (50) + numeric_guard_triggered flag.
- Alphanumeric PNs use standard word-boundary (dash OK as separator).
"""
from __future__ import annotations

import json
import re
from typing import Optional

from bs4 import BeautifulSoup


# ── PN type detection ───────────────────────────────────────────────────────────

_NUMERIC_PN_RE = re.compile(r"^\d[\d.]*\d$|^\d+$")
"""Pure numeric or dotted-numeric: 00020211, 010130.10, 033588.17, 1000106"""


def is_numeric_pn(pn: str) -> bool:
    """True if PN has no letters — only digits, dots (no leading/trailing dot)."""
    return bool(_NUMERIC_PN_RE.match(pn.strip()))


# ── Pattern builders ────────────────────────────────────────────────────────────

def _body_pattern(pn: str, strict: bool = False) -> re.Pattern:
    """Word-boundary pattern for PN in plain text.

    strict=True  → also blocks adjacent dash ('-').
                   Prevents '00020211' matching in 'SL22-020211-K6'.
    strict=False → standard: only blocks letters/digits (dash is OK separator).
    """
    escaped = re.escape(pn)
    if strict:
        return re.compile(r"(?<![A-Za-z0-9\-])" + escaped + r"(?![A-Za-z0-9\-])")
    return re.compile(r"(?<![A-Za-z0-9])" + escaped + r"(?![A-Za-z0-9])")


# ── Body match ──────────────────────────────────────────────────────────────────

def confirm_pn_body(pn: str, text: str) -> tuple[bool, str]:
    """Check PN in plain text (body / snippet / trafilatura output).

    Numeric PNs automatically use strict mode.

    Returns:
        (matched: bool, location: str)  location = "body" or "".
    """
    strict = is_numeric_pn(pn)
    pattern = _body_pattern(pn, strict=strict)
    if pattern.search(text):
        return True, "body"
    return False, ""


# ── Structured match ────────────────────────────────────────────────────────────

# DOM attributes / itemprop values that indicate a product-identifying context
_PRODUCT_CONTEXT_ITEMPROP = {"sku", "mpn", "productid", "gtin", "model", "identifier"}
_PRODUCT_CONTEXT_KEYWORDS = frozenset(
    ("sku", "mpn", "part-number", "partnumber", "partno", "model-number",
     "modelnumber", "article-number", "articlenumber", "catalog-number",
     "catalogno", "product-id", "productid", "item-number", "itemno")
)


def _jsonld_pn_match(pn: str, soup: BeautifulSoup) -> bool:
    """Exact match of pn against JSON-LD Product mpn / sku / gtin fields."""
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
            for field in ("mpn", "sku", "gtin13", "gtin12", "gtin8", "gtin"):
                val = str(item.get(field) or "").strip()
                if val and pn.strip().lower() == val.lower():
                    return True
    return False


def _title_pn_match(pn: str, soup: BeautifulSoup) -> bool:
    title_tag = soup.find("title")
    if not title_tag:
        return False
    return bool(_body_pattern(pn, strict=False).search(title_tag.get_text(" ", strip=True)))


def _h1_pn_match(pn: str, soup: BeautifulSoup) -> bool:
    h1_tag = soup.find("h1")
    if not h1_tag:
        return False
    return bool(_body_pattern(pn, strict=False).search(h1_tag.get_text(" ", strip=True)))


def _product_context_match(pn: str, soup: BeautifulSoup) -> bool:
    """Check itemprop product fields and DOM elements with product-context class/id."""
    pn_lower = pn.strip().lower()

    for tag in soup.find_all(True):
        # itemprop exact values
        itemprop = str(tag.get("itemprop") or "").lower()
        if itemprop in _PRODUCT_CONTEXT_ITEMPROP:
            tag_text = tag.get_text(strip=True).lower()
            if pn_lower == tag_text:
                return True

        # class/id keyword match + word-boundary PN check
        tag_id = str(tag.get("id") or "").lower().replace("-", "").replace("_", "")
        tag_cls = " ".join(tag.get("class") or []).lower().replace("-", "").replace("_", "")
        if any(kw.replace("-", "") in tag_id or kw.replace("-", "") in tag_cls
               for kw in _PRODUCT_CONTEXT_KEYWORDS):
            tag_text = tag.get_text(" ", strip=True)
            if _body_pattern(pn, strict=False).search(tag_text):
                return True

    return False


def confirm_pn_structured(pn: str, html: str) -> tuple[bool, str]:
    """Check PN in authoritative structured contexts.

    Priority: JSON-LD → title → h1 → product_context DOM.

    Returns:
        (matched: bool, location: str)
        location ∈ {"jsonld", "title", "h1", "product_context", ""}.
    """
    soup = BeautifulSoup(html, "html.parser")

    if _jsonld_pn_match(pn, soup):
        return True, "jsonld"
    if _title_pn_match(pn, soup):
        return True, "title"
    if _h1_pn_match(pn, soup):
        return True, "h1"
    if _product_context_match(pn, soup):
        return True, "product_context"

    return False, ""


# ── Full result ─────────────────────────────────────────────────────────────────

class PNMatchResult:
    """Full PN match result with trace fields for evidence bundle."""

    __slots__ = (
        "matched", "location", "is_numeric",
        "numeric_guard_triggered", "confidence",
    )

    def __init__(self) -> None:
        self.matched: bool = False
        self.location: str = ""           # jsonld|title|h1|product_context|body|""
        self.is_numeric: bool = False
        self.numeric_guard_triggered: bool = False
        self.confidence: int = 0          # 0-100

    def as_dict(self) -> dict:
        return {
            "pn_matched": self.matched,
            "pn_match_location": self.location,
            "pn_match_is_numeric": self.is_numeric,
            "numeric_pn_guard_triggered": self.numeric_guard_triggered,
            "pn_match_confidence": self.confidence,
        }


def match_pn(pn: str, text: str, html: str = "") -> PNMatchResult:
    """Full PN matching with structured-first priority.

    Logic:
      1. Structured (JSON-LD / title / h1 / product_context) → confidence 100
      2. Body strict/non-strict → confidence 90 (alphanum) or 50 (numeric)
         Numeric body-only → numeric_guard_triggered = True

    Usage:
      result = match_pn(pn, clean_text, raw_html)
      if result.matched and result.confidence >= 90:
          # high-confidence match, proceed
    """
    result = PNMatchResult()
    result.is_numeric = is_numeric_pn(pn)

    # 1. Structured contexts (highest authority)
    if html:
        struct_ok, struct_loc = confirm_pn_structured(pn, html)
        if struct_ok:
            result.matched = True
            result.location = struct_loc
            result.confidence = 100
            return result

    # 2. Body match (strict for numeric PNs)
    body_ok, _ = confirm_pn_body(pn, text)
    if body_ok:
        result.matched = True
        result.location = "body"
        if result.is_numeric:
            result.confidence = 50
            result.numeric_guard_triggered = True
        else:
            result.confidence = 90
    else:
        # Numeric PN not found even in body → flag as potential guard issue
        if result.is_numeric:
            result.numeric_guard_triggered = True

    return result

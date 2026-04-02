"""identity_guard.py — All identity guards in one module.

Pure functions. No side effects. No API calls. Easily testable.

Guards:
  is_identity_proof()         — is the PN match location an authoritative proof?
  check_negative_identity()   — detect accessory/compatibility page patterns
  check_cross_pollination()   — detect multi-SKU / catalog pages
  classify_photo_type()       — deterministic photo tier (no VLM)
  is_family_photo_allowed()   — whitelist check for family photo
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_WHITELIST_PATH = Path(__file__).parent.parent / "config" / "family_photo_whitelist.json"

# ── Locations considered authoritative identity proof ─────────────────────────
_PROOF_LOCATIONS = frozenset(["jsonld", "title", "h1", "product_context"])

# ── Negative identity patterns ────────────────────────────────────────────────
_NEGATIVE_PATTERNS: list[str] = [
    "suitable for",
    "for use with",
    "compatible with",
    "kit includes",
    "replacement for",
    "works with",
    "fits",
    "designed for",
    "catalog",
    "matrix",
    "options",
    "overview",
    "comparison",
]

# Words that are NOT reject signals if SKU category itself contains them
_ACCESSORY_EXEMPT_WORDS: frozenset[str] = frozenset(
    ["accessory", "mounting", "bracket", "cable"]
)


# ── is_identity_proof ─────────────────────────────────────────────────────────

def is_identity_proof(
    pn: str,
    match_location: str,
    match_context: str = "",
) -> bool:
    """Return True if match constitutes identity proof (not search expansion).

    Proof locations (jsonld / title / h1 / product_context) → always True.
    body → True only if PN is an isolated token (not substring of another code).
    Any other location → False.
    """
    if match_location in _PROOF_LOCATIONS:
        return True
    if match_location == "body":
        if not match_context:
            # Body match without context — conservative: not proof
            return False
        return _is_isolated_token(pn, match_context)
    return False


def _is_isolated_token(pn: str, text: str) -> bool:
    """True if pn appears as a standalone token — not inside a longer alphanumeric code."""
    escaped = re.escape(pn)
    pattern = re.compile(
        r"(?<![A-Za-z0-9\-])" + escaped + r"(?![A-Za-z0-9\-])"
    )
    return bool(pattern.search(text))


# ── check_negative_identity ───────────────────────────────────────────────────

def check_negative_identity(
    page_text: str,
    expected_category: str = "",
) -> list[str]:
    """Return list of triggered negative identity patterns.

    These patterns indicate the page is about accessories, compatibility, or
    a multi-product catalog — not the specific product itself.

    Exception: if expected_category of the SKU itself is an accessory/mounting/
    bracket/cable type, those specific words are not treated as reject signals.
    """
    cat_lower = expected_category.lower()
    is_accessory_sku = any(w in cat_lower for w in _ACCESSORY_EXEMPT_WORDS)

    text_lower = page_text.lower()
    triggered: list[str] = []

    for pattern in _NEGATIVE_PATTERNS:
        # Skip pattern if it matches an exempt word AND the SKU is an accessory
        if is_accessory_sku and any(w in pattern for w in _ACCESSORY_EXEMPT_WORDS):
            continue
        if pattern in text_lower:
            triggered.append(pattern)

    return triggered


# ── check_cross_pollination ───────────────────────────────────────────────────

def check_cross_pollination(page_pns: list[str], target_pn: str) -> bool:
    """Return True if page shows signs of cross-pollination.

    Triggers when:
    - 3 or more different PNs found on page (catalog / matrix page)
    - Any PN other than target_pn is present (another product's code in structured context)

    Phase A uses this conservatively: even a single "other PN" on a page
    is enough to mark the candidate as cross-pollinated.
    """
    if not page_pns:
        return False

    target_norm = target_pn.strip().lower()
    other_pns = [p for p in page_pns if p.strip().lower() != target_norm]

    # Hard case: 3+ distinct non-target PNs → definitely a catalog page
    if len(other_pns) >= 3:
        return True

    # Softer case: any single "other PN" present alongside target
    if other_pns:
        return True

    return False


# ── classify_photo_type ───────────────────────────────────────────────────────

def classify_photo_type(signals: dict) -> str:
    """Classify photo tier using deterministic signals (no VLM required).

    signals keys (all optional, default False):
      jsonld_image   (bool) — image came from JSON-LD Product schema
      pn_in_title    (bool) — exact PN found in page title or h1
      pn_in_url      (bool) — PN appears in image URL
      page_is_family (bool) — page title/breadcrumbs indicate a family/series page
      source_role    (str)  — source role (unused in Phase A, reserved)

    Returns: "exact_photo" | "family_photo" | "unknown"

    unknown = treated conservatively as family_photo by card_status calculator.
    """
    page_is_family = bool(signals.get("page_is_family"))
    pn_in_url = bool(signals.get("pn_in_url"))
    jsonld_image = bool(signals.get("jsonld_image"))
    pn_in_title = bool(signals.get("pn_in_title"))

    # Family page signal overrides everything else
    if page_is_family:
        return "family_photo"

    # PN in image URL is a strong exact signal
    if pn_in_url:
        return "exact_photo"

    # JSON-LD image + PN confirmed in title/h1 = exact
    if jsonld_image and pn_in_title:
        return "exact_photo"

    # JSON-LD image but no title confirmation = conservative unknown
    # (image may be family/series image attached to a product page)
    if jsonld_image and not pn_in_title:
        return "unknown"

    return "unknown"


# ── is_family_photo_allowed ───────────────────────────────────────────────────

def is_family_photo_allowed(
    brand: str,
    series: str,
    whitelist: Optional[dict] = None,
) -> bool:
    """Return True if family photo is allowed for this brand/series.

    Checks config/family_photo_whitelist.json (or provided dict).
    Default policy: denied_by_default=True — anything not explicitly whitelisted
    returns False.

    Series matching uses re.fullmatch() on series_pattern.
    """
    if whitelist is None:
        whitelist = _load_whitelist()

    if not whitelist.get("denied_by_default", True):
        # If policy is allow-by-default, everything is allowed
        return True

    brand_lower = brand.strip().lower()
    for entry in whitelist.get("allowed_series", []):
        if entry.get("brand", "").strip().lower() != brand_lower:
            continue
        pattern = entry.get("series_pattern", "")
        if pattern and re.fullmatch(pattern, series.strip(), re.IGNORECASE):
            return True

    return False


# ── Whitelist loader ──────────────────────────────────────────────────────────

def _load_whitelist() -> dict:
    try:
        with open(_WHITELIST_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Could not load family_photo_whitelist: %s", exc)
        return {"denied_by_default": True, "allowed_series": []}

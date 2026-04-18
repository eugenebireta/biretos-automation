"""
merge_research_to_evidence.py — Merge enriched data from research_results/ into evidence/.

Source: research_results/result_<PN>.json  (final_recommendation block)
Target: downloads/evidence/evidence_<PN>.json

Merged fields (only if source is non-empty and target is missing/empty):
  - title_ru           → deep_research.title_ru
  - description_ru     → deep_research.description_ru
  - category_suggestion→ dr_category (if not already set)
  - price_value        → dr_price, dr_currency, dr_price_source (if not already set)
  - photo_url          → dr_image_url (if not already set)
  - specs              → deep_research.specs
  - identity_confirmed → deep_research.identity_confirmed
  - confidence         → deep_research.confidence
  - key_findings       → deep_research.key_findings

Policy:
  - Never overwrite existing non-empty dr_ fields (additive only)
  - Skip results where identity_confirmed=False
  - Skip garbage description_ru (contains "citeturn", length < 10)
  - Price: only merge if price_assessment is admissible_public_price
  - Always record merge metadata: merge_ts, merge_source

Usage:
    python scripts/merge_research_to_evidence.py [--dry-run] [--pn PN]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "research_results"
EVIDENCE_DIR = ROOT / "downloads" / "evidence"

ADMISSIBLE_PRICES = {"admissible_public_price", "public_price"}

# ── DR Price Sanity Configuration ─────────────────────────────────────────────────

# Maximum allowed divergence between DR price (in RUB) and reference price.
# If ratio > (1 + threshold) or ratio < 1/(1 + threshold), merge is blocked.
DR_PRICE_DIVERGENCE_THRESHOLD = 0.30  # 30% default

# Canonical product categories with per-unit price caps and pack-sale flag.
# max_eur: conservative upper bound for a SINGLE UNIT retail price.
# can_be_pack: True if this product is commonly sold in packs/boxes (Conrad, voelkner, etc.)
# Prices above max_eur → DR_PACK_SIGNAL_DETECTED flag → merge blocked.
# product_category in evidence is the authoritative field (normalized at import time).
CANONICAL_CATEGORIES: dict[str, dict] = {
    # PEHA electrical accessories — sold per 10/5 packs on Conrad/voelkner/puhy.cz
    "PEHA AURA frame":          {"max_eur": 80,   "can_be_pack": True},
    "PEHA NOVA frame":          {"max_eur": 150,  "can_be_pack": True},
    "PEHA DIALOG frame":        {"max_eur": 80,   "can_be_pack": True},
    "PEHA COMPACTA frame":      {"max_eur": 60,   "can_be_pack": True},
    "PEHA frame":               {"max_eur": 150,  "can_be_pack": True},
    "PEHA rocker switch":       {"max_eur": 20,   "can_be_pack": True},
    "PEHA push button":         {"max_eur": 25,   "can_be_pack": True},
    "PEHA insert":              {"max_eur": 30,   "can_be_pack": True},
    "PEHA socket":              {"max_eur": 40,   "can_be_pack": True},
    "PEHA electrical accessory":{"max_eur": 100,  "can_be_pack": True},
    "switch frame":             {"max_eur": 150,  "can_be_pack": True},
    "rocker switch":            {"max_eur": 20,   "can_be_pack": True},
    "rocker cover (wippe)":     {"max_eur": 20,   "can_be_pack": True},
    "socket insert (SCHUKO)":   {"max_eur": 30,   "can_be_pack": True},
    "socket cover plate":       {"max_eur": 30,   "can_be_pack": True},
    "cover plate":              {"max_eur": 50,   "can_be_pack": True},
    "blank plate":              {"max_eur": 30,   "can_be_pack": True},
    "blanking cover":           {"max_eur": 30,   "can_be_pack": True},
    # Fiber / cable — sold per unit, no pack trap
    "fiber pigtail":            {"max_eur": 5,    "can_be_pack": False},
    "fiber patch cable":        {"max_eur": 15,   "can_be_pack": False},
    "fiber patch panel":        {"max_eur": 200,  "can_be_pack": False},
    "cable":                    {"max_eur": 50,   "can_be_pack": False},
    "wire duct / raceway":      {"max_eur": 60,   "can_be_pack": False},
    # Small components — sometimes sold in bulk packs
    "fuse":                     {"max_eur": 10,   "can_be_pack": True},
    "terminal":                 {"max_eur": 10,   "can_be_pack": True},
    "terminal block":           {"max_eur": 30,   "can_be_pack": True},
    # PPE
    "earplugs (PPE)":           {"max_eur": 15,   "can_be_pack": True},
    "hearing protection":       {"max_eur": 60,   "can_be_pack": True},
    # Fire safety
    "fire detector":            {"max_eur": 300,  "can_be_pack": False},
    "detector base":            {"max_eur": 50,   "can_be_pack": False},
    "PA speaker":               {"max_eur": 200,  "can_be_pack": False},
    "Esser transponder":        {"max_eur": 500,  "can_be_pack": False},
    # HVAC
    "valve":                    {"max_eur": 500,  "can_be_pack": False},
    "valve actuator":           {"max_eur": 400,  "can_be_pack": False},
    "actuator":                 {"max_eur": 400,  "can_be_pack": False},
    "thermostat":               {"max_eur": 200,  "can_be_pack": False},
    # IT / computing
    "monitor":                  {"max_eur": 2000, "can_be_pack": False},
    "workstation":              {"max_eur": 5000, "can_be_pack": False},
    "media converter":          {"max_eur": 300,  "can_be_pack": False},
    "network switch":           {"max_eur": 1000, "can_be_pack": False},
}

# Backward-compat alias so existing callers of CATEGORY_UNIT_PRICE_LIMITS_EUR still work.
CATEGORY_UNIT_PRICE_LIMITS_EUR = {k: v["max_eur"] for k, v in CANONICAL_CATEGORIES.items()}


def _classify_from_title(assembled_title: str) -> str:
    """Classify product category from Russian assembled_title keywords.
    Returns canonical category name or empty string if unknown.
    """
    t = assembled_title
    if "PEHA AURA" in t:
        if "Рамка" in t:
            return "PEHA AURA frame"
        if "Клавиша" in t:
            return "PEHA rocker switch"
        if "Вставка" in t:
            return "PEHA insert"
        if "Розетка" in t:
            return "PEHA socket"
        return "PEHA electrical accessory"
    if "PEHA NOVA" in t:
        if "Рамка" in t:
            return "PEHA NOVA frame"
        if "Клавиша" in t:
            return "PEHA rocker switch"
        return "PEHA electrical accessory"
    if "PEHA DIALOG" in t:
        if "Рамка" in t:
            return "PEHA DIALOG frame"
        if "Клавиша" in t:
            return "PEHA rocker switch"
        return "PEHA electrical accessory"
    if "PEHA COMPACTA" in t:
        return "PEHA COMPACTA frame"
    if "PEHA" in t:
        if "Рамка" in t:
            return "PEHA frame"
        if "Клавиша" in t:
            return "PEHA rocker switch"
        if "Кнопка" in t:
            return "PEHA push button"
        if "Розетка" in t:
            return "PEHA socket"
        if "Вставка" in t:
            return "PEHA insert"
        return "PEHA electrical accessory"
    if "Пигтейл" in t:
        return "fiber pigtail"
    if "Клапан" in t:
        return "valve"
    if "Привод" in t:
        return "valve actuator"
    if "Термостат" in t:
        return "thermostat"
    if "Извещатель" in t:
        return "fire detector"
    if "Предохранитель" in t:
        return "fuse"
    if "Клемм" in t:
        return "terminal block"
    if "Беруши" in t:
        return "earplugs (PPE)"
    if "Наушники" in t:
        return "hearing protection"
    if "Монитор" in t:
        return "monitor"
    if "Рабочая станция" in t or "Ноутбук" in t:
        return "workstation"
    if "Медиаконвертер" in t:
        return "media converter"
    if "Свитч" in t:
        return "network switch"
    if "Кабель-канал" in t:
        return "wire duct / raceway"
    if "Кабель" in t:
        return "cable"
    return ""


def _normalize_category(raw_cat: str, assembled_title: str = "") -> str:
    """Normalize raw DR category string → canonical name from CANONICAL_CATEGORIES.

    Priority:
    1. Direct case-insensitive key match
    2. PEHA sub-series detection from assembled_title
    3. Keyword-based mapping from raw_cat
    4. classify_from_title fallback
    5. Returns raw_cat stripped if nothing matches (stored as-is)
    """
    # Treat garbage / placeholder values as empty
    _GARBAGE = {"not_found", "not found", "none", "null", "n/a", "-----------", "no", "-", "unknown"}
    if not raw_cat or raw_cat.strip().lower() in _GARBAGE:
        return _classify_from_title(assembled_title)

    # 1. Direct case-insensitive match
    raw_lower = raw_cat.strip().lower()
    for key in CANONICAL_CATEGORIES:
        if key.lower() == raw_lower:
            return key

    # 2. PEHA: use assembled_title for sub-series (more reliable than DR text)
    title_upper = assembled_title.upper()
    if "PEHA" in title_upper or "PEHA" in raw_cat.upper():
        result = _classify_from_title(assembled_title)
        if result:
            return result
        return "PEHA electrical accessory"

    # 3. Keyword rules on raw_cat
    KEYWORD_MAP = [
        (["frame", "switch frame"],               "switch frame"),
        (["rocker", "wippe"],                     "rocker cover (wippe)"),
        (["socket insert"],                       "socket insert (SCHUKO)"),
        (["socket cover", "socket faceplate"],    "socket cover plate"),
        (["cover plate", "blanking cover", "blank plate"], "cover plate"),
        (["valve actuator"],                      "valve actuator"),
        (["globe valve", "ball valve", "butterfly valve", "valve"], "valve"),
        (["actuator"],                            "actuator"),
        (["thermostat"],                          "thermostat"),
        (["pigtail"],                             "fiber pigtail"),
        (["patch cable", "patch cord"],           "fiber patch cable"),
        (["patch panel"],                         "fiber patch panel"),
        (["wire duct", "raceway", "cable duct"],  "wire duct / raceway"),
        (["fuse"],                                "fuse"),
        (["terminal block"],                      "terminal block"),
        (["terminal"],                            "terminal"),
        (["earplug", "ear plug"],                 "earplugs (PPE)"),
        (["hearing protection", "earmuff"],       "hearing protection"),
        (["fire detector", "smoke detector", "heat detector", "detector"], "fire detector"),
        (["detector base", "mounting base"],      "detector base"),
        (["speaker", "pa speaker", "pa cabinet"],"PA speaker"),
        (["transponder"],                         "Esser transponder"),
        (["media converter"],                     "media converter"),
        (["network switch", "managed switch"],    "network switch"),
        (["monitor", "display"],                  "monitor"),
        (["workstation", "laptop", "desktop"],    "workstation"),
        (["cable"],                               "cable"),
    ]
    for keywords, canonical in KEYWORD_MAP:
        for kw in keywords:
            if kw in raw_lower:
                return canonical

    # 4. Fallback: assembled_title rules
    result = _classify_from_title(assembled_title)
    if result:
        return result

    # 5. Unknown — return raw stripped (logged by caller)
    return raw_cat.strip()

# Pack detection via source URL patterns (Conrad/voelkner sell in packs)
_PACK_URL_MARKERS = re.compile(
    r"[-_](?:10|5|25|50|100)[-_]?(?:st|stk|pcs|pc|pack|box)\b"
    r"|[?&](?:qty|quantity|menge)=(?:[2-9]|\d{2,})"
    r"|/(?:10|5|25|50|100)-(?:st|stk|pcs|stueck)",
    re.IGNORECASE,
)

# Pack/kit/set markers that indicate price may be for a bundle, not a unit
_PACK_MARKERS = re.compile(
    r"(?:pack|box|lot|kit|set|bundle|case|carton|"
    r"упаковк|упак\b|коробк|набор|комплект|лот\b|пачк)",
    re.IGNORECASE,
)


def _parse_our_price_rub(raw: str | None) -> float | None:
    """Parse our_price_raw field from evidence (RUB, comma decimal).

    Examples: "2018,40" → 2018.40, "0,00" → None (zero = no price).
    """
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


def _dr_price_to_rub(amount: float, currency: str) -> float | None:
    """Convert DR price to RUB using live FX. Returns None if conversion fails."""
    if not amount or amount <= 0:
        return None
    cur = (currency or "").upper()
    if cur == "RUB":
        return amount
    try:
        from fx import convert_to_rub
        return convert_to_rub(amount, cur)
    except Exception:
        return None


def _has_pack_signal(fr: dict, category: str = "", product_category: str = "") -> bool:
    """Check if final_recommendation has pack/kit/set signals.

    Checks:
    1. Pack keywords in text (title, description, context)
    2. Pack patterns in source URL (Conrad/voelkner -10-st, -5-stk, etc.)
    3. Category price limit exceeded — uses product_category (evidence) if set,
       falls back to raw category (DR suggestion) otherwise.

    Args:
        fr: final_recommendation dict from result file
        category: raw category string from DR (category_suggestion)
        product_category: normalized canonical category from evidence (preferred)
    """
    text_parts = [
        str(fr.get("title_ru", "")),
        str(fr.get("description_ru", "")),
        str(fr.get("price_context", "")),
        str(fr.get("unit_info", "")),
    ]
    pv = fr.get("price_value", {})
    if isinstance(pv, dict):
        text_parts.append(str(pv.get("context", "")))
        text_parts.append(str(pv.get("unit", "")))
    combined = " ".join(text_parts)

    # 1. Text-based pack keywords
    if _PACK_MARKERS.search(combined):
        return True

    # 2. URL-based pack patterns
    source_url = pv.get("source_url", "") if isinstance(pv, dict) else ""
    if source_url and _PACK_URL_MARKERS.search(source_url):
        return True

    # 3. Category price limit check — prefer product_category (evidence-side, normalized)
    cat = (product_category or category or fr.get("category_suggestion", "") or "").strip()
    cat_info = CANONICAL_CATEGORIES.get(cat)
    limit = cat_info["max_eur"] if cat_info else None
    if limit and isinstance(pv, dict):
        amount = pv.get("amount", 0) or 0
        currency = (pv.get("currency", "") or "").upper()
        # Rough EUR conversion factors for pack limit check
        _TO_EUR = {"EUR": 1.0, "USD": 0.93, "GBP": 1.17, "CHF": 1.05,
                   "CZK": 0.040, "PLN": 0.23, "DKK": 0.134, "RUB": 0.010,
                   "SEK": 0.088, "NOK": 0.088, "HUF": 0.0026}
        rate = _TO_EUR.get(currency, None)
        if rate is not None:
            amount_eur = float(amount) * rate
            if amount_eur > limit:
                return True

    return False


def check_dr_price_sanity(
    dr_amount: float,
    dr_currency: str,
    reference_rub: float | None,
    fr: dict,
    threshold: float = DR_PRICE_DIVERGENCE_THRESHOLD,
    product_category: str = "",
) -> dict:
    """Validate DR price against reference before merge.

    Returns:
        {"allow_merge": bool, "reason": str, "flags": list[str],
         "dr_rub": float|None, "reference_rub": float|None, "ratio": float|None}
    """
    flags: list[str] = []
    dr_rub = _dr_price_to_rub(dr_amount, dr_currency)

    # Pack/kit signal detection (text + URL + category price limit)
    category = fr.get("category_suggestion", "")
    if _has_pack_signal(fr, category=category, product_category=product_category):
        flags.append("DR_PACK_SIGNAL_DETECTED")

    # If we can't convert DR price to RUB, still merge but flag it
    if dr_rub is None:
        flags.append("DR_PRICE_FX_FAILED")
        return {
            "allow_merge": len(flags) == 1,  # allow if only FX failed, block if pack signal too
            "reason": "cannot convert DR price to RUB" if not flags else "; ".join(flags),
            "flags": flags,
            "dr_rub": None,
            "reference_rub": reference_rub,
            "ratio": None,
        }

    # No reference price — can't validate, merge with flag
    if reference_rub is None:
        flags.append("NO_REFERENCE_PRICE")
        allow = "DR_PACK_SIGNAL_DETECTED" not in flags
        return {
            "allow_merge": allow,
            "reason": "no reference price for sanity check" if allow else "pack signal without reference",
            "flags": flags,
            "dr_rub": dr_rub,
            "reference_rub": None,
            "ratio": None,
        }

    # Compute ratio
    ratio = dr_rub / reference_rub if reference_rub > 0 else None
    if ratio is None:
        return {
            "allow_merge": True,
            "reason": "reference_rub is zero",
            "flags": flags,
            "dr_rub": dr_rub,
            "reference_rub": reference_rub,
            "ratio": None,
        }

    # Check divergence
    too_high = ratio > (1 + threshold)
    too_low = ratio < 1 / (1 + threshold)

    if too_high:
        flags.append(f"DR_PRICE_TOO_HIGH: ratio={ratio:.2f} (>{1+threshold:.2f})")
    if too_low:
        flags.append(f"DR_PRICE_TOO_LOW: ratio={ratio:.2f} (<{1/(1+threshold):.2f})")

    has_divergence = too_high or too_low
    has_pack = "DR_PACK_SIGNAL_DETECTED" in flags

    if has_divergence or has_pack:
        return {
            "allow_merge": False,
            "reason": "; ".join(flags),
            "flags": flags,
            "dr_rub": dr_rub,
            "reference_rub": reference_rub,
            "ratio": ratio,
        }

    return {
        "allow_merge": True,
        "reason": "sanity passed",
        "flags": flags,
        "dr_rub": dr_rub,
        "reference_rub": reference_rub,
        "ratio": ratio,
    }


def _is_empty(val) -> bool:
    """Check if a value is effectively empty."""
    if val is None:
        return True
    if isinstance(val, str):
        return val.strip() == "" or val.strip().lower() in ("not_found", "not found", "none", "null")
    if isinstance(val, dict):
        return len(val) == 0
    if isinstance(val, list):
        return len(val) == 0
    return False


def _is_garbage_description(desc: str) -> bool:
    """Detect garbage descriptions from LLM artifacts."""
    if not desc or len(desc.strip()) < 10:
        return True
    # Strip Unicode private-use characters before checking
    clean = re.sub(r"[\ue000-\uf8ff]", "", desc)
    if "citeturn" in clean.lower():
        return True
    if "cite" in clean.lower() and "turn" in clean.lower() and "view" in clean.lower():
        return True
    # Pure citation junk
    if re.match(r"^[\s\d\w]*cite[\s\d\w]*$", clean, re.IGNORECASE):
        return True
    # Too short after stripping
    if len(clean.strip()) < 10:
        return True
    return False


def _safe_filename(pn: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", pn)


def load_result(pn: str) -> dict | None:
    """Load research result for a PN."""
    path = RESULTS_DIR / f"result_{pn}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_evidence(pn: str) -> tuple[dict | None, Path]:
    """Load evidence file for a PN."""
    safe = _safe_filename(pn)
    path = EVIDENCE_DIR / f"evidence_{safe}.json"
    if not path.exists():
        return None, path
    try:
        return json.loads(path.read_text(encoding="utf-8")), path
    except (json.JSONDecodeError, OSError):
        return None, path


def merge_one(pn: str, dry_run: bool = False) -> dict:
    """Merge one result into its evidence file.

    Returns a status dict:
      {"pn": str, "action": "merged"|"skipped"|"no_result"|"no_evidence",
       "fields_added": list[str], "reason": str}
    """
    result = load_result(pn)
    if result is None:
        return {"pn": pn, "action": "no_result", "fields_added": [], "reason": "no research result"}

    evidence, ev_path = load_evidence(pn)
    if evidence is None:
        return {"pn": pn, "action": "no_evidence", "fields_added": [], "reason": "no evidence file"}

    fr = result.get("final_recommendation", {})
    if not fr:
        return {"pn": pn, "action": "skipped", "fields_added": [], "reason": "empty final_recommendation"}

    # Skip unconfirmed identity
    if fr.get("identity_confirmed") is False:
        return {"pn": pn, "action": "skipped", "fields_added": [],
                "reason": "identity_confirmed=False"}

    fields_added = []

    # -- deep_research block (additive) --
    dr = evidence.get("deep_research", {})
    if not isinstance(dr, dict):
        dr = {}

    # title_ru
    title_ru = fr.get("title_ru", "")
    if not _is_empty(title_ru) and _is_empty(dr.get("title_ru")):
        dr["title_ru"] = title_ru.strip()
        fields_added.append("title_ru")

    # description_ru — overwrite if new is good and old is empty/garbage/much shorter
    desc_ru = fr.get("description_ru", "")
    old_desc = dr.get("description_ru", "")
    if not _is_empty(desc_ru) and not _is_garbage_description(desc_ru):
        should_write = (
            _is_empty(old_desc)
            or _is_garbage_description(old_desc)
            or (len(desc_ru) > len(old_desc) * 1.5)
        )
        if should_write:
            dr["description_ru"] = desc_ru.strip()
            fields_added.append("description_ru")

    # specs
    specs = fr.get("specs", {})
    if not _is_empty(specs) and _is_empty(dr.get("specs")):
        dr["specs"] = specs
        fields_added.append("specs")

    # identity + confidence + key_findings
    if fr.get("identity_confirmed") is not None and "identity_confirmed" not in dr:
        dr["identity_confirmed"] = fr["identity_confirmed"]
        fields_added.append("identity_confirmed")

    confidence = fr.get("confidence") or result.get("confidence")
    if confidence and "confidence" not in dr:
        dr["confidence"] = confidence
        fields_added.append("dr_confidence")

    findings = fr.get("key_findings", [])
    if findings and _is_empty(dr.get("key_findings")):
        dr["key_findings"] = findings
        fields_added.append("key_findings")

    # sources from research
    sources = fr.get("sources", [])
    if sources and _is_empty(dr.get("sources")):
        dr["sources"] = sources
        fields_added.append("dr_sources")

    # Propagate description_ru → content.description_long_ru for Excel export
    desc_long = dr.get("description_ru", "")
    if desc_long and isinstance(evidence.get("content"), dict):
        if _is_empty(evidence["content"].get("description_long_ru")):
            evidence["content"]["description_long_ru"] = desc_long
            fields_added.append("content.description_long_ru")

    # Propagate provider/model from result (top-level, not final_recommendation) into evidence DR block
    provider_added = False
    if result.get("provider") and _is_empty(dr.get("provider")):
        dr["provider"] = result["provider"]
        provider_added = True
    if result.get("model") and _is_empty(dr.get("model")):
        dr["model"] = result["model"]
        provider_added = True
    if result.get("dr_source_file") and _is_empty(dr.get("source_file")):
        dr["source_file"] = result["dr_source_file"]
        provider_added = True
    if provider_added:
        evidence["deep_research"] = dr
        fields_added.append("dr_provider")

    # merge metadata
    if fields_added:
        dr["merge_ts"] = datetime.now(timezone.utc).isoformat()
        dr["merge_source"] = f"result_{pn}.json"
        evidence["deep_research"] = dr

    # -- Top-level dr_ fields (only if not already set) --

    # dr_category (raw DR output) + product_category (normalized canonical)
    cat = fr.get("category_suggestion", "")
    assembled_title = evidence.get("assembled_title", "")
    if not _is_empty(cat) and _is_empty(evidence.get("dr_category")):
        evidence["dr_category"] = cat.strip()
        fields_added.append("dr_category")
    # product_category: always recompute if missing (authoritative for price checks)
    if _is_empty(evidence.get("product_category")):
        raw_for_norm = cat if not _is_empty(cat) else evidence.get("dr_category", "")
        product_cat = _normalize_category(raw_for_norm, assembled_title)
        if product_cat:
            evidence["product_category"] = product_cat
            fields_added.append("product_category")

    # dr_image_url
    photo = fr.get("photo_url", "")
    if not _is_empty(photo) and _is_empty(evidence.get("dr_image_url")):
        evidence["dr_image_url"] = photo.strip()
        fields_added.append("dr_image_url")

    # dr_price, dr_currency, dr_price_source — WITH sanity check
    price_assessment = fr.get("price_assessment", "")
    price_value = fr.get("price_value", {})
    if (price_assessment in ADMISSIBLE_PRICES
            and isinstance(price_value, dict)
            and price_value.get("amount")
            and _is_empty(evidence.get("dr_price"))):
        dr_amount = price_value["amount"]
        dr_currency = price_value.get("currency", "")

        # Sanity check against reference price (our_price_raw from xlsx)
        reference_rub = _parse_our_price_rub(evidence.get("our_price_raw"))
        sanity = check_dr_price_sanity(
            dr_amount=dr_amount,
            dr_currency=dr_currency,
            reference_rub=reference_rub,
            fr=fr,
            product_category=evidence.get("product_category", ""),
        )

        if sanity["allow_merge"]:
            evidence["dr_price"] = dr_amount
            evidence["dr_currency"] = dr_currency
            evidence["dr_price_source"] = price_value.get("source_url", "")
            fields_added.append("dr_price")
            if sanity["flags"]:
                evidence["dr_price_sanity_flags"] = sanity["flags"]
        else:
            # Block merge — store both values for review
            evidence["dr_price_blocked"] = {
                "amount": dr_amount,
                "currency": dr_currency,
                "source_url": price_value.get("source_url", ""),
                "reason": sanity["reason"],
                "flags": sanity["flags"],
                "dr_rub": sanity["dr_rub"],
                "reference_rub": sanity["reference_rub"],
                "ratio": sanity["ratio"],
                "blocked_ts": datetime.now(timezone.utc).isoformat(),
            }
            fields_added.append("dr_price_blocked")
            log.warning(
                f"  DR price blocked for {pn}: {dr_amount} {dr_currency} "
                f"(reason: {sanity['reason']})"
            )

    if not fields_added:
        return {"pn": pn, "action": "skipped", "fields_added": [],
                "reason": "all fields already populated"}

    # Multi-source validation for DR prices (bounded — only high-risk SKUs)
    if "dr_price" in fields_added and not dry_run:
        try:
            from multi_source_prices import should_validate_multi_source, validate_dr_price_multi_source
            should_validate, trigger_reason = should_validate_multi_source(
                evidence, trigger_source="dr_only"
            )
            if should_validate:
                brand = evidence.get("brand", "")
                validate_dr_price_multi_source(evidence, pn, brand)
                if evidence.get("price_cross_validation") == "divergent":
                    fields_added.append("multi_source_divergent")
                    log.info(f"  multi-source validation: DIVERGENT for {pn}")
                elif evidence.get("price_cross_validation") == "consistent":
                    fields_added.append("multi_source_consistent")
        except Exception as e:
            log.debug(f"multi-source validation skipped for {pn}: {e}")

    if not dry_run:
        ev_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"pn": pn, "action": "merged", "fields_added": fields_added, "reason": ""}


def backfill_product_categories(dry_run: bool = False) -> dict:
    """Backfill product_category for existing evidence files that have dr_category but no product_category.

    Safe to run repeatedly — skips files that already have product_category.
    Returns summary: {total, updated, skipped, dry_run}
    """
    evidence_files = sorted(EVIDENCE_DIR.glob("evidence_*.json"))
    updated = 0
    skipped = 0

    for ev_path in evidence_files:
        try:
            evidence = json.loads(ev_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not _is_empty(evidence.get("product_category")):
            skipped += 1
            continue

        assembled_title = evidence.get("assembled_title", "")
        raw_cat = evidence.get("dr_category", "")
        product_cat = _normalize_category(raw_cat, assembled_title)

        if not product_cat:
            skipped += 1
            continue

        log.info(f"  backfill {evidence.get('pn','?')}: dr_category={raw_cat!r} → product_category={product_cat!r}")
        evidence["product_category"] = product_cat
        updated += 1

        if not dry_run:
            ev_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")

    log.info(f"Backfill complete: {updated} updated, {skipped} skipped")
    return {"total": len(evidence_files), "updated": updated, "skipped": skipped, "dry_run": dry_run}


def run(dry_run: bool = False, pn_filter: str | None = None) -> dict:
    """Run merge across all results.

    Returns summary dict.
    """
    result_files = sorted(RESULTS_DIR.glob("result_*.json"))
    pns = []
    for f in result_files:
        pn = f.stem.replace("result_", "")
        if pn_filter and pn != pn_filter:
            continue
        pns.append(pn)

    merged = 0
    skipped = 0
    no_evidence = 0
    no_result = 0
    all_fields = []
    details = []

    for pn in pns:
        status = merge_one(pn, dry_run=dry_run)
        details.append(status)
        if status["action"] == "merged":
            merged += 1
            all_fields.extend(status["fields_added"])
        elif status["action"] == "skipped":
            skipped += 1
        elif status["action"] == "no_evidence":
            no_evidence += 1
        elif status["action"] == "no_result":
            no_result += 1

    # Field counts
    from collections import Counter
    field_counts = dict(Counter(all_fields))

    summary = {
        "total": len(pns),
        "merged": merged,
        "skipped": skipped,
        "no_evidence": no_evidence,
        "no_result": no_result,
        "dry_run": dry_run,
        "field_counts": field_counts,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    log.info(f"Merge complete: {merged} merged, {skipped} skipped, "
             f"{no_evidence} no evidence, {no_result} no result")
    log.info(f"Fields added: {field_counts}")

    # Auto-normalize: update normalized{} blocks after evidence modification
    if not dry_run and merged > 0:
        print("\n[auto-normalize] Updating normalized{} blocks...")
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "evidence_normalize.py")],
            check=False,
        )

    return summary


def main():
    parser = argparse.ArgumentParser(description="Merge research results into evidence files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be merged without writing")
    parser.add_argument("--pn", type=str, default=None, help="Process only this PN")
    parser.add_argument("--backfill-categories", action="store_true",
                        help="Backfill product_category for existing evidence files (uses dr_category + assembled_title)")  # noqa: E501
    args = parser.parse_args()

    if args.backfill_categories:
        summary = backfill_product_categories(dry_run=args.dry_run)
    else:
        summary = run(dry_run=args.dry_run, pn_filter=args.pn)

    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.dry_run:
        print("\n[DRY RUN] No files were modified.")


if __name__ == "__main__":
    main()

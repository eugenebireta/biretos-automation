"""Universal Rules Engine — applies learned rules BEFORE making AI calls.

For every new SKU:
1. detect_brand_from_pn(pn) → tries brand regex library
2. predict_ean(pn, brand) → applies brand EAN formula if known
3. get_trusted_sources(brand, field) → where to search
4. check_red_flags(record) → auto-detect data issues
5. get_ai_model_for_task(task) → routes to cheapest adequate model

Savings: every AI call skipped when rule applies = permanent saving.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BRAND_REGISTRY = json.loads((ROOT / "config" / "brand_registry.json").read_text(encoding="utf-8"))
UNIVERSAL_RULES = json.loads((ROOT / "config" / "universal_rules.json").read_text(encoding="utf-8"))


def _ean13_check_digit(first_12: str) -> str:
    digits = [int(d) for d in first_12]
    s = sum(digits[i] * (3 if i % 2 else 1) for i in range(12))
    return str((10 - (s % 10)) % 10)


def validate_ean13(ean: str) -> bool:
    """Validate EAN-13 checksum."""
    if not ean or not ean.isdigit() or len(ean) != 13:
        return False
    return _ean13_check_digit(ean[:12]) == ean[12]


def detect_brand_from_pn(pn: str) -> dict:
    """Apply brand detection regex library. Returns None if unknown."""
    if not pn:
        return None

    for rule in UNIVERSAL_RULES.get("brand_detection_from_pn", []):
        if re.match(rule["regex"], pn):
            return {
                "brand": rule.get("brand") or rule.get("brand_candidates", [None])[0],
                "candidates": rule.get("brand_candidates", []),
                "product_hint": rule.get("product", ""),
                "needs_disambiguation": rule.get("requires_disambiguation", False),
                "confidence": "high" if rule.get("brand") else "medium",
            }
    return None


def predict_ean(pn: str, brand: str) -> dict:
    """Predict EAN for PN+brand using brand-specific formula. Returns None if no rule."""
    if not pn or not brand:
        return None

    brand_data = BRAND_REGISTRY.get(brand)
    if not brand_data:
        return None

    ean_rule = brand_data.get("ean_rule", {})
    prefix = ean_rule.get("company_prefix", "")
    if not prefix or ean_rule.get("confidence") in ("none", "low"):
        return None

    # PEHA: first 5 of normalized PN
    if brand == "PEHA":
        if not pn.replace("-", "").replace(".", "").isdigit():
            return None
        pn_5 = pn.lstrip("0").zfill(6)[:5]
        first_12 = prefix + pn_5
        ean = first_12 + _ean13_check_digit(first_12)
        return {
            "ean": ean,
            "source": "peha_rule_predicted",
            "confidence": ean_rule.get("confidence", "medium"),
            "verified_rate": ean_rule.get("verified_rate", 0),
        }

    # Howard Leight: last 5 of PN, try both prefixes
    if brand == "Howard Leight":
        if not pn.isdigit():
            return None
        pn_5 = pn[-5:]
        candidates = []
        for pref in prefix.split("|"):
            first_12 = pref + pn_5
            ean = first_12 + _ean13_check_digit(first_12)
            candidates.append(ean)
        return {
            "ean_candidates": candidates,
            "source": "hl_rule_candidates",
            "confidence": "medium",
            "note": "verify against actual datasheet",
        }

    # Generic: single prefix rule (for future brands)
    return None


def get_trusted_sources(brand: str, field_type: str = "all") -> list:
    """Get sources list for given field (price/specs/photo/datasheet)."""
    brand_data = BRAND_REGISTRY.get(brand, {})
    sources = brand_data.get("trusted_sources", {})

    if field_type == "all":
        all_urls = []
        for urls in sources.values():
            if isinstance(urls, list):
                all_urls.extend(urls)
        return list(set(all_urls))

    # Common field aliases
    if field_type == "specs":
        return sources.get("specs_and_datasheet", []) or sources.get("specs", [])
    if field_type == "price":
        return sources.get("price", [])
    if field_type == "photo":
        return (sources.get("photo", []) + sources.get("photo_manufacturer", []) +
                sources.get("photo_cdn", []) or sources.get("cdn_photo", []))
    if field_type == "datasheet":
        return sources.get("specs_and_datasheet", []) or sources.get("datasheet", [])

    return sources.get(field_type, [])


def check_red_flags(record: dict) -> list:
    """Check record against quality rules. Returns list of flags."""
    flags = []

    pn = record.get("pn", "")
    brand = record.get("brand", "")
    ean = record.get("ean", "")
    datasheet_title = record.get("datasheet_title", "")
    specs_count = record.get("specs_count", 0)
    datasheet_size_kb = record.get("datasheet_size_kb", 0)

    # Brand mismatch: PN format indicates different brand
    detected = detect_brand_from_pn(pn)
    if detected and detected.get("brand") and brand and detected["brand"] != brand:
        if not detected.get("needs_disambiguation"):
            flags.append({
                "rule": "brand_mismatch",
                "detail": f"PN pattern suggests {detected['brand']}, record says {brand}",
                "severity": "high",
            })

    # Wrong EAN prefix for brand
    if ean and validate_ean13(ean) and brand:
        brand_data = BRAND_REGISTRY.get(brand, {})
        expected_prefix = brand_data.get("ean_rule", {}).get("company_prefix", "")
        if expected_prefix and "|" in expected_prefix:
            expected_prefixes = expected_prefix.split("|")
            if not any(ean.startswith(p) for p in expected_prefixes):
                flags.append({
                    "rule": "wrong_ean_prefix",
                    "detail": f"EAN {ean[:7]} not in expected {expected_prefixes}",
                    "severity": "medium",
                })
        elif expected_prefix and not ean.startswith(expected_prefix):
            flags.append({
                "rule": "wrong_ean_prefix",
                "detail": f"EAN {ean[:7]} != expected {expected_prefix}",
                "severity": "medium",
            })

    # Empty datasheet big file
    if datasheet_size_kb > 5000 and specs_count == 0:
        flags.append({
            "rule": "empty_datasheet_big_file",
            "detail": f"PDF {datasheet_size_kb}KB but 0 specs — likely wrong document",
            "severity": "high",
        })

    # Title mismatch
    if datasheet_title and pn:
        if pn.lower() not in datasheet_title.lower() and pn.replace("-", "").replace(".", "").lower() not in datasheet_title.lower().replace("-", "").replace(".", ""):
            seed = record.get("seed_name", "").lower()
            title_lower = datasheet_title.lower()
            common_words = set(seed.split()) & set(title_lower.split())
            if len(common_words) < 2:
                flags.append({
                    "rule": "datasheet_title_mismatch",
                    "detail": f"Title '{datasheet_title[:60]}' doesn't match PN/seed",
                    "severity": "high",
                })

    return flags


def get_ai_model_for_task(task: str) -> dict:
    """Route to appropriate AI model."""
    routing = UNIVERSAL_RULES.get("ai_routing_rules", {}).get("tasks", {})
    return routing.get(task, {
        "primary": "gemini-2.5-flash",
        "reasoning": "default to cheapest",
    })


def get_datasheet_url_candidates(pn: str, brand: str) -> list:
    """Build datasheet URL candidates from brand patterns."""
    brand_data = BRAND_REGISTRY.get(brand, {})
    patterns = brand_data.get("datasheet_location_pattern", [])
    urls = []
    for pat in patterns:
        url = pat.format(pn=pn.lower(), brand=brand.lower())
        urls.append(url)
    return urls


def needs_usa_vps(url: str) -> bool:
    """Check if URL requires USA VPS to download."""
    usa_blocked = [
        "prod-edam.honeywell.com", "honeywell.scene7.com",
        "buildings.honeywell.com", "automation.honeywell.com",
        "sps.honeywell.com", "sps-support.honeywell.com",
        "process.honeywell.com", "honeywellsafety.com",
    ]
    return any(d in url for d in usa_blocked)


# ── Main demo ──
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    # Demo: apply rules to new SKU
    print("=" * 70)
    print("Universal Rules Engine — demo")
    print("=" * 70)

    test_cases = [
        {"pn": "109411", "brand": "PEHA", "ean": ""},
        {"pn": "2CDG110146R0011", "brand": "Honeywell", "ean": "4016779866699"},
        {"pn": "P2421D", "brand": "Honeywell", "ean": ""},  # actually Dell
        {"pn": "V5329A1053", "brand": "Honeywell", "ean": ""},
        {"pn": "CF274A", "brand": "Honeywell", "ean": ""},  # actually HP
    ]

    for case in test_cases:
        pn, brand, ean = case["pn"], case["brand"], case["ean"]
        print(f"\n  PN={pn}, stated_brand={brand}")

        detected = detect_brand_from_pn(pn)
        if detected:
            print(f"    Detected brand: {detected}")

        predicted = predict_ean(pn, detected["brand"] if detected and detected["brand"] else brand)
        if predicted:
            print(f"    Predicted EAN: {predicted}")

        sources = get_trusted_sources(brand, "datasheet")
        if sources:
            print(f"    Trusted sources: {sources[:3]}")

        flags = check_red_flags(case)
        if flags:
            for f in flags:
                print(f"    RED FLAG: {f}")

    print()
    print("Universal rules library ready. Use functions to pre-filter before AI calls.")

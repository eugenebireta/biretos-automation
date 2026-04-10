"""brand_knowledge.py — YAML-based brand config registry.

Loads per-brand configuration from config/brands/<brand>.yaml files.
Used by enrichment pipeline, research runner, and training export.

Public API:
  load_brand_config(brand) -> dict | None
  get_product_family(brand, pn) -> str | None
  get_trusted_domains(brand, pn=None) -> list[str]
  get_datasheet_query(brand, pn) -> str
  get_search_hints(brand) -> dict
  list_known_brands() -> list[str]
"""
from __future__ import annotations

import re
import sys
import os
from pathlib import Path
from typing import Optional

# Allow import from scripts/ when run directly
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

_ROOT = Path(_scripts_dir).parent
_BRANDS_DIR = _ROOT / "config" / "brands"

# In-memory cache keyed by normalised brand name (lower)
_BRAND_CACHE: dict[str, Optional[dict]] = {}


def _normalise_brand_key(brand: str) -> str:
    return brand.strip().lower().replace(" ", "_")


def _load_yaml(path: Path) -> Optional[dict]:
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def load_brand_config(brand: str) -> Optional[dict]:
    """Load brand config from YAML. Returns None if brand not found.

    Lookup order:
    1. Exact filename match: config/brands/{brand_lower}.yaml
    2. Alias match across all YAML files
    """
    if not brand:
        return None

    cache_key = _normalise_brand_key(brand)
    if cache_key in _BRAND_CACHE:
        return _BRAND_CACHE[cache_key]

    if not _BRANDS_DIR.exists():
        _BRAND_CACHE[cache_key] = None
        return None

    # 1. Direct filename match
    candidate = _BRANDS_DIR / f"{cache_key}.yaml"
    if candidate.exists():
        config = _load_yaml(candidate)
        _BRAND_CACHE[cache_key] = config
        return config

    # 2. Alias search
    brand_lower = brand.strip().lower()
    for p in sorted(_BRANDS_DIR.glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        config = _load_yaml(p)
        if config is None:
            continue
        aliases = [a.lower() for a in config.get("aliases", [])]
        if brand_lower in aliases:
            _BRAND_CACHE[cache_key] = config
            return config

    _BRAND_CACHE[cache_key] = None
    return None


def list_known_brands() -> list[str]:
    """Return list of brand names from all non-template YAML files."""
    brands = []
    if not _BRANDS_DIR.exists():
        return brands
    for p in sorted(_BRANDS_DIR.glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        config = _load_yaml(p)
        if config and config.get("brand"):
            brands.append(config["brand"])
    return brands


def get_product_family(brand: str, pn: str) -> Optional[str]:
    """Determine sub-brand / product family for a PN.

    Checks sub_brands list in parent brand config, then tests each sub-brand's
    pn_patterns against the PN. Returns sub-brand name if matched, else parent brand.
    """
    config = load_brand_config(brand)
    if not config:
        return None

    # Check sub-brands first
    for sub in config.get("sub_brands", []):
        sub_config = load_brand_config(sub)
        if not sub_config:
            continue
        for pattern in sub_config.get("pn_patterns", []):
            try:
                if re.match(pattern, str(pn)):
                    return sub_config.get("brand", sub)
            except re.error:
                continue

    return config.get("brand", brand)


def get_trusted_domains(brand: str, pn: Optional[str] = None) -> list[str]:
    """Return trusted domains for brand, optionally augmented by sub-brand domains.

    If pn is provided and matches a sub-brand, sub-brand tier1 domains are
    prepended (higher priority). Deduplicates preserving order.
    """
    config = load_brand_config(brand)
    if not config:
        return []

    main_domains = config.get("trusted_domains", {})
    result = list(main_domains.get("tier1", [])) + list(main_domains.get("tier2", []))

    if pn:
        family = get_product_family(brand, pn)
        if family and family.lower() != brand.lower():
            family_config = load_brand_config(family)
            if family_config:
                fd = family_config.get("trusted_domains", {})
                sub_domains = list(fd.get("tier1", [])) + list(fd.get("tier2", []))
                # Prepend sub-brand tier1 to give them priority
                result = sub_domains + result

    # Deduplicate preserving order
    seen: set = set()
    deduped = []
    for d in result:
        if d not in seen:
            seen.add(d)
            deduped.append(d)
    return deduped


def get_datasheet_query(brand: str, pn: str) -> str:
    """Return optimised datasheet search query for brand+pn."""
    config = load_brand_config(brand)
    template = "{pn} {brand} datasheet filetype:pdf"
    if config:
        template = config.get("datasheet_query_template", template)
    try:
        return template.format(pn=pn, brand=brand)
    except KeyError:
        return f"{pn} {brand} datasheet filetype:pdf"


def get_search_hints(brand: str) -> dict:
    """Return search hints dict for a brand (primary_lang, append_terms, avoid_terms)."""
    config = load_brand_config(brand)
    if config:
        return config.get("search_hints", {})
    return {}


def clear_cache() -> None:
    """Clear in-memory brand config cache (for testing)."""
    _BRAND_CACHE.clear()


if __name__ == "__main__":
    import json

    known = list_known_brands()
    print(f"Known brands: {known}")
    for b in known:
        cfg = load_brand_config(b)
        domains = get_trusted_domains(b)
        print(f"\n{b}:")
        print(f"  Trusted domains: {domains[:4]}")
        print(f"  Search hints: {get_search_hints(b)}")
        print(f"  Datasheet query (test PN): {get_datasheet_query(b, 'TEST001')}")

    # Test sub-brand detection
    fam = get_product_family("Honeywell", "153711")
    print(f"\nget_product_family('Honeywell', '153711') = {fam}")
    fam2 = get_product_family("Honeywell", "1000106")
    print(f"get_product_family('Honeywell', '1000106') = {fam2}")

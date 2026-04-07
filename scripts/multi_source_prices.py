"""multi_source_prices.py — Optional distributor multi-source price validation.

When --multi-source flag is active in the pipeline:
- Searches additional distributor URLs (using Q_DISTRIBUTORS query + trusted domains)
- Cross-validates the primary price against 1-2 additional sources
- Feeds additional_prices list into price_sanity.py Rule 3 (cross-median)

This module is OPTIONAL and OFF by default (extra SerpAPI budget).
It never replaces the primary price — only adds validation metadata.
"""
from __future__ import annotations

import logging
import re
import sys
import os
from typing import Optional
from urllib.parse import urlparse

log = logging.getLogger(__name__)

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def search_distributor_prices(
    pn: str,
    brand: str,
    trusted_domains: list[str],
    serpapi_key: str,
    max_sources: int = 3,
) -> list[dict]:
    """Search SerpAPI for distributor price sources beyond the primary hit.

    Returns list of price dicts (may be empty). Each dict has:
      price_usd, currency, source_url, source_domain, source_tier

    Never raises — all errors return empty list.
    """
    if not serpapi_key or not pn:
        return []

    try:
        import serpapi  # type: ignore
    except ImportError:
        log.debug("serpapi not installed — multi-source skipped")
        return []

    q = f'"{pn}" (distributor OR supplier OR "buy online") -{brand.lower()} -forum -blog'
    results = []

    try:
        client = serpapi.Client(api_key=serpapi_key)
        search = client.search({
            "q": q,
            "engine": "google",
            "num": 10,
            "gl": "us",
        })
        organic = search.get("organic_results", [])
    except Exception as e:
        log.debug(f"multi_source SerpAPI failed: {e}")
        return []

    for item in organic[:max_sources * 2]:
        url = item.get("link", "")
        if not url:
            continue
        domain = urlparse(url).netloc.lstrip("www.")
        # Only process trusted domains to avoid noise
        if not any(d.endswith(domain) or domain.endswith(d.lstrip("www."))
                   for d in trusted_domains):
            continue
        # Quick price regex scan on snippet
        snippet = item.get("snippet", "")
        price_info = _extract_price_from_snippet(snippet, url, domain)
        if price_info:
            results.append(price_info)
        if len(results) >= max_sources:
            break

    return results


def _extract_price_from_snippet(snippet: str, url: str, domain: str) -> Optional[dict]:
    """Quick regex price extraction from SERP snippet. Returns None if not found."""
    # Patterns for USD, EUR, GBP, RUB
    patterns = [
        (r"\$\s*([\d,]+\.?\d*)", "USD"),
        (r"€\s*([\d,]+\.?\d*)", "EUR"),
        (r"£\s*([\d,]+\.?\d*)", "GBP"),
        (r"([\d,]+\.?\d*)\s*₽", "RUB"),
        (r"([\d,]+\.?\d*)\s*руб", "RUB"),
        (r"([\d.]+)\s*EUR", "EUR"),
        (r"([\d.]+)\s*USD", "USD"),
    ]
    for pattern, currency in patterns:
        m = re.search(pattern, snippet, re.IGNORECASE)
        if m:
            try:
                amount = float(m.group(1).replace(",", ""))
                if amount <= 0:
                    continue
                return {
                    "price_usd": amount,  # Note: stored as native currency
                    "currency": currency,
                    "source_url": url,
                    "source_domain": domain,
                    "source_tier": "tier2",
                    "extraction_method": "snippet_regex",
                }
            except ValueError:
                continue
    return None


def run_multi_source_validation(
    bundle: dict,
    pn: str,
    brand: str,
    serpapi_key: str,
    trusted_domains: Optional[list[str]] = None,
) -> dict:
    """Add multi-source validation metadata to an evidence bundle.

    Called ONLY when --multi-source flag is active. Returns updated bundle.
    Wraps all operations in try/except — never crashes the pipeline.
    """
    if bundle.get("price", {}).get("price_status") not in (
        "public_price", "admissible_public_price"
    ):
        return bundle

    try:
        from brand_knowledge import get_trusted_domains as _get_domains
        domains = trusted_domains or _get_domains(brand, pn)
        additional = search_distributor_prices(
            pn=pn, brand=brand, trusted_domains=domains,
            serpapi_key=serpapi_key, max_sources=3,
        )

        if additional:
            bundle["additional_prices"] = additional
            bundle["price_sources_count"] = 1 + len(additional)

            # Cross-validate via price_sanity
            primary_usd = bundle.get("price", {}).get("price_per_unit")
            if primary_usd is not None:
                all_prices = [primary_usd] + [p["price_usd"] for p in additional]
                try:
                    from price_sanity import check_price_sanity
                    sanity = check_price_sanity(
                        price_usd=primary_usd,
                        pn=pn,
                        brand=brand,
                        source_currency=bundle.get("price", {}).get("currency"),
                        unit_basis=bundle.get("price", {}).get("offer_unit_basis"),
                        existing_prices_usd=all_prices,
                    )
                    bundle["price_cross_validation"] = (
                        "divergent" if sanity.status == "WARNING" else "consistent"
                    )
                except Exception as e:
                    log.debug(f"cross_validation sanity check failed: {e}")
        else:
            bundle["price_sources_count"] = 1
            bundle["price_cross_validation"] = "single_source"

    except Exception as e:
        log.debug(f"multi_source_validation failed for {pn}: {e}")

    return bundle


if __name__ == "__main__":
    print("multi_source_prices.py — optional distributor price validation")
    print("Usage: pass --multi-source flag to photo_pipeline.py")
    print("This module is OFF by default (extra SerpAPI budget).")

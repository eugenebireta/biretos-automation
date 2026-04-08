"""yandex_market_search.py — Search Yandex Market for product prices.

OPTIONAL: requires either SerpAPI key or Yandex XML API key.

Three approaches (in priority order):
1. SerpAPI with engine=yandex — uses existing SerpAPI infrastructure
2. Gemini grounding with Russian query — uses Gemini web search
3. Yandex XML API — free quota 1000 requests/day (requires registration)

Usage:
    python scripts/yandex_market_search.py --pn "153711" --brand "Honeywell"
    python scripts/yandex_market_search.py --from-queue [--limit 50]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

log = logging.getLogger(__name__)

_scripts_dir = Path(__file__).parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

_ROOT = Path(__file__).parent.parent
_QUEUE_JSONL = _ROOT / "research_queue" / "research_queue.jsonl"
_CHECKPOINT = _ROOT / "downloads" / "checkpoint.json"


def search_yandex_via_serpapi(
    pn: str,
    brand: str,
    api_key: str = "",
) -> list[dict]:
    """Search Yandex via SerpAPI for product prices.

    Returns list of price candidates.
    """
    api_key = api_key or os.environ.get("SERPAPI_KEY", "") or os.environ.get("SERPAPI_API_KEY", "")
    if not api_key:
        log.warning("yandex_market: no SerpAPI key")
        return []

    try:
        from serpapi import GoogleSearch  # SerpAPI supports Yandex engine
    except ImportError:
        log.warning("yandex_market: serpapi not installed")
        return []

    query = f"{brand} {pn} купить цена"
    try:
        search = GoogleSearch({
            "engine": "yandex",
            "text": query,
            "lang": "ru",
            "api_key": api_key,
        })
        results = search.get_dict()
        organic = results.get("organic_results", [])
        candidates = []
        for r in organic[:5]:
            url = r.get("link", "")
            if not url:
                continue
            candidates.append({
                "url": url,
                "title": r.get("title", ""),
                "snippet": r.get("snippet", ""),
                "source": "yandex_serpapi",
            })
        return candidates
    except Exception as exc:
        log.warning(f"yandex_market serpapi search failed: {exc}")
        return []


def search_yandex_via_gemini(
    pn: str,
    brand: str,
    api_key: str = "",
) -> list[dict]:
    """Search via Gemini with Russian grounding query.

    Returns list of price candidates.
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        log.warning("yandex_market: no Gemini API key")
        return []

    try:
        import google.genai as genai
        client = genai.Client(api_key=api_key)
    except ImportError:
        log.warning("yandex_market: google.genai not installed")
        return []

    query = (
        f"Найди текущую цену на товар {brand} {pn} в российских интернет-магазинах. "
        f"Ищи на market.yandex.ru, ozon.ru, etm.ru, elec.ru, chipdip.ru. "
        f"Верни JSON: {{\"found\": true/false, \"price_rub\": число, \"source_url\": \"...\", \"store\": \"...\"}}"
    )

    try:
        from google.genai.types import Tool, GoogleSearch as GSearch
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=query,
            config={"tools": [Tool(google_search=GSearch())]},
        )
        text = response.text or ""
        # Try to extract JSON from response
        json_match = re.search(r'\{[^}]+\}', text)
        if json_match:
            data = json.loads(json_match.group())
            if data.get("found") and data.get("source_url"):
                return [{
                    "url": data["source_url"],
                    "title": data.get("store", ""),
                    "price_rub": data.get("price_rub"),
                    "source": "gemini_grounding",
                }]
    except Exception as exc:
        log.warning(f"yandex_market gemini search failed: {exc}")

    return []


def search_yandex_market(
    pn: str,
    brand: str,
) -> list[dict]:
    """Search Yandex Market using best available method.

    Tries: SerpAPI → Gemini → returns empty if neither available.
    """
    # Try SerpAPI first
    results = search_yandex_via_serpapi(pn, brand)
    if results:
        return results

    # Fallback to Gemini
    results = search_yandex_via_gemini(pn, brand)
    if results:
        return results

    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Search Yandex Market for product prices")
    parser.add_argument("--pn", help="Product number to search")
    parser.add_argument("--brand", default="Honeywell")
    parser.add_argument("--from-queue", action="store_true", help="Process from research queue")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    if args.pn:
        results = search_yandex_market(args.pn, args.brand)
        print(f"\nResults for {args.brand} {args.pn}:")
        for r in results:
            print(f"  {r['source']}: {r['url'][:80]}")
            if r.get("price_rub"):
                print(f"    Price: {r['price_rub']} RUB")
        if not results:
            print("  No results found (API keys may not be set)")
    elif args.from_queue:
        print("Queue processing not yet implemented")
        print("Set SERPAPI_KEY or GEMINI_API_KEY environment variable first")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

"""gemini_pilot.py — Pilot run: DDG search + Gemini extraction for DRAFT SKUs.

Exercises the full Gemini pipeline on a sample of DRAFT_ONLY SKUs:
1. DDG search for candidate URLs
2. Fetch + extract page text
3. Gemini price extraction (structured output)
4. Gemini vision verdict (if image exists)
5. Report results (no checkpoint modification)

Usage:
    python scripts/gemini_pilot.py [--limit 30] [--seed 42] [--apply]
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import sys
import time
from pathlib import Path

import requests
import trafilatura

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
PHOTOS_DIR = DOWNLOADS / "photos"
CHECKPOINT_FILE = DOWNLOADS / "checkpoint.json"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
}

SKIP_PAGE_DOMAINS = {"avito.ru", "youla.ru", "drom.ru", "irr.ru"}


def _confirm_pn_exact(pn: str, text: str) -> bool:
    """Lightweight PN word boundary check."""
    escaped = re.escape(pn)
    return bool(re.search(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", text, re.IGNORECASE))


def get_draft_skus(checkpoint_path: Path = CHECKPOINT_FILE) -> list[dict]:
    """Get DRAFT_ONLY SKUs from checkpoint."""
    cp = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    drafts = []
    for pn, bundle in cp.items():
        pdv2 = bundle.get("policy_decision_v2", {})
        card_status = pdv2.get("card_status", "")
        if card_status != "DRAFT_ONLY":
            continue
        drafts.append({
            "pn": pn,
            "name": bundle.get("name", pn),
            "brand": bundle.get("brand", "Honeywell"),
            "category": bundle.get("category", ""),
            "bundle": bundle,
        })
    return drafts


def pilot_single_sku(item: dict) -> dict:
    """Run pilot for a single SKU through DDG+Gemini pipeline.

    Returns result dict with search, extraction, and vision outcomes.
    """
    from gemini_provider import (
        search_ddg,
        extract_price_gemini,
        vision_verdict_gemini,
        get_rate_limiter,
    )

    pn = item["pn"]
    brand = item["brand"]
    name = item["name"]
    category = item["category"]

    result = {
        "pn": pn,
        "name": name,
        "search_candidates": 0,
        "pages_fetched": 0,
        "pn_confirmed_on_page": False,
        "extraction_result": None,
        "vision_result": None,
        "price_found": False,
        "price_usd": None,
        "currency": None,
        "price_status": "no_price_found",
    }

    # Step 1: DDG search
    queries = [
        f'{pn} {brand} price distributor',
        f'{pn} {brand} buy',
    ]

    all_candidates = []
    for q in queries:
        candidates = search_ddg(q, max_results=5)
        all_candidates.extend(candidates)
        time.sleep(0.5)  # polite delay between DDG queries

    # Deduplicate by URL
    seen_urls = set()
    unique_candidates = []
    for c in all_candidates:
        url = c["url"]
        if url in seen_urls or any(d in url for d in SKIP_PAGE_DOMAINS):
            continue
        seen_urls.add(url)
        unique_candidates.append(c)

    result["search_candidates"] = len(unique_candidates)
    log.info(f"  {pn}: {len(unique_candidates)} unique candidates from DDG")

    if not unique_candidates:
        return result

    # Step 2: Fetch + extract from top candidates
    best_extraction = None
    best_confidence = 0

    for cand in unique_candidates[:4]:  # max 4 pages
        url = cand["url"]
        try:
            resp = requests.get(url, headers=BROWSER_HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
            result["pages_fetched"] += 1

            # Extract text
            clean_text = trafilatura.extract(resp.text) or ""
            if len(clean_text) < 100:
                continue

            # PN word boundary check
            if not _confirm_pn_exact(pn, clean_text):
                continue
            result["pn_confirmed_on_page"] = True

            # Gemini extraction
            parsed = extract_price_gemini(
                page_text=clean_text,
                pn=pn,
                brand=brand,
                expected_category=category,
            )
            if not parsed:
                continue

            if not parsed.get("pn_exact_confirmed"):
                continue

            confidence = int(parsed.get("price_confidence", 0))
            if confidence > best_confidence:
                best_confidence = confidence
                best_extraction = {
                    **parsed,
                    "source_url": url,
                }

        except Exception as exc:
            log.debug(f"  {pn}: page fetch/extract error for {url[:60]}: {exc}")

    if best_extraction:
        result["extraction_result"] = best_extraction
        result["price_found"] = best_extraction.get("price_status") == "public_price"
        result["price_usd"] = best_extraction.get("price_per_unit")
        result["currency"] = best_extraction.get("currency")
        result["price_status"] = best_extraction.get("price_status", "no_price_found")

    # Step 3: Vision verdict (if image exists)
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        img_path = PHOTOS_DIR / f"{pn}{ext}"
        if img_path.exists():
            vision = vision_verdict_gemini(
                image_path=str(img_path),
                pn=pn,
                name=name,
            )
            result["vision_result"] = vision
            break

    return result


def run_pilot(limit: int = 30, seed: int = 42, apply: bool = False) -> dict:
    """Run pilot on a sample of DRAFT_ONLY SKUs.

    Returns report dict.
    """
    from dotenv import load_dotenv
    load_dotenv(DOWNLOADS / ".env")

    from gemini_provider import get_rate_limiter

    drafts = get_draft_skus()
    log.info(f"Total DRAFT_ONLY SKUs: {len(drafts)}")

    rng = random.Random(seed)
    rng.shuffle(drafts)
    sample = drafts[:limit]
    log.info(f"Pilot sample: {len(sample)} SKUs")

    results = []
    prices_found = 0
    pn_confirmed = 0
    search_hits = 0

    for i, item in enumerate(sample, 1):
        log.info(f"[{i}/{len(sample)}] {item['pn']} ({item['name'][:40]})")
        result = pilot_single_sku(item)
        results.append(result)

        if result["search_candidates"] > 0:
            search_hits += 1
        if result["pn_confirmed_on_page"]:
            pn_confirmed += 1
        if result["price_found"]:
            prices_found += 1
            log.info(
                f"  PRICE: {result['currency']} {result['price_usd']} "
                f"({result['price_status']})"
            )

    rate_stats = get_rate_limiter().get_stats()

    report = {
        "pilot_size": len(sample),
        "search_hits": search_hits,
        "pn_confirmed": pn_confirmed,
        "prices_found": prices_found,
        "price_pct": round(prices_found / len(sample) * 100, 1) if sample else 0,
        "rate_limiter": rate_stats,
        "results": results,
        "price_summary": [
            {
                "pn": r["pn"],
                "price": r["price_usd"],
                "currency": r["currency"],
                "status": r["price_status"],
                "source_url": (r.get("extraction_result") or {}).get("source_url", ""),
            }
            for r in results if r["price_found"]
        ],
    }

    # Save report
    report_path = ROOT / "shadow_log" / "gemini_pilot_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info(f"Report saved to {report_path}")

    return report


def main():
    import argparse
    p = argparse.ArgumentParser(description="Gemini pipeline pilot run")
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--apply", action="store_true", help="Apply results to checkpoint (NOT IMPLEMENTED)")
    args = p.parse_args()

    report = run_pilot(limit=args.limit, seed=args.seed, apply=args.apply)

    print(f"\n=== Gemini Pilot Report ===")
    print(f"  Pilot size:      {report['pilot_size']}")
    print(f"  DDG search hits: {report['search_hits']}")
    print(f"  PN confirmed:    {report['pn_confirmed']}")
    print(f"  Prices found:    {report['prices_found']} ({report['price_pct']}%)")
    print(f"  Gemini RPD used: plain={report['rate_limiter']['daily_plain']}, "
          f"grounded={report['rate_limiter']['daily_grounded']}")

    if report["price_summary"]:
        print(f"\n  Price results:")
        for p_item in report["price_summary"]:
            print(
                f"    {p_item['pn']:20s} {p_item['currency'] or '???':>4s} "
                f"{p_item['price'] or 0:>10.2f}  {p_item['source_url'][:50]}"
            )


if __name__ == "__main__":
    main()

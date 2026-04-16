"""Pipeline v2 Tier Collector — fetch product data from real pages via Playwright.

Uses headless Chromium to bypass 403/anti-bot protection.
For each URL: loads page, extracts text, passes to Haiku for structured extraction.

Usage:
    python scripts/pipeline_v2/tier_collector.py --pn 109411 00020211 --limit 5
    python scripts/pipeline_v2/tier_collector.py --all-test
"""
from __future__ import annotations

import argparse
import json
import sys
import io
import time
from pathlib import Path
from urllib.parse import urlparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
TRUST_CONFIG = json.loads((ROOT / "config" / "seed_source_trust.json").read_text(encoding="utf-8"))
OUTPUT_DIR = ROOT / "downloads" / "staging" / "tier_collector_output"

TEST_PNS = [
    "109411", "EASY", "CM010610", "00020211", "010130.10", "1000106",
    "1011893-RU", "1050000000", "2208WFPT", "CF274A", "CWSS-RB-S8",
    "7508001857", "EVCS-HSB", "36022-RU", "3240197-RU", "2CDG110146R0011",
    "7910180000", "1006186", "1006187", "027913.10", "2SM-3.0-SCU-SCU-1",
    "CAB-010-SC-SM", "36299-RU", "2CDG110177R0011", "36024-RU",
    "1011894-RU", "7508001858",
]

TIER_ORDER = ["manufacturer_proof", "authorized_distributor", "industrial_distributor",
              "marketplace_fallback", "datasheet_source"]

# Known blockers that need special handling even with Playwright
SLOW_DOMAINS = {"mouser.com", "digikey.com", "rs-online.com"}

EXTRACTION_PROMPT = (
    "Extract product data from this page. The product should be: {brand} {pn} ({seed_name}).\n"
    "Return ONLY a JSON object:\n"
    '{{"pn":"{pn}","brand":"{brand}","title":"","price":"","currency":"","photo_url":"",'
    '"specs":{{}},"ean":"","category_path":"","datasheet_url":"","is_correct_product":true}}\n\n'
    "Rules:\n"
    "- If the page shows a DIFFERENT product than {brand} {pn}, set is_correct_product=false\n"
    "- price: the selling price, not pack price. If pack, note pack_qty in specs\n"
    "- photo_url: main product image URL\n"
    "- specs: all technical specifications found (dimensions, weight, material, etc)\n"
    "- ean: EAN/GTIN barcode if visible\n"
    "- category_path: how the product is categorized on this site\n"
    "- datasheet_url: link to PDF datasheet if found\n"
)


def get_tier(domain: str) -> str:
    for tier_name in TIER_ORDER:
        if any(d in domain for d in TRUST_CONFIG.get(tier_name, [])):
            return tier_name
    return "organic"


def collect_urls_for_pn(pn: str) -> list[dict]:
    """Get all fetchable URLs from evidence for this PN, sorted by tier."""
    ef = EV_DIR / f"evidence_{pn}.json"
    if not ef.exists():
        return []

    d = json.loads(ef.read_text(encoding="utf-8"))
    dr = d.get("deep_research") or {}
    brand = d.get("brand", "") or (d.get("structured_identity") or {}).get("confirmed_manufacturer", "")
    subbrand = d.get("subbrand", "")
    real_brand = subbrand or brand
    seed_name = (d.get("content") or {}).get("seed_name", "") or d.get("name", "")

    all_urls = set()
    for t in (d.get("training_urls") or []):
        u = t if isinstance(t, str) else t.get("url", "")
        if u and u.startswith("http"): all_urls.add(u)
    for src in (dr.get("sources") or []):
        if isinstance(src, dict) and src.get("url"):
            all_urls.add(src["url"])
    pc = d.get("price_contract") or {}
    if pc.get("source_url"): all_urls.add(pc["source_url"])
    if pc.get("dr_source_url"): all_urls.add(pc["dr_source_url"])

    # Classify and sort
    results = []
    seen_domains = set()
    for url in all_urls:
        try:
            dom = urlparse(url).netloc.replace("www.", "")
        except Exception:
            continue
        if not dom or len(dom) < 4 or dom in seen_domains:
            continue
        # Skip image/PDF/CDN URLs
        if any(x in url.lower() for x in [".jpg", ".png", ".gif", ".pdf", "scene7.", "cdn.", "static.", "prod-edam"]):
            continue
        # Skip denylist
        if any(dl in dom for dl in TRUST_CONFIG.get("denylist", [])):
            continue

        seen_domains.add(dom)
        tier = get_tier(dom)
        results.append({
            "url": url, "domain": dom, "tier": tier,
            "brand": real_brand, "seed_name": seed_name,
        })

    tier_rank = {t: i for i, t in enumerate(TIER_ORDER)}
    results.sort(key=lambda x: tier_rank.get(x["tier"], 99))
    return results


STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en', 'de']});
window.chrome = {runtime: {}};
"""

# Shared browser instance for batch processing
_browser = None
_page = None


def _get_browser_page():
    """Get or create a persistent browser + page (headed mode for anti-bot bypass)."""
    global _browser, _page
    if _browser is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
        )
        context = _browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="de-DE",
            timezone_id="Europe/Berlin",
            extra_http_headers={
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            },
        )
        _page = context.new_page()
        _page.add_init_script(STEALTH_JS)
    return _page


def close_browser():
    """Close the shared browser."""
    global _browser, _page
    if _browser:
        _browser.close()
        _browser = None
        _page = None


def fetch_page(url: str, timeout_ms: int = 25000) -> str | None:
    """Fetch page content using Playwright in headed mode (bypasses anti-bot)."""
    try:
        page = _get_browser_page()

        page.goto(url, timeout=timeout_ms, wait_until="networkidle")
        time.sleep(6)  # generous wait for SPA render
        page.evaluate("window.scrollTo(0, 500)")
        time.sleep(2)

        text = page.evaluate("document.body.innerText")

        # Check for blocks
        if "Access Denied" in text or "denied" in (page.title() or "").lower():
            return None
        if len(text) < 100:
            return None

        # Truncate to ~4000 chars for Haiku
        if len(text) > 4000:
            text = text[:4000] + "\n...(truncated)"

        return text
    except Exception:
        return None


def extract_with_haiku(page_text: str, pn: str, brand: str, seed_name: str) -> dict | None:
    """Send page text to Haiku for structured extraction."""
    from scripts.app_secrets import get_secret
    import anthropic

    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    prompt = EXTRACTION_PROMPT.format(pn=pn, brand=brand, seed_name=seed_name)

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": f"{prompt}\n\nPage content:\n{page_text}",
            }],
        )
        text = resp.content[0].text.strip()
        if "```" in text:
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else text
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pn", nargs="+", help="Specific PNs to process")
    parser.add_argument("--all-test", action="store_true", help="Process all 27 test SKUs")
    parser.add_argument("--limit", type=int, default=3, help="Max URLs per SKU")
    parser.add_argument("--dry-run", action="store_true", help="Show URLs without fetching")
    args = parser.parse_args()

    pns = args.pn if args.pn else (TEST_PNS if args.all_test else [])
    if not pns:
        print("Usage: --pn PN1 PN2 or --all-test")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Tier Collector: {len(pns)} SKUs, limit={args.limit} URLs/SKU")
    print("=" * 100)

    all_results = {}
    total_fetched = 0
    total_extracted = 0

    for pn in pns:
        urls = collect_urls_for_pn(pn)
        if not urls:
            print(f"  {pn:<25} NO URLs in evidence")
            continue

        brand = urls[0]["brand"]
        seed_name = urls[0]["seed_name"]
        print(f"\n  {pn:<25} ({brand}) — {len(urls)} URLs available")

        pn_results = []

        for url_info in urls[:args.limit]:
            url = url_info["url"]
            dom = url_info["domain"]
            tier = url_info["tier"]

            if args.dry_run:
                print(f"    [{tier[:4]}] {dom:<30} {url[:65]}")
                continue

            print(f"    [{tier[:4]}] {dom:<30} ", end="", flush=True)

            # Fetch with Playwright
            page_text = fetch_page(url)
            if not page_text:
                print("FETCH FAILED")
                continue

            total_fetched += 1
            print(f"fetched ({len(page_text)} chars) ", end="", flush=True)

            # Extract with Haiku
            data = extract_with_haiku(page_text, pn, brand, seed_name)
            if not data:
                print("EXTRACT FAILED")
                continue

            total_extracted += 1
            is_correct = data.get("is_correct_product", False)
            has_price = bool(data.get("price"))
            has_photo = bool(data.get("photo_url"))
            has_specs = bool(data.get("specs"))
            has_ean = bool(data.get("ean"))
            has_ds = bool(data.get("datasheet_url"))

            status = "CORRECT" if is_correct else "WRONG"
            fields = []
            if has_price: fields.append(f"price={data['price']}{data.get('currency','')}")
            if has_photo: fields.append("photo")
            if has_specs: fields.append(f"specs({len(data['specs'])})")
            if has_ean: fields.append(f"EAN={data['ean']}")
            if has_ds: fields.append("datasheet")

            print(f"{status} {' '.join(fields)}")

            data["_source_url"] = url
            data["_source_domain"] = dom
            data["_source_tier"] = tier
            pn_results.append(data)

            time.sleep(0.5)

        all_results[pn] = pn_results

    if not args.dry_run:
        # Save results
        out_file = OUTPUT_DIR / "tier_collector_results.json"
        out_file.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")

        print()
        print("=" * 100)
        print(f"Fetched: {total_fetched}, Extracted: {total_extracted}")
        print(f"Output: {out_file}")

        # Summary
        correct = sum(1 for pn_res in all_results.values()
                      for r in pn_res if r.get("is_correct_product"))
        wrong = sum(1 for pn_res in all_results.values()
                    for r in pn_res if not r.get("is_correct_product"))
        with_price = sum(1 for pn_res in all_results.values()
                         for r in pn_res if r.get("price") and r.get("is_correct_product"))
        with_ean = sum(1 for pn_res in all_results.values()
                       for r in pn_res if r.get("ean") and r.get("is_correct_product"))

        print(f"Correct product: {correct}, Wrong product: {wrong}")
        print(f"With price: {with_price}, With EAN: {with_ean}")


if __name__ == "__main__":
    try:
        main()
    finally:
        close_browser()

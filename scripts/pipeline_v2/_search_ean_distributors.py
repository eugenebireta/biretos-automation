"""Search for EAN on distributor sites (mouser, RS, digikey, farnell, conrad).

Distributors always show barcode/EAN on product pages.
This is FALLBACK — datasheet is primary source for EAN.

Uses SerpAPI with query: "{brand} {pn}" EAN site:mouser.com OR site:rs-online.com OR ...
Then fetches top result and extracts EAN via Gemini.
"""
from __future__ import annotations

import json
import sys
import time
import re
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import requests as http_requests

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
RESULTS_DS = ROOT / "downloads" / "staging" / "tier_collector_output" / "datasheet_extracted.json"
RESULTS_FOCUSED = ROOT / "downloads" / "staging" / "tier_collector_output" / "ean_focused_extraction.json"
OUT_FILE = ROOT / "downloads" / "staging" / "tier_collector_output" / "ean_from_distributors.json"

DISTRIBUTOR_SITES = "site:mouser.com OR site:rs-online.com OR site:digikey.com OR site:farnell.com OR site:conrad.de OR site:tme.eu"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}


def get_skus_needing_ean() -> list:
    """Find SKUs without valid EAN from datasheet parsing."""
    ds_data = json.loads(RESULTS_DS.read_text(encoding="utf-8"))
    focused = json.loads(RESULTS_FOCUSED.read_text(encoding="utf-8")) if RESULTS_FOCUSED.exists() else {}
    existing = json.loads(OUT_FILE.read_text(encoding="utf-8")) if OUT_FILE.exists() else {}

    have_ean = set()
    for d in [ds_data, focused, existing]:
        for pn, info in d.items():
            ean = info.get("ean", "")
            if ean and str(ean).isdigit() and len(str(ean)) == 13:
                have_ean.add(pn)

    targets = []
    for f in sorted(EV_DIR.glob("evidence_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        if not pn or pn.strip("-_") == "" or pn in {"---", "--", "_", "PN", "-----"}:
            continue
        pn_safe = pn.replace("/", "_").replace(" ", "_")
        if pn_safe in have_ean or pn in have_ean:
            continue
        if pn_safe in existing:
            continue

        brand = d.get("brand", "") or (d.get("structured_identity") or {}).get("confirmed_manufacturer", "")
        subbrand = d.get("subbrand", "")
        real_brand = subbrand or brand
        targets.append((pn, pn_safe, real_brand))

    return targets


def search_distributor(pn: str, brand: str, serpapi_key: str) -> list:
    """Search Google for PN on distributor sites, return snippets with EAN candidates."""
    query = f'"{pn}" EAN {brand} ({DISTRIBUTOR_SITES})'
    try:
        resp = http_requests.get(
            "https://serpapi.com/search",
            params={"q": query, "engine": "google", "api_key": serpapi_key, "num": 5, "gl": "de", "hl": "en"},
            timeout=25,
        )
        results = resp.json().get("organic_results", [])
        return results
    except Exception:
        return []


def extract_ean_from_snippet(snippet: str) -> str:
    """Extract 13-digit EAN from text."""
    if not snippet:
        return ""
    # Look for 13-digit number, optionally with EAN/GTIN label
    patterns = [
        r'(?:EAN|GTIN|barcode)[:\s]*(\d{13})',
        r'\b(\d{13})\b',
    ]
    for pat in patterns:
        m = re.search(pat, snippet, re.IGNORECASE)
        if m:
            ean = m.group(1)
            # Validate: not all same digit, not obviously fake
            if len(set(ean)) > 2:
                return ean
    return ""


def fetch_page_ean(url: str, pn: str) -> str:
    """Fetch distributor page and extract EAN."""
    try:
        r = http_requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return ""
        text = r.text
        # Look for EAN patterns in HTML
        patterns = [
            rf'{re.escape(pn)}.{{0,500}}?EAN[:\s]*(\d{{13}})',
            rf'EAN[:\s]*(\d{{13}}).{{0,200}}?{re.escape(pn)}',
            r'GTIN[^0-9]{0,50}(\d{13})',
            r'barcode[^0-9]{0,50}(\d{13})',
            r'"ean"\s*:\s*"(\d{13})"',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if m:
                ean = m.group(1)
                if len(set(ean)) > 2:
                    return ean
    except Exception:
        pass
    return ""


def main():
    from scripts.app_secrets import get_secret
    serpapi_key = get_secret("SERPAPI_KEY")

    targets = get_skus_needing_ean()
    existing = json.loads(OUT_FILE.read_text(encoding="utf-8")) if OUT_FILE.exists() else {}

    print(f"EAN search on distributors: {len(targets)} SKUs")
    print("=" * 80)

    found = 0
    no_result = 0
    serp_used = 0

    for idx, (pn, pn_safe, brand) in enumerate(targets):
        print(f"  [{idx+1}/{len(targets)}] {pn:<22} ({brand})... ", end="", flush=True)

        # SerpAPI search
        results = search_distributor(pn, brand, serpapi_key)
        serp_used += 1

        if not results:
            no_result += 1
            existing[pn_safe] = {"ean": "", "source": "no_search_results"}
            print("no results")
            time.sleep(5)
            continue

        # Try to find EAN in snippets first (fast)
        ean = ""
        source_url = ""
        for r in results[:5]:
            snippet = r.get("snippet", "") + " " + r.get("title", "")
            ean_candidate = extract_ean_from_snippet(snippet)
            if ean_candidate:
                ean = ean_candidate
                source_url = r.get("link", "")
                break

        # If not in snippets, fetch top page and search
        if not ean:
            for r in results[:3]:
                url = r.get("link", "")
                dom = urlparse(url).netloc.replace("www.", "")
                if not any(d in dom for d in ["mouser", "rs-online", "digikey", "farnell", "conrad", "tme"]):
                    continue
                ean_candidate = fetch_page_ean(url, pn)
                if ean_candidate:
                    ean = ean_candidate
                    source_url = url
                    break
                time.sleep(2)

        if ean:
            existing[pn_safe] = {
                "ean": ean,
                "source": "distributor",
                "source_url": source_url,
                "domain": urlparse(source_url).netloc.replace("www.", "") if source_url else "",
            }
            found += 1
            domain = urlparse(source_url).netloc.replace("www.", "") if source_url else ""
            print(f"EAN={ean} from {domain}")
        else:
            existing[pn_safe] = {"ean": "", "source": "not_found"}
            print("no EAN")

        # Save every 5
        if (idx + 1) % 5 == 0:
            OUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

        time.sleep(6)  # pause between searches

    OUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nResults:")
    print(f"  EAN found:     {found}")
    print(f"  No results:    {no_result}")
    print(f"  SerpAPI calls: {serp_used}")
    print(f"  Output: {OUT_FILE}")


if __name__ == "__main__":
    main()

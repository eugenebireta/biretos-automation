"""Tier cascade test: search each tier top-down for 27 test SKUs.

For each SKU, try TIER1 first, then TIER2, then TIER3...
On each tier, try to collect ALL fields (identity, price, photo, specs, EAN).
Stop descending for a field when it's found.
"""
from __future__ import annotations

import json
import sys
import io
import time
from pathlib import Path
from urllib.parse import urlparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.app_secrets import get_secret
import requests

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
TRUST_CONFIG = json.loads((ROOT / "config" / "seed_source_trust.json").read_text(encoding="utf-8"))
SERPAPI_KEY = get_secret("SERPAPI_KEY")

TEST_PNS = [
    "109411", "EASY", "CM010610",
    "00020211", "010130.10", "1000106", "1011893-RU",
    "1050000000", "2208WFPT", "CF274A", "CWSS-RB-S8",
    "7508001857", "D-71570", "EVCS-HSB", "36022-RU",
    "3240197-RU", "2CDG110146R0011", "7910180000",
    "1006186", "1006187", "027913.10", "2SM-3.0-SCU-SCU-1",
    "CAB-010-SC-SM", "36299-RU", "2CDG110177R0011",
    "36024-RU", "1011894-RU",
]

# Manufacturer domains per brand
BRAND_MANUFACTURER_SITES = {
    "Honeywell": ["honeywell.com", "buildings.honeywell.com"],
    "PEHA": ["peha.de", "pehastore.de"],
    "Esser": ["esser-systems.com", "security.honeywell.de"],
    "DKC": ["dkc.ru", "dkc.com"],
    "Dell": ["dell.com"],
    "HP": ["hp.com"],
    "ABB": ["abb.com", "new.abb.com"],
    "Weidmuller": ["weidmueller.com", "weidmuller.com"],
    "Howard Leight": ["honeywellsafety.com", "sps.honeywell.com"],
    "Sperian": ["honeywellsafety.com", "sperian-protection.com"],
    "System Sensor": ["systemsensor.com"],
    "Notifier": ["notifier.com"],
    "Phoenix Contact": ["phoenixcontact.com"],
    "Optcom": ["optcom.ru"],
    "Hyperline": ["hyperline.ru"],
    "Murrelektronik": ["murrelektronik.com"],
    "NEC": ["nec.com"],
}

TIER2_SITES = "site:mouser.com OR site:rs-online.com OR site:digikey.com OR site:farnell.com OR site:conrad.de"
TIER3_SITES = "site:tme.eu OR site:automation24.com OR site:radwell.com OR site:bolasystems.com"


def serp_search(query: str, num: int = 5) -> list[dict]:
    """Run SerpAPI search, return organic results."""
    try:
        resp = requests.get("https://serpapi.com/search", params={
            "q": query, "engine": "google", "api_key": SERPAPI_KEY,
            "num": num, "gl": "de", "hl": "en",
        }, timeout=30)
        return resp.json().get("organic_results", [])
    except Exception as e:
        print(f"      SERP ERROR: {e}")
        return []


def extract_signals(results: list[dict], pn: str) -> dict:
    """Extract what data signals are available from search results."""
    signals = {
        "found": len(results) > 0,
        "urls": [],
        "has_product_page": False,
        "has_price_signal": False,
        "has_photo_signal": False,
        "has_specs_signal": False,
        "has_datasheet": False,
        "has_ean": False,
    }

    for r in results[:5]:
        url = r.get("link", "")
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        domain = urlparse(url).netloc.replace("www.", "") if url else ""

        signals["urls"].append({"url": url, "domain": domain, "title": title[:80]})

        title_lower = (title + " " + snippet).lower()
        pn_lower = pn.lower().replace("-", "").replace(".", "")

        # Check if PN is in title/snippet (product page signal)
        if pn_lower in title_lower.replace("-", "").replace(".", ""):
            signals["has_product_page"] = True

        # Price signals
        if any(c in title_lower for c in ["$", "eur", "gbp", "usd", "price", "buy", "order", "shop"]):
            signals["has_price_signal"] = True
        if any(c in snippet.lower() for c in ["$", "eur", "gbp", "price", "buy"]):
            signals["has_price_signal"] = True

        # Photo signals (thumbnails in results)
        if r.get("thumbnail"):
            signals["has_photo_signal"] = True

        # Specs/datasheet signals
        if any(w in title_lower for w in ["datasheet", "pdf", "specification", "technical"]):
            signals["has_datasheet"] = True
            signals["has_specs_signal"] = True
        if any(w in title_lower for w in ["specs", "dimensions", "weight", "rating"]):
            signals["has_specs_signal"] = True

        # EAN signals
        if any(w in title_lower for w in ["ean", "gtin", "barcode", "upc"]):
            signals["has_ean"] = True

    return signals


def main():
    print("=" * 110)
    print("TIER CASCADE: Top-down search for 27 test SKUs")
    print("=" * 110)
    print()

    results_all = {}
    serp_count = 0

    for pn in TEST_PNS:
        ef = EV_DIR / f"evidence_{pn}.json"
        if not ef.exists():
            continue
        d = json.loads(ef.read_text(encoding="utf-8"))
        si = d.get("structured_identity") or {}
        brand = d.get("brand", "") or si.get("confirmed_manufacturer", "")
        subbrand = d.get("subbrand", "")
        real_brand = subbrand or brand
        (d.get("content") or {}).get("seed_name", "") or d.get("name", "")

        print(f"  {pn:<25} ({real_brand})")

        sku_result = {
            "pn": pn, "brand": real_brand,
            "tier1": {"searched": False, "found": False},
            "tier2": {"searched": False, "found": False},
            "tier3": {"searched": False, "found": False},
            "fields_found": {
                "identity": None, "price": None, "photo": None,
                "specs": None, "datasheet": None, "ean": None,
            },
        }

        # === TIER 1: Manufacturer site ===
        mfg_sites = BRAND_MANUFACTURER_SITES.get(real_brand, [])
        if not mfg_sites and brand != real_brand:
            mfg_sites = BRAND_MANUFACTURER_SITES.get(brand, [])

        if mfg_sites:
            site_query = " OR ".join(f"site:{s}" for s in mfg_sites[:2])
            query = f"{pn} ({site_query})"
            results = serp_search(query, num=3)
            serp_count += 1
            signals = extract_signals(results, pn)

            sku_result["tier1"]["searched"] = True
            sku_result["tier1"]["found"] = signals["found"]
            sku_result["tier1"]["signals"] = signals

            if signals["has_product_page"]:
                sku_result["fields_found"]["identity"] = "TIER1"
            if signals["has_price_signal"]:
                sku_result["fields_found"]["price"] = "TIER1"
            if signals["has_photo_signal"]:
                sku_result["fields_found"]["photo"] = "TIER1"
            if signals["has_specs_signal"]:
                sku_result["fields_found"]["specs"] = "TIER1"
            if signals["has_datasheet"]:
                sku_result["fields_found"]["datasheet"] = "TIER1"
            if signals["has_ean"]:
                sku_result["fields_found"]["ean"] = "TIER1"

            found_fields = [k for k, v in sku_result["fields_found"].items() if v]
            print(f"    TIER1: {len(results)} results -> {found_fields or 'nothing'}")
            time.sleep(1.5)
        else:
            print(f"    TIER1: no manufacturer site for {real_brand}")

        # === TIER 2: Authorized distributors (only for missing fields) ===
        missing = [k for k, v in sku_result["fields_found"].items() if not v]
        if missing:
            query = f"{real_brand} {pn} ({TIER2_SITES})"
            results = serp_search(query, num=5)
            serp_count += 1
            signals = extract_signals(results, pn)

            sku_result["tier2"]["searched"] = True
            sku_result["tier2"]["found"] = signals["found"]
            sku_result["tier2"]["signals"] = signals

            if not sku_result["fields_found"]["identity"] and signals["has_product_page"]:
                sku_result["fields_found"]["identity"] = "TIER2"
            if not sku_result["fields_found"]["price"] and signals["has_price_signal"]:
                sku_result["fields_found"]["price"] = "TIER2"
            if not sku_result["fields_found"]["photo"] and signals["has_photo_signal"]:
                sku_result["fields_found"]["photo"] = "TIER2"
            if not sku_result["fields_found"]["specs"] and signals["has_specs_signal"]:
                sku_result["fields_found"]["specs"] = "TIER2"
            if not sku_result["fields_found"]["datasheet"] and signals["has_datasheet"]:
                sku_result["fields_found"]["datasheet"] = "TIER2"
            if not sku_result["fields_found"]["ean"] and signals["has_ean"]:
                sku_result["fields_found"]["ean"] = "TIER2"

            new_found = [k for k, v in sku_result["fields_found"].items() if v and v == "TIER2"]
            print(f"    TIER2: {len(results)} results -> +{new_found or 'nothing new'}")
            time.sleep(1.5)

        # === TIER 3: Industrial distributors (only for still-missing) ===
        missing = [k for k, v in sku_result["fields_found"].items() if not v]
        if missing and len(missing) > 2:  # don't bother for 1-2 missing fields
            query = f"{real_brand} {pn} ({TIER3_SITES})"
            results = serp_search(query, num=3)
            serp_count += 1
            signals = extract_signals(results, pn)

            sku_result["tier3"]["searched"] = True
            sku_result["tier3"]["found"] = signals["found"]

            if not sku_result["fields_found"]["identity"] and signals["has_product_page"]:
                sku_result["fields_found"]["identity"] = "TIER3"
            if not sku_result["fields_found"]["price"] and signals["has_price_signal"]:
                sku_result["fields_found"]["price"] = "TIER3"
            if not sku_result["fields_found"]["photo"] and signals["has_photo_signal"]:
                sku_result["fields_found"]["photo"] = "TIER3"

            new_found = [k for k, v in sku_result["fields_found"].items() if v and v == "TIER3"]
            print(f"    TIER3: {len(results)} results -> +{new_found or 'nothing new'}")
            time.sleep(1.5)

        # Summary for this SKU
        found = {k: v for k, v in sku_result["fields_found"].items() if v}
        missing = [k for k, v in sku_result["fields_found"].items() if not v]
        print(f"    RESULT: found={list(found.keys())}  missing={missing}")
        print()

        results_all[pn] = sku_result

    # === SUMMARY ===
    print("=" * 110)
    print(f"TIER CASCADE SUMMARY ({len(results_all)} SKUs, {serp_count} SerpAPI calls)")
    print("=" * 110)
    print()

    # Field coverage by tier
    field_tier_count = {}
    for field in ["identity", "price", "photo", "specs", "datasheet", "ean"]:
        tier_counts = {"TIER1": 0, "TIER2": 0, "TIER3": 0, "not_found": 0}
        for pn, res in results_all.items():
            v = res["fields_found"].get(field)
            if v:
                tier_counts[v] += 1
            else:
                tier_counts["not_found"] += 1
        field_tier_count[field] = tier_counts

    print(f"{'Field':<15} {'TIER1':>8} {'TIER2':>8} {'TIER3':>8} {'Missing':>8} {'Total':>8}")
    print("-" * 60)
    n = len(results_all)
    for field, counts in field_tier_count.items():
        total_found = counts["TIER1"] + counts["TIER2"] + counts["TIER3"]
        print(f"{field:<15} {counts['TIER1']:>8} {counts['TIER2']:>8} {counts['TIER3']:>8} "
              f"{counts['not_found']:>8} {total_found:>5}/{n}")

    # Save
    out = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "tier_cascade_results.json"
    out.write_text(json.dumps(results_all, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()

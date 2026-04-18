"""Extended EAN search via Gemini grounding (Google Search) for SKUs without EAN.

Uses Gemini with google_search tool to find barcodes/EAN/GTIN.
Validates EAN-13 checksum.
Smart query patterns based on brand.
"""
from __future__ import annotations

import json
import sys
import time
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
OUT_FILE = ROOT / "downloads" / "staging" / "tier_collector_output" / "ean_extended_search.json"


def validate_ean13(ean: str) -> bool:
    """Validate EAN-13 checksum."""
    if not ean or not ean.isdigit() or len(ean) != 13:
        return False
    digits = [int(d) for d in ean]
    checksum = sum(digits[i] * (3 if i % 2 else 1) for i in range(12))
    check_digit = (10 - (checksum % 10)) % 10
    return check_digit == digits[12]


def get_existing_eans():
    """Load all known EANs from previous extractions."""
    eans = {}
    for f in [
        ROOT / "downloads/staging/tier_collector_output/datasheet_extracted.json",
        ROOT / "downloads/staging/tier_collector_output/ean_focused_extraction.json",
        ROOT / "downloads/staging/tier_collector_output/ean_from_distributors.json",
    ]:
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            for pn, d in data.items():
                ean = str(d.get("ean", ""))
                if validate_ean13(ean):
                    eans[pn] = ean
    return eans


def main():
    from google import genai as genai_new
    from google.genai import types
    from scripts.app_secrets import get_secret

    client = genai_new.Client(api_key=get_secret("GEMINI_API_KEY"))
    search_config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.0,
    )

    existing_eans = get_existing_eans()
    existing_extended = json.loads(OUT_FILE.read_text(encoding="utf-8")) if OUT_FILE.exists() else {}

    targets = []
    for f in sorted(EV_DIR.glob("evidence_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        if not pn or pn.strip("-_") == "" or pn in {"---", "--", "_", "PN", "-----"}:
            continue
        pn_safe = pn.replace("/", "_").replace(" ", "_")
        if pn_safe in existing_eans or pn in existing_eans:
            continue
        if pn_safe in existing_extended:
            continue
        brand = d.get("brand", "") or (d.get("structured_identity") or {}).get("confirmed_manufacturer", "")
        subbrand = d.get("subbrand", "")
        real_brand = subbrand or brand
        seed = (d.get("content") or {}).get("seed_name", "") or d.get("name", "")
        targets.append((pn, pn_safe, real_brand, seed))

    print(f"Extended EAN search: {len(targets)} SKUs")
    print("=" * 80)

    found = 0
    no_result = 0

    for idx, (pn, pn_safe, brand, seed) in enumerate(targets):
        print(f"  [{idx+1}/{len(targets)}] {pn:<22} ({brand})... ", end="", flush=True)

        prompt = (
            f"Search Google for the EAN-13 barcode (also called GTIN or Article number EAN) for this product:\n"
            f"  Brand: {brand}\n"
            f"  Part Number: {pn}\n"
            f"  Description: {seed}\n\n"
            f"Look at distributor sites (Mouser, RS Components, Digikey, Conrad, TME, Farnell), manufacturer pages, and product databases.\n"
            f"Return ONLY the 13-digit EAN code, nothing else.\n"
            f"If multiple EAN found, return the one that matches the exact part number.\n"
            f"If not found, return: NOT_FOUND"
        )

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=search_config,
            )
            text = response.text.strip() if response.text else ""

            # Find 13-digit number
            ean_match = re.search(r'\b(\d{13})\b', text)
            if ean_match:
                ean = ean_match.group(1)
                # Validate checksum
                if validate_ean13(ean):
                    existing_extended[pn_safe] = {"ean": ean, "source": "gemini_grounding", "valid": True}
                    found += 1
                    print(f"EAN={ean} (valid)")
                else:
                    existing_extended[pn_safe] = {"ean": ean, "source": "gemini_grounding", "valid": False}
                    print(f"EAN={ean} (INVALID checksum)")
            else:
                existing_extended[pn_safe] = {"ean": "", "source": "gemini_grounding"}
                no_result += 1
                print("not found")

        except Exception as e:
            existing_extended[pn_safe] = {"ean": "", "error": str(e)[:100]}
            err_str = str(e)
            if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
                print("RATE LIMIT — sleeping 60s")
                time.sleep(60)
            else:
                print(f"ERROR: {err_str[:60]}")

        if (idx + 1) % 10 == 0:
            OUT_FILE.write_text(json.dumps(existing_extended, indent=2, ensure_ascii=False), encoding="utf-8")

        time.sleep(8)  # generous pause for grounding

    OUT_FILE.write_text(json.dumps(existing_extended, indent=2, ensure_ascii=False), encoding="utf-8")

    valid_eans = sum(1 for v in existing_extended.values() if v.get("valid"))
    print("\nResults:")
    print(f"  Found valid EANs: {valid_eans}")
    print(f"  Not found: {no_result}")
    print(f"  Output: {OUT_FILE}")


if __name__ == "__main__":
    main()

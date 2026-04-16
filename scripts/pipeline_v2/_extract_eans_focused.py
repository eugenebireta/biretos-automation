"""Focused EAN extraction from downloaded datasheets.

Problem: Gemini parsed 290 PDFs but only found EAN for 19.
Hypothesis: generic "extract all" prompt misses EAN in dense tables/back pages.
Solution: dedicated EAN-only prompt + force check last pages.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
DS_DIR = ROOT / "downloads" / "datasheets_v2"
EV_DIR = ROOT / "downloads" / "evidence"
RESULTS = ROOT / "downloads" / "staging" / "tier_collector_output" / "datasheet_extracted.json"
OUT_FILE = ROOT / "downloads" / "staging" / "tier_collector_output" / "ean_focused_extraction.json"

PROMPT = """This is a product datasheet PDF. Your ONLY task is to find the EAN code (also called GTIN, barcode, or EAN-code).

EAN codes are 13-digit numbers, often found:
- On the last page of datasheet
- In "Material No." or "Article Number" tables
- Next to pack quantities
- Near manufacturer address
- With prefix "EAN:", "GTIN:", "Barcode:"

CHECK EVERY PAGE carefully, especially the last pages.

Product: {brand} {pn} ({seed})

Return ONLY a JSON object:
{{"ean": "<13-digit EAN or empty string>", "article_no": "<article number or empty>", "page_found": <page number or 0>}}

If no EAN found on any page, return empty string. Do NOT hallucinate numbers."""


def main():
    from google import genai as genai_new
    from google.genai import types
    from scripts.app_secrets import get_secret

    client = genai_new.Client(api_key=get_secret("GEMINI_API_KEY"))

    # Load existing results
    parsed = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    existing_ean = json.loads(OUT_FILE.read_text(encoding="utf-8")) if OUT_FILE.exists() else {}

    # Find SKUs with PDF but no EAN
    targets = []
    for f in sorted(EV_DIR.glob("evidence_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        if not pn or pn.strip("-_") == "" or pn in {"---","--","_","PN","-----"}:
            continue
        pn_safe = pn.replace("/", "_").replace(" ", "_")
        pdf_path = DS_DIR / f"{pn_safe}.pdf"
        if not pdf_path.exists():
            continue
        # Skip if already processed in this script
        if pn_safe in existing_ean:
            continue
        # Skip if Gemini already found EAN
        ds_data = parsed.get(pn_safe) or parsed.get(pn, {})
        existing_ean_val = ds_data.get("ean", "")
        if existing_ean_val and str(existing_ean_val) not in ("-","","None","Not provided","Not specified"):
            continue
        # Skip very large files
        if pdf_path.stat().st_size > 20 * 1024 * 1024:
            continue

        brand = d.get("brand", "") or (d.get("structured_identity") or {}).get("confirmed_manufacturer", "")
        seed = (d.get("content") or {}).get("seed_name", "") or d.get("name", "")
        targets.append((pn, pn_safe, brand, seed, pdf_path))

    print(f"Focused EAN extraction: {len(targets)} PDFs")
    print("=" * 80)

    found_count = 0
    for idx, (pn, pn_safe, brand, seed, pdf_path) in enumerate(targets):
        size_kb = pdf_path.stat().st_size // 1024
        print(f"  [{idx+1}/{len(targets)}] {pn:<22} ({size_kb} KB)... ", end="", flush=True)

        try:
            # Upload file
            uploaded = client.files.upload(file=str(pdf_path))

            prompt = PROMPT.format(brand=brand, pn=pn, seed=seed)

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[uploaded, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=500,
                ),
            )
            text = response.text.strip() if response.text else ""

            # Parse JSON
            if "```" in text:
                parts = text.split("```")
                text = parts[1] if len(parts) > 1 else text
                if text.startswith("json"): text = text[4:]

            # Try to parse or regex-extract EAN
            data = None
            try:
                data = json.loads(text.strip())
            except Exception:
                # Regex fallback
                import re
                ean_match = re.search(r'"ean"\s*:\s*"(\d{13})"', text)
                article_match = re.search(r'"article_no"\s*:\s*"([^"]*)"', text)
                page_match = re.search(r'"page_found"\s*:\s*(\d+)', text)
                # Or any 13-digit number in text
                if not ean_match:
                    # Look for raw 13-digit number
                    digits_match = re.search(r'\b(\d{13})\b', text)
                    if digits_match:
                        ean_match = digits_match
                data = {
                    "ean": ean_match.group(1) if ean_match else "",
                    "article_no": article_match.group(1) if article_match else "",
                    "page_found": int(page_match.group(1)) if page_match else 0,
                    "_salvaged": True,
                }

            if data:
                ean = str(data.get("ean", "")).strip()
                # Validate EAN is 13 digits
                if ean and ean.isdigit() and len(ean) == 13:
                    existing_ean[pn_safe] = data
                    found_count += 1
                    print(f"EAN={ean}  (page {data.get('page_found','?')})")
                elif ean:
                    # Partial/invalid, still save
                    existing_ean[pn_safe] = data
                    print(f"invalid EAN ({ean})")
                else:
                    existing_ean[pn_safe] = {"ean": "", "page_found": 0}
                    print("no EAN")

            # Save after each successful extraction
            if (idx + 1) % 5 == 0:
                OUT_FILE.write_text(json.dumps(existing_ean, indent=2, ensure_ascii=False), encoding="utf-8")

        except Exception as e:
            print(f"ERROR: {str(e)[:60]}")
            existing_ean[pn_safe] = {"error": str(e)[:200]}

        time.sleep(6)  # 6 sec between Gemini calls

    OUT_FILE.write_text(json.dumps(existing_ean, indent=2, ensure_ascii=False), encoding="utf-8")

    valid_eans = sum(1 for v in existing_ean.values()
                     if v.get("ean", "").isdigit() and len(v.get("ean", "")) == 13)
    print(f"\nFound valid EANs: {valid_eans}/{len(existing_ean)}")
    print(f"Output: {OUT_FILE}")


if __name__ == "__main__":
    main()

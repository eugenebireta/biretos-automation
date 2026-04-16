"""Parse large PDFs that were skipped (>5MB).

Strategy: extract first 10 pages as separate PDF, feed to Gemini.
Most product data is in first pages, catalogs have data blocks per product.
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
OUT_DIR = ROOT / "downloads" / "staging" / "datasheets_truncated"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROMPT = """This is a product datasheet PDF (first 10 pages of a larger document).

Product: {brand} {pn} ({seed})

Find data specifically for this product PN. Return ONLY JSON:
{{"pn":"","article_no":"","brand":"","title":"","description":"",
"specs":{{}},"ean":"","dimensions_mm":"","weight_g":"",
"series":"","category":""}}

If PN is not in the document, set all fields empty.
Check all pages for EAN codes (13-digit) and material numbers."""


def truncate_pdf(src: Path, max_pages: int = 10) -> Path:
    """Extract first N pages to smaller PDF."""
    import fitz
    dst = OUT_DIR / src.name
    if dst.exists() and dst.stat().st_size > 1000:
        return dst
    doc = fitz.open(str(src))
    new_doc = fitz.open()
    for i in range(min(max_pages, len(doc))):
        new_doc.insert_pdf(doc, from_page=i, to_page=i)
    new_doc.save(str(dst), deflate=True, garbage=4)
    new_doc.close()
    doc.close()
    return dst


def main():
    from google import genai as genai_new
    from google.genai import types
    from scripts.app_secrets import get_secret

    client = genai_new.Client(api_key=get_secret("GEMINI_API_KEY"))
    parsed = json.loads(RESULTS.read_text(encoding="utf-8"))

    # Find unparsed PDFs
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
        if pn_safe in parsed or pn in parsed:
            continue

        brand = d.get("brand", "") or (d.get("structured_identity") or {}).get("confirmed_manufacturer", "")
        seed = (d.get("content") or {}).get("seed_name", "") or d.get("name", "")
        targets.append((pn, pn_safe, brand, seed, pdf_path))

    # Sort by size ascending (easier ones first)
    targets.sort(key=lambda t: t[4].stat().st_size)

    print(f"Parsing {len(targets)} large PDFs (truncated to 10 pages)")
    print("=" * 80)

    parsed_count = 0
    for idx, (pn, pn_safe, brand, seed, pdf_path) in enumerate(targets):
        orig_size_mb = pdf_path.stat().st_size / (1024*1024)
        print(f"  [{idx+1}/{len(targets)}] {pn:<22} ({orig_size_mb:.1f} MB)... ", end="", flush=True)

        try:
            trunc = truncate_pdf(pdf_path, max_pages=10)
            trunc.stat().st_size // 1024

            uploaded = client.files.upload(file=str(trunc))
            prompt = PROMPT.format(brand=brand, pn=pn, seed=seed)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[uploaded, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=2000,
                ),
            )
            text = response.text.strip() if response.text else ""
            if "```" in text:
                parts = text.split("```")
                text = parts[1] if len(parts) > 1 else text
                if text.startswith("json"): text = text[4:]

            try:
                data = json.loads(text.strip())
                parsed[pn_safe] = data
                parsed_count += 1
                ean = data.get("ean", "")
                title = data.get("title", "")[:40]
                specs = len(data.get("specs", {}))
                print(f"OK specs={specs} ean={ean or '-'}  title={title}")
            except Exception:
                # Save raw for review
                parsed[pn_safe] = {"_partial_raw": text[:500], "_error": "json parse"}
                print("PARTIAL")

            # Save after each
            RESULTS.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")

        except Exception as e:
            print(f"ERROR: {str(e)[:60]}")

        time.sleep(8)

    print(f"\nParsed {parsed_count} new PDFs")


if __name__ == "__main__":
    main()

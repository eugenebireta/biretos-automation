"""Extract specs from downloaded PDF datasheets via Gemini."""
from __future__ import annotations

import json
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.app_secrets import get_secret

ROOT = Path(__file__).resolve().parent.parent.parent
DS_DIR = ROOT / "downloads" / "datasheets_v2"
OUTPUT = ROOT / "downloads" / "staging" / "tier_collector_output"

PROMPT = (
    "IMPORTANT: Read ALL pages of this PDF, not just the first page.\n"
    "The EAN code, article number, and part number are often on page 2 or later pages.\n\n"
    "This is a product datasheet PDF. Extract ALL available data from EVERY page.\n"
    "Return ONLY a valid JSON object, no other text:\n"
    '{"pn":"","article_no":"","brand":"","title":"","description":"",\n'
    '"specs":{},"ean":"","dimensions_mm":"","weight_g":"",\n'
    '"series":"","category":"","certifications":[],"manufacturer_address":""}\n\n'
    "Extract:\n"
    "- pn: Material Number / Part Number\n"
    "- article_no: Article Number (may differ from PN)\n"
    "- ean: EAN-code / GTIN / barcode (MUST check all pages for this)\n"
    "- All specifications: dimensions, weight, voltage, current, temperature,\n"
    "  IP rating, material, color, mounting type, standards\n"
    "- For dimensions use mm. For weight use grams.\n"
    "- series: product series name (e.g. NOVA, Dialog, Aura)\n"
    "Be thorough — check EVERY page for data."
)


def main():
    import google.generativeai as genai

    genai.configure(api_key=get_secret("GEMINI_API_KEY"))
    model = genai.GenerativeModel("gemini-2.5-flash")

    results = {}
    pdfs = sorted(DS_DIR.glob("*.pdf"))
    # Skip catalog (too large)
    pdfs = [p for p in pdfs if "catalog" not in p.stem.lower()]

    print(f"Extracting specs from {len(pdfs)} datasheets via Gemini")
    print("=" * 90)

    for pdf in pdfs:
        pn = pdf.stem
        size_kb = pdf.stat().st_size // 1024
        print(f"  {pn:<22} ({size_kb} KB)... ", end="", flush=True)

        try:
            # Upload file to Gemini
            uploaded = genai.upload_file(str(pdf), mime_type="application/pdf")

            response = model.generate_content(
                [uploaded, PROMPT],
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=4000,
                ),
            )

            raw = response.text.strip()
            # Clean markdown code blocks
            if "```" in raw:
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            data = json.loads(raw)
            results[pn] = data

            specs_count = len(data.get("specs", {}))
            title = data.get("title", "")[:50]
            weight = data.get("weight_g", "?")
            dims = data.get("dimensions_mm", "?")
            ean = data.get("ean", "")
            series = data.get("series", "")

            print(f"OK  specs={specs_count}  weight={weight}  dims={dims}  ean={ean or '-'}  series={series or '-'}")
            print(f"    title: {title}")
            if data.get("specs"):
                for k, v in list(data["specs"].items())[:6]:
                    print(f"    {k}: {v}")

        except json.JSONDecodeError as e:
            # Try to salvage partial JSON
            try:
                # Find last complete key-value and close the JSON
                if raw.startswith("{"):
                    # Find EAN if present
                    import re
                    ean_match = re.search(r'"ean"\s*:\s*"([^"]*)"', raw)
                    title_match = re.search(r'"title"\s*:\s*"([^"]*)"', raw)
                    brand_match = re.search(r'"brand"\s*:\s*"([^"]*)"', raw)
                    pn_match = re.search(r'"pn"\s*:\s*"([^"]*)"', raw)
                    weight_match = re.search(r'"weight_g"\s*:\s*"([^"]*)"', raw)
                    dims_match = re.search(r'"dimensions_mm"\s*:\s*"([^"]*)"', raw)
                    series_match = re.search(r'"series"\s*:\s*"([^"]*)"', raw)

                    partial = {
                        "pn": pn_match.group(1) if pn_match else "",
                        "brand": brand_match.group(1) if brand_match else "",
                        "title": title_match.group(1) if title_match else "",
                        "ean": ean_match.group(1) if ean_match else "",
                        "weight_g": weight_match.group(1) if weight_match else "",
                        "dimensions_mm": dims_match.group(1) if dims_match else "",
                        "series": series_match.group(1) if series_match else "",
                        "_partial": True,
                    }
                    results[pn] = partial
                    print(f"PARTIAL  title={partial['title'][:50]}  ean={partial['ean'] or '-'}  weight={partial['weight_g'] or '-'}")
                else:
                    print(f"JSON ERROR: {e}")
            except Exception:
                print(f"JSON ERROR: {e}")
            print(f"    raw: {raw[:200]}...")
        except Exception as e:
            print(f"ERROR: {e}")

        print()

    out_file = OUTPUT / "datasheet_extracted.json"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(results)} extractions to {out_file}")


if __name__ == "__main__":
    main()

"""Extract specs from downloaded PDF datasheets via Haiku Vision."""
from __future__ import annotations

import json
import sys
import io
import base64
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.app_secrets import get_secret
import anthropic

ROOT = Path(__file__).resolve().parent.parent.parent
DS_DIR = ROOT / "downloads" / "datasheets_v2"
OUTPUT = ROOT / "downloads" / "staging" / "tier_collector_output"

PROMPT = (
    "This is a product datasheet PDF. Extract ALL available data.\n"
    "Return ONLY a JSON object:\n"
    '{"pn":"","brand":"","title":"","description":"",\n'
    '"specs":{},"ean":"","dimensions_mm":"","weight_g":"",\n'
    '"series":"","category":"","certifications":[]}\n\n'
    "Extract every specification: dimensions, weight, voltage, current,\n"
    "temperature range, IP rating, material, color, mounting type,\n"
    "standards, certifications. Be thorough."
)


def main():
    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))
    results = {}

    pdfs = sorted(DS_DIR.glob("*.pdf"))
    print(f"Extracting specs from {len(pdfs)} datasheets")
    print("=" * 80)

    for pdf in pdfs:
        pn = pdf.stem
        size_kb = pdf.stat().st_size // 1024
        print(f"  {pn:<22} ({size_kb} KB)... ", end="", flush=True)

        pdf_data = base64.standard_b64encode(pdf.read_bytes()).decode()

        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "document", "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_data,
                        }},
                        {"type": "text", "text": PROMPT},
                    ],
                }],
            )
            raw = resp.content[0].text.strip()
            if "```" in raw:
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
            results[pn] = data

            specs_count = len(data.get("specs", {}))
            title = data.get("title", "")[:50]
            weight = data.get("weight_g", "?")
            dims = data.get("dimensions_mm", "?")
            ean = data.get("ean", "")
            print(f"OK  specs={specs_count}  weight={weight}  dims={dims}  ean={ean or '-'}")
            print(f"    title: {title}")
            if data.get("specs"):
                for k, v in list(data["specs"].items())[:5]:
                    print(f"    {k}: {v}")
        except Exception as e:
            print(f"ERROR: {e}")

        print()

    out_file = OUTPUT / "datasheet_extracted.json"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(results)} extractions to {out_file}")


if __name__ == "__main__":
    main()

"""Audit datasheet photos via Gemini Vision.

For each photo: classify as product_photo / diagram / schema / table / other.
Keep only product_photos for catalog.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
PHOTOS_DIR = ROOT / "downloads" / "datasheet_photos"
EV_DIR = ROOT / "downloads" / "evidence"
OUT_FILE = ROOT / "downloads" / "staging" / "tier_collector_output" / "photo_audit.json"


def main():
    from google import genai as genai_new
    from google.genai import types
    from scripts.app_secrets import get_secret

    client = genai_new.Client(api_key=get_secret("GEMINI_API_KEY"))

    existing = json.loads(OUT_FILE.read_text(encoding="utf-8")) if OUT_FILE.exists() else {}

    photos = sorted(PHOTOS_DIR.glob("*.*"))
    photos = [p for p in photos if p.name not in existing]

    print(f"Auditing {len(photos)} photos via Gemini Vision")
    print("=" * 80)

    stats = {"product_photo": 0, "diagram": 0, "schema": 0, "table": 0, "other": 0, "error": 0}

    for idx, photo in enumerate(photos):
        pn = photo.stem.split("_p")[0]
        size_kb = photo.stat().st_size // 1024

        # Get product info from evidence
        ev_file = EV_DIR / f"evidence_{pn}.json"
        brand = ""
        seed = ""
        if ev_file.exists():
            d = json.loads(ev_file.read_text(encoding="utf-8"))
            brand = d.get("brand", "") or (d.get("structured_identity") or {}).get("confirmed_manufacturer", "")
            seed = (d.get("content") or {}).get("seed_name", "") or d.get("name", "")

        prompt = (
            f"What is in this image? Product: {brand} {pn} ({seed}).\n\n"
            f"Categories:\n"
            f"- product = photo or rendered image of the actual physical product (regardless of background)\n"
            f"- diagram = line drawing, technical schema, dimensional drawing, blueprint\n"
            f"- schematic = electrical wiring diagram, circuit\n"
            f"- table = specifications table, data grid\n"
            f"- text = page with mostly text/paragraphs\n"
            f"- logo = brand logo, certification mark, icon (small element)\n"
            f"- chart = graph, plot, performance chart\n"
            f"- other = everything else\n\n"
            f"Reply with ONE WORD ONLY (lowercase, from list above)."
        )

        print(f"  [{idx+1}/{len(photos)}] {photo.name:<45} ({size_kb} KB)... ", end="", flush=True)

        try:
            uploaded = client.files.upload(file=str(photo))
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[uploaded, prompt],
                config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=20),
            )
            verdict_raw = response.text.strip().lower() if response.text else "error"

            # Normalize to single category
            verdict = "other"
            for v in ["product", "diagram", "schematic", "table", "text", "logo", "chart"]:
                if v in verdict_raw:
                    verdict = v
                    break

            existing[photo.name] = {"verdict": verdict, "pn": pn, "brand": brand}
            stats[verdict] = stats.get(verdict, 0) + 1
            print(verdict)

        except Exception as e:
            existing[photo.name] = {"verdict": "error", "pn": pn, "error": str(e)[:100]}
            stats["error"] += 1
            print(f"ERROR: {str(e)[:50]}")

        if (idx + 1) % 20 == 0:
            OUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

        # Adaptive sleep: increase on errors
        if stats.get("error", 0) > 3:
            time.sleep(15)
        else:
            time.sleep(7)

    OUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'='*60}")
    print("Audit complete:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"\nOutput: {OUT_FILE}")


if __name__ == "__main__":
    main()

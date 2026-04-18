"""Photo audit via AI Router (Gemini primary, Claude fallback).

When Gemini rate limit exhausted, auto-fallback to Claude Haiku.
"""
from __future__ import annotations

import json
import sys
import base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
PHOTOS_DIR = ROOT / "downloads" / "datasheet_photos"
EV_DIR = ROOT / "downloads" / "evidence"
OUT_FILE = ROOT / "downloads" / "staging" / "tier_collector_output" / "photo_audit.json"

from scripts.pipeline_v2.ai_router import _LIMITER, _log_usage


PROMPT_TEXT = """What is in this image? Product: {brand} {pn} ({seed}).

Categories:
- product = photo or rendered image of the actual physical product (any background)
- diagram = line drawing, technical schema, dimensional drawing
- schematic = electrical wiring diagram, circuit
- table = specifications table, data grid
- text = page with mostly text
- logo = brand logo, certification mark
- chart = graph, plot, performance chart
- other = everything else

Reply with ONE WORD ONLY (lowercase)."""


def classify_photo(photo: Path, brand: str, pn: str, seed: str) -> tuple[str, dict]:
    """Classify photo using Gemini first, fallback to Claude."""
    prompt = PROMPT_TEXT.format(brand=brand or "unknown", pn=pn, seed=seed[:100])

    # Try Gemini first
    try:
        from google import genai as genai_new
        from google.genai import types
        from scripts.app_secrets import get_secret

        _LIMITER.wait_if_needed("gemini-2.5-flash")
        client = genai_new.Client(api_key=get_secret("GEMINI_API_KEY"))
        uploaded = client.files.upload(file=str(photo))

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[uploaded, prompt],
            config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=20),
        )
        text = response.text.strip().lower() if response.text else ""
        usage = response.usage_metadata
        cost = ((usage.prompt_token_count if usage else 0) * 0.075 +
                (usage.candidates_token_count if usage else 0) * 0.30) / 1_000_000
        _log_usage("gemini-2.5-flash", usage.prompt_token_count if usage else 0,
                   usage.candidates_token_count if usage else 0, cost, "photo_audit", True)
        return text, {"model": "gemini", "cost_usd": cost}

    except Exception as e:
        err = str(e)
        if "RESOURCE_EXHAUSTED" not in err and "429" not in err:
            # Not a rate-limit issue, something else
            return "", {"error": err[:200]}

    # Fallback to Claude
    try:
        from scripts.app_secrets import get_secret
        import anthropic

        _LIMITER.wait_if_needed("claude-haiku-4-5")
        client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

        img_data = base64.standard_b64encode(photo.read_bytes()).decode()
        ext = photo.suffix[1:].lower()
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=20,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime, "data": img_data}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        text = response.content[0].text.strip().lower()
        cost = (response.usage.input_tokens * 1.00 +
                response.usage.output_tokens * 5.00) / 1_000_000
        _log_usage("claude-haiku-4-5", response.usage.input_tokens,
                   response.usage.output_tokens, cost, "photo_audit", True)
        return text, {"model": "claude", "cost_usd": cost}
    except Exception as e:
        return "", {"error": str(e)[:200]}


def main():
    existing = json.loads(OUT_FILE.read_text(encoding="utf-8")) if OUT_FILE.exists() else {}

    # Reset errors so we retry them
    to_process = []
    for photo in sorted(PHOTOS_DIR.glob("*.*")):
        existing_verdict = existing.get(photo.name, {}).get("verdict", "")
        if existing_verdict and existing_verdict != "error":
            continue  # already classified
        to_process.append(photo)

    print(f"Photo audit via router: {len(to_process)} photos")
    print("=" * 80)

    stats = {"product": 0, "diagram": 0, "schematic": 0, "table": 0, "text": 0,
             "logo": 0, "chart": 0, "other": 0, "error": 0}
    total_cost = 0.0

    for idx, photo in enumerate(to_process):
        pn = photo.stem.split("_p")[0]
        ev_file = EV_DIR / f"evidence_{pn}.json"
        brand = ""
        seed = ""
        if ev_file.exists():
            d = json.loads(ev_file.read_text(encoding="utf-8"))
            brand = d.get("brand", "") or (d.get("structured_identity") or {}).get("confirmed_manufacturer", "")
            seed = (d.get("content") or {}).get("seed_name", "") or d.get("name", "")

        print(f"  [{idx+1}/{len(to_process)}] {photo.name[:50]:<50} ", end="", flush=True)

        verdict_raw, meta = classify_photo(photo, brand, pn, seed)
        if "error" in meta:
            stats["error"] += 1
            existing[photo.name] = {"verdict": "error", "pn": pn, "error": meta["error"]}
            print("ERROR")
            continue

        # Normalize
        verdict = "other"
        for v in ["product", "diagram", "schematic", "table", "text", "logo", "chart"]:
            if v in verdict_raw:
                verdict = v
                break

        stats[verdict] = stats.get(verdict, 0) + 1
        cost = meta.get("cost_usd", 0)
        total_cost += cost
        existing[photo.name] = {
            "verdict": verdict, "pn": pn, "brand": brand,
            "model": meta.get("model", ""),
            "cost_usd": cost,
        }
        print(f"{verdict} ({meta.get('model','')}, ${cost:.5f})")

        if (idx + 1) % 20 == 0:
            OUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    OUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("=" * 80)
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"  Total cost: ${total_cost:.4f}")


if __name__ == "__main__":
    main()

"""Compare Gemini 2.5 Flash vs Claude Haiku 4.5 on datasheet parsing.

Tests on 10 PDFs that we already parsed via Gemini.
Measures:
- Accuracy: EAN match, specs count, title quality
- Cost: tokens used, $ per request
- Speed: seconds per request
"""
from __future__ import annotations

import json
import sys
import time
import base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
DS_DIR = ROOT / "downloads" / "datasheets_v2"
GEMINI_RESULTS = ROOT / "downloads" / "staging" / "tier_collector_output" / "datasheet_extracted.json"
OUT_FILE = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "gemini_vs_claude_comparison.json"

# Test on PDFs that have known EAN (so we can verify accuracy)
TEST_PNS = [
    "00020211", "2CDG110146R0011", "2CDG110177R0011", "3240197",
    "773111", "773211", "775511", "1050000000", "193111", "902591",
]

PROMPT = (
    "This is a product datasheet PDF. Extract data from ALL pages.\n"
    "Return ONLY a JSON object:\n"
    '{"pn":"","brand":"","title":"","ean":"","specs":{},"weight_g":"","dimensions_mm":"","series":""}\n\n'
    "Find EAN code (13 digits), title, all technical specs, weight, dimensions, series.\n"
    "Check ALL pages — EAN often on page 2."
)


def test_gemini(pdf_path: Path):
    from google import genai as genai_new
    from google.genai import types
    from scripts.app_secrets import get_secret

    client = genai_new.Client(api_key=get_secret("GEMINI_API_KEY"))

    start = time.time()
    uploaded = client.files.upload(file=str(pdf_path))
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[uploaded, PROMPT],
        config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=2000),
    )
    elapsed = time.time() - start

    text = response.text.strip() if response.text else ""
    if "```" in text:
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"): text = text[4:]
    text = text.strip()

    # Get token usage from response
    usage = response.usage_metadata
    input_tokens = usage.prompt_token_count if usage else 0
    output_tokens = usage.candidates_token_count if usage else 0

    # Cost: $0.075/M input, $0.30/M output
    cost = (input_tokens * 0.075 + output_tokens * 0.30) / 1_000_000

    try:
        data = json.loads(text)
    except Exception:
        data = {"_raw": text[:500], "_parse_error": True}

    return {
        "data": data,
        "elapsed_sec": round(elapsed, 1),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 5),
    }


def test_claude(pdf_path: Path):
    from scripts.app_secrets import get_secret
    import anthropic

    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    pdf_data = base64.standard_b64encode(pdf_path.read_bytes()).decode()

    start = time.time()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
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
    elapsed = time.time() - start

    text = response.content[0].text.strip()
    if "```" in text:
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"): text = text[4:]
    text = text.strip()

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    # Cost: $1.00/M input, $5.00/M output
    cost = (input_tokens * 1.00 + output_tokens * 5.00) / 1_000_000

    try:
        data = json.loads(text)
    except Exception:
        data = {"_raw": text[:500], "_parse_error": True}

    return {
        "data": data,
        "elapsed_sec": round(elapsed, 1),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 5),
    }


def main():
    json.loads(GEMINI_RESULTS.read_text(encoding="utf-8"))
    results = {}

    print("=" * 90)
    print("Gemini 2.5 Flash vs Claude Haiku 4.5 — datasheet parsing comparison")
    print("=" * 90)
    print(f"{'PN':<22} {'Engine':<10} {'Time':<6} {'Tokens':<14} {'Cost':<10} {'EAN':<16} {'Specs'}")
    print("-" * 90)

    totals = {"gemini": {"time": 0, "tokens_in": 0, "tokens_out": 0, "cost": 0, "eans": 0, "specs": 0},
              "claude": {"time": 0, "tokens_in": 0, "tokens_out": 0, "cost": 0, "eans": 0, "specs": 0}}

    for pn in TEST_PNS:
        pdf_path = DS_DIR / f"{pn}.pdf"
        if not pdf_path.exists():
            continue

        results[pn] = {}

        # Gemini
        try:
            g = test_gemini(pdf_path)
            results[pn]["gemini"] = g
            ean = str(g["data"].get("ean", ""))
            specs = len(g["data"].get("specs", {})) if isinstance(g["data"].get("specs"), dict) else 0
            totals["gemini"]["time"] += g["elapsed_sec"]
            totals["gemini"]["tokens_in"] += g["input_tokens"]
            totals["gemini"]["tokens_out"] += g["output_tokens"]
            totals["gemini"]["cost"] += g["cost_usd"]
            if ean.isdigit() and len(ean) == 13:
                totals["gemini"]["eans"] += 1
            totals["gemini"]["specs"] += specs
            print(f"{pn:<22} Gemini    {g['elapsed_sec']}s  in={g['input_tokens']}/out={g['output_tokens']:<5} ${g['cost_usd']:<8.5f} {ean:<16} {specs}")
        except Exception as e:
            print(f"{pn:<22} Gemini    ERROR: {str(e)[:50]}")

        time.sleep(2)

        # Claude
        try:
            c = test_claude(pdf_path)
            results[pn]["claude"] = c
            ean = str(c["data"].get("ean", ""))
            specs = len(c["data"].get("specs", {})) if isinstance(c["data"].get("specs"), dict) else 0
            totals["claude"]["time"] += c["elapsed_sec"]
            totals["claude"]["tokens_in"] += c["input_tokens"]
            totals["claude"]["tokens_out"] += c["output_tokens"]
            totals["claude"]["cost"] += c["cost_usd"]
            if ean.isdigit() and len(ean) == 13:
                totals["claude"]["eans"] += 1
            totals["claude"]["specs"] += specs
            print(f"{pn:<22} Claude    {c['elapsed_sec']}s  in={c['input_tokens']}/out={c['output_tokens']:<5} ${c['cost_usd']:<8.5f} {ean:<16} {specs}")
        except Exception as e:
            print(f"{pn:<22} Claude    ERROR: {str(e)[:50]}")

        time.sleep(2)
        print()

    print("=" * 90)
    print("SUMMARY")
    print("=" * 90)
    for engine in ["gemini", "claude"]:
        t = totals[engine]
        print(f"{engine.upper()}:")
        print(f"  Total time:    {t['time']:.1f}s")
        print(f"  Tokens in:     {t['tokens_in']:,}")
        print(f"  Tokens out:    {t['tokens_out']:,}")
        print(f"  Total cost:    ${t['cost']:.4f}")
        print(f"  Cost per PDF:  ${t['cost']/len(TEST_PNS):.4f}")
        print(f"  EANs found:    {t['eans']}/{len(TEST_PNS)}")
        print(f"  Total specs:   {t['specs']}")
        print()

    # Cost ratio
    if totals["gemini"]["cost"] > 0:
        ratio = totals["claude"]["cost"] / totals["gemini"]["cost"]
        print(f"Claude is {ratio:.1f}x more expensive than Gemini")
    if totals["claude"]["cost"] > 0:
        ratio = totals["gemini"]["cost"] / totals["claude"]["cost"]
        print(f"Gemini is {ratio:.1f}x cheaper than Claude")

    # Save
    OUT_FILE.write_text(json.dumps({
        "results": results,
        "totals": totals,
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved: {OUT_FILE}")


if __name__ == "__main__":
    main()

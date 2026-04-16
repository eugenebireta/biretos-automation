"""Retry EAN extraction via Claude Haiku for PDFs where Gemini failed.

Only targets PDFs that Gemini parsed but didn't find EAN.
Uses Claude for higher accuracy on EAN detection.
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
EV_DIR = ROOT / "downloads" / "evidence"
RESULTS_DS = ROOT / "downloads" / "staging" / "tier_collector_output" / "datasheet_extracted.json"
RESULTS_FOCUSED = ROOT / "downloads" / "staging" / "tier_collector_output" / "ean_focused_extraction.json"
RESULTS_DIST = ROOT / "downloads" / "staging" / "tier_collector_output" / "ean_from_distributors.json"
RESULTS_EXTENDED = ROOT / "downloads" / "staging" / "tier_collector_output" / "ean_extended_search.json"
OUT_FILE = ROOT / "downloads" / "staging" / "tier_collector_output" / "ean_claude_retry.json"

PROMPT = """Find the EAN-13 code for this product: {brand} {pn}.

EAN codes are exactly 13 digits, often found on:
- Last page of datasheet (article number tables)
- Near manufacturer address
- After "EAN:", "GTIN:", or "Barcode:"

Check EVERY page carefully.

Return ONLY a JSON object:
{{"ean":"<13-digit EAN>","page_found":<page_num>,"confidence":"high|medium|low"}}

If no EAN found, return: {{"ean":"","page_found":0,"confidence":"not_found"}}

DO NOT invent numbers. Only return EAN that is visible in the document."""


def validate_ean13(ean: str) -> bool:
    if not ean or not ean.isdigit() or len(ean) != 13:
        return False
    digits = [int(d) for d in ean]
    checksum = sum(digits[i] * (3 if i % 2 else 1) for i in range(12))
    check_digit = (10 - (checksum % 10)) % 10
    return check_digit == digits[12]


def main():
    from scripts.app_secrets import get_secret
    import anthropic

    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    # Load all existing EANs
    have_ean = set()
    for f in [RESULTS_DS, RESULTS_FOCUSED, RESULTS_DIST, RESULTS_EXTENDED]:
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            for pn, d in data.items():
                if validate_ean13(str(d.get("ean", ""))):
                    have_ean.add(pn)

    existing = json.loads(OUT_FILE.read_text(encoding="utf-8")) if OUT_FILE.exists() else {}

    # Find SKUs with PDF but no valid EAN yet
    targets = []
    for f in sorted(EV_DIR.glob("evidence_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        if not pn or pn.strip("-_") == "" or pn in {"---","--","_","PN","-----"}:
            continue
        pn_safe = pn.replace("/", "_").replace(" ", "_")
        if pn_safe in have_ean or pn in have_ean or pn_safe in existing:
            continue
        pdf = DS_DIR / f"{pn_safe}.pdf"
        if not pdf.exists():
            continue
        # Skip very large
        if pdf.stat().st_size > 20 * 1024 * 1024:
            continue

        brand = d.get("brand", "") or (d.get("structured_identity") or {}).get("confirmed_manufacturer", "")
        targets.append((pn, pn_safe, brand, pdf))

    print(f"Claude EAN retry: {len(targets)} PDFs")
    print("=" * 80)

    found = 0
    total_cost = 0.0

    for idx, (pn, pn_safe, brand, pdf) in enumerate(targets):
        size_kb = pdf.stat().st_size // 1024
        print(f"  [{idx+1}/{len(targets)}] {pn:<22} ({size_kb} KB)... ", end="", flush=True)

        try:
            pdf_data = base64.standard_b64encode(pdf.read_bytes()).decode()
            prompt = PROMPT.format(brand=brand, pn=pn)

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "document", "source": {
                            "type": "base64", "media_type": "application/pdf", "data": pdf_data,
                        }},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            text = response.content[0].text.strip()
            if "```" in text:
                parts = text.split("```")
                text = parts[1] if len(parts) > 1 else text
                if text.startswith("json"): text = text[4:]

            try:
                data = json.loads(text.strip())
                ean = str(data.get("ean", "")).strip()
                if validate_ean13(ean):
                    existing[pn_safe] = {
                        "ean": ean,
                        "page_found": data.get("page_found", 0),
                        "confidence": data.get("confidence", ""),
                        "model": "claude-haiku-4-5",
                        "valid": True,
                    }
                    found += 1
                    print(f"EAN={ean} (p{data.get('page_found',0)})")
                else:
                    existing[pn_safe] = {"ean": "", "model": "claude-haiku-4-5", "raw": text[:200]}
                    print("no EAN")
            except Exception:
                existing[pn_safe] = {"ean": "", "raw": text[:200]}
                print("parse error")

            # Cost
            tokens_in = response.usage.input_tokens
            tokens_out = response.usage.output_tokens
            cost = (tokens_in * 1.00 + tokens_out * 5.00) / 1_000_000
            total_cost += cost

        except Exception as e:
            err = str(e)
            if "overloaded" in err.lower() or "529" in err:
                print("overloaded, sleeping 30s")
                time.sleep(30)
                continue
            existing[pn_safe] = {"error": err[:200]}
            print(f"ERROR: {err[:50]}")

        if (idx + 1) % 20 == 0:
            OUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

        time.sleep(1.5)  # Claude has high rate limit

    OUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nClaude EAN retry results:")
    print(f"  Found: {found}")
    print(f"  Total cost: ${total_cost:.4f}")


if __name__ == "__main__":
    main()

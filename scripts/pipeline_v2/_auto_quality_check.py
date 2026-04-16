"""Automatic quality check of pipeline results via Claude Sonnet 4.5.

Sonnet reviews: EAN correctness, title quality, description accuracy,
photo-product match, specs consistency.

Returns structured findings: passed/failed/needs_fix per SKU.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
OUT_FILE = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "quality_check.json"


REVIEW_PROMPT = """You are QA auditor for a product catalog. Review this product record for correctness.

Product data:
{data}

Check these items. Return JSON:
{{
  "pn_brand_match": "ok|mismatch|unclear",
  "title_quality": "good|generic|wrong|missing",
  "ean_plausibility": "valid|suspicious|wrong_prefix|missing",
  "description_quality": "good|too_short|off_topic|missing",
  "specs_completeness": "full|partial|empty",
  "data_consistency": "consistent|conflicting|unclear",
  "overall_verdict": "READY|NEEDS_FIX|REJECT",
  "issues": ["list specific issues"],
  "recommendations": ["what to fix"]
}}

Specific rules:
- EAN must be 13 digits, valid GS1 prefix for the brand (PEHA=4010105, ABB=4016779, Howard Leight=7312550/7312553)
- Title should name the actual product (not just PN)
- Description >200 words and on-topic for this product
- Specs should match product type (switch=material/color, valve=pressure/size)
- Warning signs: title mentions different product than PN/brand, EAN prefix mismatches brand, description generic"""


def get_brand_expected_prefix(brand: str) -> str:
    prefixes = {
        "PEHA": "4010105",
        "ABB": "4016779",
        "Howard Leight": "7312550",
        "Esser": "4007185",
        "Weidmuller": "4008190",
        "Weidmüller": "4008190",
        "Phoenix Contact": "4046356",
    }
    return prefixes.get(brand, "")


def build_review_data(pn: str) -> dict:
    """Build compact review data from evidence + descriptions."""
    ev_file = EV_DIR / f"evidence_{pn}.json"
    if not ev_file.exists():
        ev_file = EV_DIR / f"evidence_{pn.replace('_','/')}.json"
    if not ev_file.exists():
        return None

    d = json.loads(ev_file.read_text(encoding="utf-8"))
    fd = d.get("from_datasheet", {})
    norm = d.get("normalized") or {}
    si = d.get("structured_identity") or {}

    brand = d.get("brand", "") or si.get("confirmed_manufacturer", "")
    subbrand = d.get("subbrand", "")
    real_brand = subbrand or brand

    # Load description if exists
    seo_file = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "descriptions_seo.json"
    seo_desc = ""
    if seo_file.exists():
        desc_data = json.loads(seo_file.read_text(encoding="utf-8"))
        pn_safe = pn.replace("/", "_").replace(" ", "_")
        entry = desc_data.get(pn) or desc_data.get(pn_safe, {})
        seo_desc = entry.get("description_seo_ru", "")[:500]

    specs = fd.get("specs", {})
    if isinstance(specs, dict):
        specs_str = "; ".join(f"{k}: {v}" for k, v in list(specs.items())[:8])
    else:
        specs_str = ""

    ean = fd.get("ean", "")
    ean_prefix = str(ean)[:7] if ean else ""
    expected_prefix = get_brand_expected_prefix(real_brand)

    return {
        "pn": pn,
        "brand": real_brand,
        "seed_name_from_excel": (d.get("content") or {}).get("seed_name", "") or d.get("name", ""),
        "title_from_datasheet": fd.get("title", ""),
        "series": fd.get("series", ""),
        "ean": ean,
        "ean_prefix": ean_prefix,
        "expected_ean_prefix": expected_prefix,
        "prefix_matches": ean_prefix == expected_prefix if expected_prefix else "no_rule",
        "ean_source": fd.get("ean_source", ""),
        "specs_count": len(specs) if isinstance(specs, dict) else 0,
        "specs_sample": specs_str,
        "weight_g": fd.get("weight_g", ""),
        "dimensions_mm": fd.get("dimensions_mm", ""),
        "description_first_500": seo_desc,
        "description_words": len(seo_desc.split()),
        "price": norm.get("best_price"),
        "price_currency": norm.get("best_price_currency", ""),
        "has_datasheet_pdf": bool(fd.get("datasheet_pdf")),
        "verified_photos": fd.get("verified_photo_count", 0),
    }


def review_sku_via_claude(client, data: dict) -> dict:
    """Send to Claude Sonnet for quality review."""
    prompt = REVIEW_PROMPT.format(data=json.dumps(data, indent=2, ensure_ascii=False))

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    if "```" in text:
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"): text = text[4:]
    text = text.strip()

    try:
        result = json.loads(text)
    except Exception:
        return {"error": "parse_failed", "raw": text[:500]}

    cost = (response.usage.input_tokens * 3.00 + response.usage.output_tokens * 15.00) / 1_000_000
    result["_cost_usd"] = round(cost, 5)
    return result


def main():
    from scripts.app_secrets import get_secret
    import anthropic

    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    # Load existing results to skip already reviewed
    existing = json.loads(OUT_FILE.read_text(encoding="utf-8")) if OUT_FILE.exists() else {}

    # Build list of SKUs with data to review (priority: EAN present OR description present)
    candidates = []
    seo_file = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "descriptions_seo.json"
    seo_data = json.loads(seo_file.read_text(encoding="utf-8")) if seo_file.exists() else {}

    for f in sorted(EV_DIR.glob("evidence_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        if not pn or pn.strip("-_") == "" or pn in {"---", "--", "_", "PN", "-----"}:
            continue
        if pn in existing:
            continue
        fd = d.get("from_datasheet", {})
        # Only review SKUs with meaningful data
        has_ean = bool(fd.get("ean"))
        has_desc = (seo_data.get(pn) or seo_data.get(pn.replace("/","_"), {})).get("word_count", 0) >= 150
        if not (has_ean or has_desc or fd.get("title")):
            continue
        candidates.append(pn)

    # Full audit mode
    sample = candidates

    print(f"Quality Check: reviewing {len(sample)} random SKUs (of {len(candidates)} candidates)")
    print("=" * 90)

    stats = {"READY": 0, "NEEDS_FIX": 0, "REJECT": 0, "error": 0}
    total_cost = 0

    for idx, pn in enumerate(sample):
        data = build_review_data(pn)
        if not data:
            continue

        print(f"  [{idx+1}/{len(sample)}] {pn:<22}... ", end="", flush=True)

        result = review_sku_via_claude(client, data)
        if "error" in result:
            stats["error"] += 1
            print(f"ERROR: {result['error']}")
            existing[pn] = result
            continue

        verdict = result.get("overall_verdict", "unknown").upper()
        stats[verdict] = stats.get(verdict, 0) + 1
        cost = result.get("_cost_usd", 0)
        total_cost += cost

        issues_count = len(result.get("issues", []))
        print(f"{verdict} ({issues_count} issues, ${cost:.4f})")
        existing[pn] = result

        if (idx + 1) % 5 == 0:
            OUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    OUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("=" * 90)
    print("Summary:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"Total cost: ${total_cost:.4f}")
    print(f"Output: {OUT_FILE}")

    # Print issues summary
    print("\nTop issues across SKUs:")
    issue_counter = defaultdict(int)
    for pn, r in existing.items():
        for issue in (r.get("issues") or []):
            issue_counter[issue[:80]] += 1
    for issue, n in sorted(issue_counter.items(), key=lambda x: -x[1])[:10]:
        print(f"  {n}x: {issue}")


if __name__ == "__main__":
    main()

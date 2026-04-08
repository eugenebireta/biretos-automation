"""deep_research_formatter.py — Export pilot SKUs for deep research (Claude Pro / Gemini DR).

Selects 20-30 SKUs in a stratified sample covering:
- High confidence (REVIEW/AUTO) — verify existing data
- Has price but weak identity — confirm identity
- No price, strong identity — find price
- Weak identity, no price — hardest cases

One SKU = one provider (not mass cross-validation).
Distribution: Claude Pro (brand batches) / Gemini DR (web retrieval) / ChatGPT DR (synthesis).

Output:
    research_results/pilot/
        pilot_skus.json              — full manifest
        claude_pro_batch.json        — prompt pack for Claude Pro
        gemini_dr_batch.json         — prompt pack for Gemini DR
        chatgpt_dr_batch.json        — prompt pack for ChatGPT DR
        README.md                    — workflow instructions

Usage:
    python scripts/deep_research_formatter.py [--checkpoint PATH] [--count 25]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Optional

_DEFAULT_CHECKPOINT = Path(__file__).parent.parent / "downloads" / "checkpoint.json"
_PILOT_DIR = Path(__file__).parent.parent / "research_results" / "pilot"


def select_pilot_skus(
    checkpoint: dict,
    count: int = 25,
    seed: int = 42,
) -> list[dict]:
    """Stratified selection of pilot SKUs from checkpoint."""
    rng = random.Random(seed)

    # Build strata
    auto_publish = []
    review_required = []
    draft_with_price = []
    draft_no_price_strong = []
    weak_any = []

    for pn, bundle in checkpoint.items():
        pdv2 = bundle.get("policy_decision_v2", {})
        price = bundle.get("price", {})
        photo = bundle.get("photo", {})
        identity = pdv2.get("identity_level", "weak")
        status = pdv2.get("card_status", "DRAFT_ONLY")
        has_price = price.get("price_status") not in ("no_price_found", "", None)

        entry = {
            "pn": pn,
            "brand": bundle.get("brand", "Honeywell"),
            "name": bundle.get("name", ""),
            "expected_category": bundle.get("expected_category", ""),
            "identity_level": identity,
            "card_status": status,
            "has_price": has_price,
            "has_photo": photo.get("verdict") == "KEEP",
        }
        if status == "AUTO_PUBLISH":
            auto_publish.append(entry)
        elif status == "REVIEW_REQUIRED":
            review_required.append(entry)
        elif has_price and identity == "weak":
            draft_with_price.append(entry)
        elif not has_price and identity in ("strong", "confirmed"):
            draft_no_price_strong.append(entry)
        else:
            weak_any.append(entry)

    # Sample from strata (proportional, min 1 per stratum)
    total = count
    targets = {
        "auto_publish": max(1, min(len(auto_publish), 2)),
        "review_required": max(1, min(len(review_required), 5)),
        "draft_with_price": max(1, min(len(draft_with_price), 8)),
        "draft_no_price_strong": max(1, min(len(draft_no_price_strong), 5)),
        "weak_any": max(1, min(len(weak_any), 5)),
    }

    selected = []
    for stratum_name, stratum_list in [
        ("auto_publish", auto_publish),
        ("review_required", review_required),
        ("draft_with_price", draft_with_price),
        ("draft_no_price_strong", draft_no_price_strong),
        ("weak_any", weak_any),
    ]:
        n = targets[stratum_name]
        sample = rng.sample(stratum_list, min(n, len(stratum_list)))
        for s in sample:
            s["stratum"] = stratum_name
        selected.extend(sample)

    return selected[:count]


def _build_research_prompt(entry: dict, provider: str) -> str:
    """Build a research prompt for a single SKU."""
    pn = entry["pn"]
    brand = entry["brand"]
    name = entry["name"] or pn
    category = entry["expected_category"] or "industrial product"

    context_lines = [
        f"Part Number: {pn}",
        f"Brand: {brand}",
        f"Product Name: {name}",
        f"Expected Category: {category}",
    ]
    if not entry["has_price"]:
        context_lines.append("TASK: Price not found — find current market price (RUB)")
    if entry["identity_level"] == "weak":
        context_lines.append("TASK: Identity weak — confirm this is a real product")
    if not entry["has_photo"]:
        context_lines.append("TASK: No photo — find official product image URL")

    context = "\n".join(context_lines)

    critical_instruction = (
        "\n\nCRITICAL: Your response MUST end with a JSON block:\n"
        "```json\n"
        "{\n"
        '  "pn_confirmed": true/false,\n'
        '  "product_name": "...",\n'
        '  "category": "...",\n'
        '  "price_rub": null or number,\n'
        '  "price_source_url": "...",\n'
        '  "image_url": null or "...",\n'
        '  "datasheet_url": null or "...",\n'
        '  "confidence": "high"|"medium"|"low",\n'
        '  "notes": "..."\n'
        "}\n"
        "```"
    )

    if provider == "claude_pro":
        intro = f"Research this industrial product and find all available information:\n\n{context}"
    elif provider == "gemini_dr":
        intro = f"Use web search to research this industrial product:\n\n{context}"
    else:  # chatgpt_dr
        intro = f"Search the web for this industrial product and synthesize findings:\n\n{context}"

    return intro + critical_instruction


def format_pilot_batches(
    pilot_skus: list[dict],
) -> dict[str, list[dict]]:
    """Assign SKUs to providers and build prompt batches."""
    # Simple round-robin assignment
    providers = ["claude_pro", "gemini_dr", "chatgpt_dr"]
    batches: dict[str, list[dict]] = {p: [] for p in providers}

    for i, entry in enumerate(pilot_skus):
        provider = providers[i % len(providers)]
        batches[provider].append({
            "pn": entry["pn"],
            "brand": entry["brand"],
            "stratum": entry.get("stratum", "unknown"),
            "provider": provider,
            "prompt": _build_research_prompt(entry, provider),
            "context": {
                "identity_level": entry["identity_level"],
                "card_status": entry["card_status"],
                "has_price": entry["has_price"],
                "has_photo": entry["has_photo"],
            },
        })

    return batches


def export_pilot(
    checkpoint_path: Path = _DEFAULT_CHECKPOINT,
    count: int = 25,
    output_dir: Path = _PILOT_DIR,
) -> dict:
    """Export pilot research batches. Returns summary."""
    checkpoint = json.loads(checkpoint_path.read_text("utf-8"))
    pilot_skus = select_pilot_skus(checkpoint, count=count)
    batches = format_pilot_batches(pilot_skus)

    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "total_selected": len(pilot_skus),
        "strata": {},
        "skus": pilot_skus,
    }
    for sku in pilot_skus:
        s = sku.get("stratum", "unknown")
        manifest["strata"][s] = manifest["strata"].get(s, 0) + 1

    (output_dir / "pilot_skus.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for provider, items in batches.items():
        (output_dir / f"{provider}_batch.json").write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    readme = (
        "# Deep Research Pilot\n\n"
        f"Generated: {len(pilot_skus)} SKUs across 3 providers.\n\n"
        "## Workflow\n\n"
        "1. `claude_pro_batch.json` → Run prompts in Claude.ai (Pro account)\n"
        "2. `gemini_dr_batch.json` → Run prompts in Google AI Studio\n"
        "3. `chatgpt_dr_batch.json` → Run prompts in ChatGPT with web search\n\n"
        "Each prompt ends with a CRITICAL JSON block — copy/paste the JSON response.\n\n"
        "## Result format\n\n"
        "Save results as `pilot_results/<pn>_result.json` with the raw JSON block.\n"
    )
    (output_dir / "README.md").write_text(readme, encoding="utf-8")

    return {
        "total": len(pilot_skus),
        "strata": manifest["strata"],
        "providers": {p: len(items) for p, items in batches.items()},
        "output_dir": str(output_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default=str(_DEFAULT_CHECKPOINT))
    parser.add_argument("--count", type=int, default=25)
    args = parser.parse_args()

    summary = export_pilot(Path(args.checkpoint), count=args.count)
    print(f"Pilot exported: {summary['total']} SKUs")
    print(f"Strata: {summary['strata']}")
    print(f"Providers: {summary['providers']}")
    print(f"Output: {summary['output_dir']}")


if __name__ == "__main__":
    main()

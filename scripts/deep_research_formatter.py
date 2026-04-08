"""deep_research_formatter.py — Export pilot SKUs for Deep Research subscriptions.

Revenue-first selection from DRAFT_ONLY SKUs.
Smart provider routing (not round-robin):
  - Gemini DR: exact PN hunting, manufacturer/distributor retrieval
  - Claude Projects/Research: brand-family batches, long context
  - ChatGPT Deep Research: tie-breaker, synthesis, conflict cases

1 SKU = 1 provider (no mass cross-validation).
Includes search constraints (already-searched domains) to avoid wasted effort.

Output structure (training-data-ready):
    research_results/deep/
        manifest.json                    — full pilot manifest
        gemini_dr/<pn>.md               — individual prompts
        claude_pro/<pn>.md              — individual prompts
        chatgpt_dr/<pn>.md              — individual prompts

Results saved alongside prompts as raw answers (future training corpus).

Usage:
    python scripts/deep_research_formatter.py [--checkpoint PATH] [--count 25]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

_DEFAULT_CHECKPOINT = Path(__file__).parent.parent / "downloads" / "checkpoint.json"
_EVIDENCE_DIR = Path(__file__).parent.parent / "downloads" / "evidence"
_OUTPUT_DIR = Path(__file__).parent.parent / "research_results" / "deep"


def select_pilot_skus(
    checkpoint: dict,
    count: int = 25,
) -> list[dict]:
    """Revenue-first selection from DRAFT_ONLY SKUs.

    Priority order:
    1. Strong identity DRAFT (sorted by owner_price descending)
    2. Weak identity DRAFT (sorted by owner_price descending)
    """
    drafts = []
    for pn, bundle in checkpoint.items():
        pdv2 = bundle.get("policy_decision_v2", {})
        if pdv2.get("card_status") != "DRAFT_ONLY":
            continue

        price = bundle.get("price", {})
        photo = bundle.get("photo", {})
        identity = pdv2.get("identity_level", "weak")
        price_status = price.get("price_status", "no_price_found")
        photo_verdict = photo.get("verdict", "NO_PHOTO")

        # Parse owner price for revenue sorting
        our_price_raw = str(bundle.get("our_price_raw", "")).strip()
        try:
            owner_price = float(our_price_raw.replace(",", ".").replace(" ", ""))
        except (ValueError, AttributeError):
            owner_price = 0.0

        # Determine blockers
        # Price statuses that are NOT publishable
        _NO_USABLE_PRICE = {
            "no_price_found", "hidden_price", "category_mismatch_only",
            "ambiguous_offer", "", None,
        }
        blockers = []
        if identity == "weak":
            blockers.append("identity_weak")
        if price_status in _NO_USABLE_PRICE:
            blockers.append("no_price")
        if photo_verdict in ("REJECT", "NO_PHOTO"):
            blockers.append("photo_problem")

        # Collect already-searched URLs from evidence
        searched_domains = _get_searched_domains(pn, bundle)

        drafts.append({
            "pn": pn,
            "brand": bundle.get("brand", "Honeywell"),
            "name": bundle.get("name", ""),
            "category": bundle.get("category", ""),
            "identity_level": identity,
            "price_status": price_status,
            "owner_price_rub": owner_price,
            "photo_verdict": photo_verdict,
            "blockers": blockers,
            "searched_domains": searched_domains,
        })

    # Sort: strong identity first, then by owner_price descending
    drafts.sort(
        key=lambda x: (0 if x["identity_level"] == "strong" else 1, -x["owner_price_rub"]),
    )
    return drafts[:count]


def _get_searched_domains(pn: str, bundle: dict) -> list[str]:
    """Collect domains already searched for this SKU."""
    domains = set()

    # From price source_url
    source_url = bundle.get("price", {}).get("source_url", "")
    if source_url:
        d = urlparse(source_url).netloc
        if d:
            domains.add(d)

    # From evidence file
    safe_pn = re.sub(r'[\\/:*?"<>|]', "_", pn)
    ev_path = _EVIDENCE_DIR / f"evidence_{safe_pn}.json"
    if ev_path.exists():
        try:
            ev = json.loads(ev_path.read_text("utf-8"))
            for url in ev.get("searched_urls", []):
                d = urlparse(url).netloc
                if d:
                    domains.add(d)
        except Exception:
            pass

    return sorted(domains)


def route_to_provider(entry: dict) -> str:
    """Smart routing: assign SKU to best provider based on task type.

    - Gemini DR: exact PN hunting, manufacturer/distributor retrieval
    - Claude Pro: brand-family batches, complex identity, long context
    - ChatGPT DR: tie-breaker, synthesis, conflict cases
    """
    identity = entry["identity_level"]
    blockers = entry["blockers"]

    # Weak identity = needs deep confirmation → Claude (long context reasoning)
    if identity == "weak" and "identity_weak" in blockers:
        # High-value weak identity → Claude for thorough analysis
        if entry["owner_price_rub"] > 50000:
            return "claude_pro"
        # Standard weak identity → Gemini for web retrieval
        return "gemini_dr"

    # Strong identity but no price → Gemini (web search for distributor pages)
    if "no_price" in blockers:
        return "gemini_dr"

    # Photo problem only → ChatGPT (image search synthesis)
    if "photo_problem" in blockers and len(blockers) == 1:
        return "chatgpt_dr"

    # Multiple blockers → Claude (complex reasoning)
    if len(blockers) >= 2:
        return "claude_pro"

    # Default fallback
    return "gemini_dr"


def build_prompt(entry: dict, provider: str) -> str:
    """Build a research prompt with search constraints and training-data JSON block."""
    pn = entry["pn"]
    brand = entry["brand"]
    name = entry["name"] or pn
    category = entry["category"] or "industrial product"

    # Header
    lines = [
        f"# Deep Research: {brand} {pn}",
        "",
        f"**Part Number:** {pn}",
        f"**Brand:** {brand}",
        f"**Product Name:** {name}",
        f"**Category:** {category}",
        f"**Owner Price (RUB):** {entry['owner_price_rub']:,.0f}" if entry["owner_price_rub"] else "",
        "",
    ]

    # Tasks
    lines.append("## Tasks")
    if "identity_weak" in entry["blockers"]:
        lines.append(f"- **IDENTITY:** Confirm this is a real {brand} product. What exactly is it?")
    if "no_price" in entry["blockers"]:
        lines.append(f"- **PRICE:** Find current market price (any currency). Check authorized distributors.")
    if "photo_problem" in entry["blockers"]:
        lines.append(f"- **PHOTO:** Find official product image URL (not a placeholder).")
    if not entry["blockers"]:
        lines.append(f"- **VERIFY:** Confirm all existing data for this product.")
    lines.append("")

    # Search constraints
    if entry["searched_domains"]:
        lines.append("## Search Constraints")
        lines.append("These domains were already searched with zero useful results — skip them:")
        for d in entry["searched_domains"]:
            lines.append(f"- {d}")
        lines.append("")

    # Provider-specific instructions
    lines.append("## Instructions")
    if provider == "gemini_dr":
        lines.append(
            f"Search for the EXACT part number \"{pn}\" from \"{brand}\". "
            "Focus on: manufacturer website, authorized distributors, industrial catalogs, "
            "PDF datasheets. Check the actual product page, not just search snippets."
        )
    elif provider == "claude_pro":
        lines.append(
            f"Analyze this product thoroughly. Part number \"{pn}\" by \"{brand}\". "
            "Consider: Is this a sub-brand (PEHA, Honeywell Security, Resideo)? "
            "What product family does it belong to? Are there related PNs? "
            "Use your knowledge of industrial catalogs and B2B distribution."
        )
    else:  # chatgpt_dr
        lines.append(
            f"Search the web comprehensively for \"{brand} {pn}\". "
            "Cross-reference multiple sources. If this product is sold under "
            "a different name or brand, find that too. Synthesize all findings."
        )
    lines.append("")

    # JSON output format
    lines.append("## Required Output")
    lines.append("Your response MUST end with this JSON block:")
    lines.append("```json")
    lines.append("{")
    lines.append('  "pn_confirmed": true/false,')
    lines.append('  "actual_brand": "Honeywell or sub-brand",')
    lines.append('  "product_name": "...",')
    lines.append('  "category": "...",')
    lines.append('  "price_per_unit": null or number,')
    lines.append('  "price_currency": "EUR/USD/GBP/RUB/...",')
    lines.append('  "price_source_url": "..." or null,')
    lines.append('  "image_url": "..." or null,')
    lines.append('  "datasheet_url": "..." or null,')
    lines.append('  "distributor_urls": ["..."],')
    lines.append('  "confidence": "high" | "medium" | "low",')
    lines.append('  "notes": "brief explanation"')
    lines.append("}")
    lines.append("```")

    return "\n".join(line for line in lines if line is not None)


def export_pilot(
    checkpoint_path: Path = _DEFAULT_CHECKPOINT,
    count: int = 25,
    output_dir: Path = _OUTPUT_DIR,
) -> dict:
    """Export pilot research prompts with smart routing.

    Creates individual markdown files per SKU under provider subdirectories.
    Returns summary dict.
    """
    checkpoint = json.loads(checkpoint_path.read_text("utf-8"))
    pilot_skus = select_pilot_skus(checkpoint, count=count)

    # Route each SKU to a provider
    assignments: dict[str, list[dict]] = {
        "gemini_dr": [],
        "claude_pro": [],
        "chatgpt_dr": [],
    }
    for entry in pilot_skus:
        provider = route_to_provider(entry)
        entry["provider"] = provider
        assignments[provider].append(entry)

    # Create directory structure
    output_dir.mkdir(parents=True, exist_ok=True)
    for provider in assignments:
        (output_dir / provider).mkdir(exist_ok=True)

    # Write individual prompt files
    for provider, entries in assignments.items():
        for entry in entries:
            pn = entry["pn"]
            safe_pn = re.sub(r'[\\/:*?"<>|]', "_", pn)
            prompt = build_prompt(entry, provider)
            (output_dir / provider / f"{safe_pn}.md").write_text(
                prompt, encoding="utf-8"
            )

    # Write manifest
    manifest = {
        "pilot_version": "v2_revenue_first",
        "total_selected": len(pilot_skus),
        "provider_counts": {p: len(entries) for p, entries in assignments.items()},
        "total_owner_price_rub": sum(e["owner_price_rub"] for e in pilot_skus),
        "blocker_distribution": {},
        "skus": [
            {
                "pn": e["pn"],
                "brand": e["brand"],
                "name": e["name"],
                "provider": e["provider"],
                "identity_level": e["identity_level"],
                "owner_price_rub": e["owner_price_rub"],
                "blockers": e["blockers"],
                "searched_domains": e["searched_domains"],
            }
            for e in pilot_skus
        ],
    }
    # Count blockers
    for e in pilot_skus:
        for b in e["blockers"]:
            manifest["blocker_distribution"][b] = (
                manifest["blocker_distribution"].get(b, 0) + 1
            )

    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "total": len(pilot_skus),
        "providers": manifest["provider_counts"],
        "total_owner_price_rub": manifest["total_owner_price_rub"],
        "blockers": manifest["blocker_distribution"],
        "output_dir": str(output_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Deep Research prompts for pilot SKUs"
    )
    parser.add_argument("--checkpoint", default=str(_DEFAULT_CHECKPOINT))
    parser.add_argument("--count", type=int, default=25)
    args = parser.parse_args()

    summary = export_pilot(Path(args.checkpoint), count=args.count)
    print(f"\n=== Deep Research Pilot Export ===")
    print(f"  Total SKUs:   {summary['total']}")
    print(f"  Providers:    {summary['providers']}")
    print(f"  Revenue pool: {summary['total_owner_price_rub']:,.0f} RUB")
    print(f"  Blockers:     {summary['blockers']}")
    print(f"  Output:       {summary['output_dir']}")


if __name__ == "__main__":
    main()

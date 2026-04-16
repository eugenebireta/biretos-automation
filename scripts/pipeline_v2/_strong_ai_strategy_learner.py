"""Strong AI (Claude Sonnet / Opus / Gemini Pro) analyzes a domain and outputs strategies.

Process:
1. Take 5-10 successful examples from a domain (brand or product type)
2. Send to strong AI with all data: PDF, evidence, sources, found EANs
3. Strong AI returns structured rules: where to find data, common pitfalls, trusted sources
4. Save to config/domain_strategies/{brand}.json
5. Cheap AI uses these rules in subsequent runs

This is one-time investment per domain → permanent knowledge.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
DS_DIR = ROOT / "downloads" / "datasheets_v2"
DS_DATA = ROOT / "downloads" / "staging" / "tier_collector_output" / "datasheet_extracted.json"
EAN_FILES = [
    ROOT / "downloads/staging/tier_collector_output/ean_focused_extraction.json",
    ROOT / "downloads/staging/tier_collector_output/ean_from_distributors.json",
    ROOT / "downloads/staging/tier_collector_output/ean_extended_search.json",
]
OUT_DIR = ROOT / "config" / "domain_strategies"
OUT_DIR.mkdir(parents=True, exist_ok=True)


STRATEGY_PROMPT = """Ты эксперт по обогащению данных каталога электротехники.
Я даю тебе примеры товаров одного бренда: {brand}, со всеми источниками данных.

Твоя задача — проанализировать паттерны и выдать СТРАТЕГИЮ для cheap AI:
1. Где для этого бренда лучше всего находить EAN, цены, фото, specs
2. Какие особенности именования PN
3. Какие сайты надёжные для этого бренда (по моим данным)
4. Частые ошибки/ловушки (например pack prices, wrong PN matches)
5. Конкретные правила валидации

Данные:
{examples}

Верни ТОЛЬКО JSON:
{{
    "brand": "{brand}",
    "pn_naming_conventions": ["pattern1", "rule2"],
    "ean_locations": {{
        "primary": "where most EANs found",
        "format": "what they look like"
    }},
    "trusted_sources": {{
        "price": ["site1.com", "site2.com"],
        "ean": ["site1.com"],
        "photo": ["site1.com"],
        "specs": ["site1.com"]
    }},
    "common_pitfalls": ["pitfall1 with example", "pitfall2"],
    "validation_rules": [
        {{"field": "price", "rule": "if >X then check pack", "reason": "..."}},
        {{"field": "pn", "rule": "...", "reason": "..."}}
    ],
    "search_query_templates": [
        "{{pn}} site:domain.com",
        "{{brand}} {{pn}} datasheet"
    ],
    "notes_for_cheap_ai": "Plain English instructions for Gemini Flash / Haiku"
}}"""


def collect_brand_examples(brand: str, max_examples: int = 8) -> list[dict]:
    """Collect successful examples for a brand."""
    json.loads(DS_DATA.read_text(encoding="utf-8")) if DS_DATA.exists() else {}

    # Load all EAN sources
    all_eans = {}
    for f in EAN_FILES:
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            for pn, d in data.items():
                ean = str(d.get("ean", ""))
                if ean.isdigit() and len(ean) == 13 and pn not in all_eans:
                    all_eans[pn] = {"ean": ean, "source": d.get("source") or d.get("domain", "")}

    examples = []
    for f in sorted(EV_DIR.glob("evidence_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        if not pn or pn.strip("-_") == "" or pn in {"---", "--", "_", "PN", "-----"}:
            continue
        si = d.get("structured_identity") or {}
        b = d.get("brand", "") or si.get("confirmed_manufacturer", "")
        sub = d.get("subbrand", "")
        real_brand = sub or b
        if real_brand.lower() != brand.lower():
            continue

        pn_safe = pn.replace("/", "_").replace(" ", "_")
        from_ds = d.get("from_datasheet", {})
        ean_info = all_eans.get(pn_safe) or all_eans.get(pn)

        if not (from_ds.get("title") or ean_info):
            continue

        # Compact example
        ex = {
            "pn": pn,
            "title": from_ds.get("title", "")[:100],
            "series": from_ds.get("series", ""),
            "ean": ean_info["ean"] if ean_info else from_ds.get("ean", ""),
            "ean_source": ean_info["source"] if ean_info else from_ds.get("ean_source", ""),
            "weight_g": from_ds.get("weight_g", ""),
            "dimensions_mm": from_ds.get("dimensions_mm", ""),
            "specs_count": from_ds.get("specs_count", 0),
            "datasheet_size_kb": from_ds.get("datasheet_size_kb", 0),
            "norm_price": (d.get("normalized") or {}).get("best_price"),
            "norm_price_source": (d.get("normalized") or {}).get("best_price_source", ""),
            "training_url_domains": list(set(
                u.get("url", "").split("/")[2].replace("www.", "") if isinstance(u, dict) and "://" in u.get("url", "")
                else (u.split("/")[2].replace("www.", "") if isinstance(u, str) and "://" in u else "")
                for u in (d.get("training_urls") or [])[:10]
            ))[:8],
        }
        examples.append(ex)
        if len(examples) >= max_examples:
            break

    return examples


def analyze_brand_with_claude(brand: str):
    """Use Claude Sonnet (strong) to analyze brand strategy."""
    from scripts.app_secrets import get_secret
    import anthropic

    examples = collect_brand_examples(brand)
    if len(examples) < 3:
        return {"error": f"Not enough examples for {brand} ({len(examples)})"}

    examples_str = json.dumps(examples, indent=2, ensure_ascii=False)
    prompt = STRATEGY_PROMPT.format(brand=brand, examples=examples_str)

    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model="claude-sonnet-4-5",  # strong model
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    if "```" in text:
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"): text = text[4:]
    text = text.strip()

    try:
        strategy = json.loads(text)
    except Exception as e:
        return {"error": f"JSON parse failed: {e}", "raw": text[:500]}

    # Add metadata
    strategy["_meta"] = {
        "examples_analyzed": len(examples),
        "model": "claude-sonnet-4-5",
        "tokens_in": response.usage.input_tokens,
        "tokens_out": response.usage.output_tokens,
        "cost_usd": round((response.usage.input_tokens * 3.00 + response.usage.output_tokens * 15.00) / 1_000_000, 4),
    }

    out_file = OUT_DIR / f"{brand.lower().replace(' ', '_')}.json"
    out_file.write_text(json.dumps(strategy, indent=2, ensure_ascii=False), encoding="utf-8")
    return strategy


def main():
    # Analyze top brands by SKU count
    brands = ["PEHA", "Honeywell", "Esser", "DKC", "Howard Leight", "Phoenix Contact", "ABB", "Weidmuller"]

    print("=" * 80)
    print("Strong AI domain strategy learner (Claude Sonnet 4.5)")
    print("=" * 80)

    total_cost = 0
    for brand in brands:
        print(f"\n  Analyzing {brand}...")
        result = analyze_brand_with_claude(brand)
        if "error" in result:
            print(f"    SKIP: {result['error']}")
            continue
        meta = result.get("_meta", {})
        cost = meta.get("cost_usd", 0)
        total_cost += cost
        n_examples = meta.get("examples_analyzed", 0)
        rules = len(result.get("validation_rules", []))
        sources = sum(len(s) for s in result.get("trusted_sources", {}).values())
        print(f"    OK: {n_examples} examples → {rules} rules, {sources} trusted sources, ${cost}")

    print(f"\nTotal cost: ${total_cost:.4f}")
    print(f"Strategies saved: {OUT_DIR}")


if __name__ == "__main__":
    main()

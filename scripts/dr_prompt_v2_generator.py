"""dr_prompt_v2_generator.py — Generate v2 Deep Research prompts.

Incorporates critique feedback:
- "Gray Market Analyst" role instead of formal procurement
- Alias/alternative PN searching
- Surplus dealer sources (eBay, Radwell, IndiaMart, etc.)
- Batches of 30-50 SKUs (not 210 at once)
- Market/Surplus price labeling
- ASCII-only output

Usage:
    python scripts/dr_prompt_v2_generator.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BATCHES_PATH = ROOT / "research_queue" / "dr_prompts" / "v2_batches.json"
OUTPUT_DIR = ROOT / "research_queue" / "dr_prompts" / "v2"

ROLE_BLOCK = """\
You are a Senior Procurement Intelligence Analyst specializing in Gray Market \
and Industrial Surplus sourcing. Your expertise is finding real, purchasable \
prices for obscure industrial part numbers that normal search engines miss.

You know that:
- Many Honeywell PNs have ALIASES: sub-brands (PEHA, Resideo, Notifier, \
Esser, Saia Burgess, Morley-IAS), OEM codes, replacement codes (suffix -N, -U)
- Regional suffixes exist: -RU (Russia), -L3 (kit), .10/.20 (color variants)
- A PN like PANC300-03 might be listed as 8C-PCNT03 or Notifier PANC300-03
- Some PNs are internal Honeywell catalog codes that map to different public PNs

Your job is NOT to verify official channels -- it is to FIND ANY real price \
from ANY source, including gray market, surplus, and secondary dealers.\
"""

SEARCH_INSTRUCTIONS = """\
## Search Strategy (MANDATORY for each PN)

For EACH part number, you MUST try ALL of these approaches before reporting \
"not found":

1. **Exact PN search**: "{pn}" in quotes
2. **Brand + PN**: "Honeywell {pn}", "Resideo {pn}", "Notifier {pn}"
3. **Alias hunting**: Search for the PN without prefix/suffix, with common \
alternatives (drop -RU, drop .10, try adding -N or -U)
4. **Datasheet mining**: "{pn} datasheet PDF" -- datasheets often list \
distributor PNs or ordering codes
5. **Surplus/gray market**: Search specifically on these platforms:
   - eBay (ebay.com, ebay.co.uk, ebay.de)
   - Radwell International (radwell.com)
   - IndiaMart (indiamart.com)
   - NSE Automation (nseautomation.com)
   - Classic Automation (classicautomation.com)
   - Alibaba / AliExpress
   - EU Automation (euautomation.com)
   - TradeMachines / Machinio

Do NOT skip surplus sources. A surplus price of $200 for a $5000 item is \
still valuable data -- label it as "surplus" in the Price_Type column.\
"""


def build_v2_prompt(batch: list[tuple[str, str]], batch_num: int, total_batches: int, platform: str) -> str:
    """Build a v2 DR prompt for a batch of SKUs."""
    lines = []

    # Role
    lines.append(ROLE_BLOCK)
    lines.append("")

    # Task
    lines.append(f"## Task: Find market prices for {len(batch)} industrial part numbers")
    lines.append(f"(Batch {batch_num} of {total_batches} -- {len(batch)} SKUs)")
    lines.append("")

    lines.append(SEARCH_INSTRUCTIONS.format(pn="{PN}"))
    lines.append("")

    # SKU table
    lines.append("## Part Numbers to Research")
    lines.append("")
    lines.append("| # | PN | Brand |")
    lines.append("|---|-----|-------|")
    for i, (pn, brand) in enumerate(batch, 1):
        lines.append(f"| {i} | {pn} | {brand} |")
    lines.append("")

    # Output format
    lines.append("## Required Output Format")
    lines.append("")

    if platform == "chatgpt":
        lines.append("Return results as a JSON array:")
        lines.append("```json")
        lines.append("[")
        lines.append("  {")
        lines.append('    "pn": "EXACT_PN_FROM_TABLE",')
        lines.append('    "price": 123.45,')
        lines.append('    "currency": "EUR",')
        lines.append('    "price_type": "distributor" | "surplus" | "gray_market" | "list_price",')
        lines.append('    "source_url": "https://...",')
        lines.append('    "category": "short product description",')
        lines.append('    "image_url": "https://..." or null,')
        lines.append('    "alias_found": "alternative PN if different from original" or null,')
        lines.append('    "notes": "brief context"')
        lines.append("  }")
        lines.append("]")
        lines.append("```")
    else:
        lines.append("Return a markdown table with these columns:")
        lines.append("")
        lines.append("| # | PN | Price | Currency | Price_Type | Source URL | Category | Image URL | Alias | Notes |")
        lines.append("|---|-----|-------|----------|-----------|-----------|----------|-----------|-------|-------|")
        lines.append("")
        lines.append("Price_Type values: distributor, surplus, gray_market, list_price")

    lines.append("")
    lines.append("## Critical Rules")
    lines.append("")
    lines.append("- If you cannot find a price after ALL 5 search approaches, write price=null")
    lines.append("- NEVER invent or guess prices -- only report what you actually find on a webpage")
    lines.append("- Include the ACTUAL source URL where the price is visible")
    lines.append("- Surplus/gray market prices are WELCOME -- just label them correctly")
    lines.append("- If you find the product under a DIFFERENT part number (alias), report both")
    lines.append("- Prices in ANY currency are accepted (EUR, USD, GBP, CHF, DKK, RUB, INR, CNY)")
    lines.append("- Include VAT/tax status in notes if visible (e.g., 'excl. VAT', 'incl. 19% VAT')")
    lines.append(f"- Report ALL {len(batch)} PNs even if price=null")

    return "\n".join(lines)


def main():
    batches = json.loads(BATCHES_PATH.read_text("utf-8"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for platform in ("chatgpt", "gemini"):
        for i, batch in enumerate(batches):
            batch_num = i + 1
            prompt = build_v2_prompt(batch, batch_num, len(batches), platform)
            filename = f"{platform}_batch{batch_num}_{len(batch)}skus.txt"
            out_path = OUTPUT_DIR / filename
            out_path.write_text(prompt, encoding="utf-8")
            print(f"  {filename} ({len(prompt):,} chars)")

    print(f"\nGenerated {len(batches) * 2} prompt files in {OUTPUT_DIR}")
    print(f"Workflow: copy-paste each file into the DR web UI")
    print(f"  ChatGPT: chatgpt_batch1_40skus.txt -> chatgpt_batch5_28skus.txt")
    print(f"  Gemini:  gemini_batch1_40skus.txt  -> gemini_batch5_28skus.txt")


if __name__ == "__main__":
    main()

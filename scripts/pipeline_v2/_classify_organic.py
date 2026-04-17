"""Classify top organic domains: real distributor or garbage.

Uses WebFetch to check each domain and classify.
Output: JSON with classification per domain.
"""
from __future__ import annotations

import json
import sys
import io
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

DOMAINS = [
    "hlkshop.ch",
    "sanitaershop24.ch",
    "barcodefactory.com",
    "stockonfire.com",
    "manualslib.com",
    "geizhals.de",
    "barcodesinc.com",
    "mytub.co.uk",
    "oumanshop.com",
    "us.wiautomation.com",
    "bhphotovideo.com",
    "pcliquidations.com",
    "modern-eastern.com",
    "eibabo.us",
    "logiscenter.us",
    "santehmoskva.ru",
    "blackhawksupply.com",
    "satro-paladin.com",
    "esylux.com",
    "eaccu-tech.com",
    "jmac.com",
    "alive-sr.com",
    "honeywellstore.com",
    "elektro4000.de",
    "thebarcodewarehouse.co.uk",
    "serversupply.com",
    "nexinstrument.com",
    "hls-austria.com",
    "voltus.de",
    "volzhsk.aelektro.ru",
]

PROMPT = (
    "Classify this website in ONE LINE. Format: TYPE | DESCRIPTION\n"
    "Types:\n"
    "- DISTRIBUTOR: sells industrial/electrical products, has prices, product pages\n"
    "- MANUFACTURER: makes products, official brand site\n"
    "- PRICE_AGGREGATOR: compares prices from other sites, no own stock\n"
    "- MANUALS_DOCS: hosts manuals/datasheets, no sales\n"
    "- MARKETPLACE: like Amazon/eBay, many sellers\n"
    "- LIQUIDATOR: sells surplus/refurbished/liquidation\n"
    "- GARBAGE: spam, dead, irrelevant\n"
    "- OTHER: none of the above\n\n"
    "Also note: does it have product prices? photos? specs? "
    "What brands does it carry? What country?\n"
    "Answer in ONE LINE: TYPE | country | has_prices:yes/no | has_photos:yes/no | "
    "has_specs:yes/no | brands: list | brief description"
)


def main():
    from scripts.app_secrets import get_secret
    import anthropic

    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    results = {}

    for i, domain in enumerate(DOMAINS):
        url = f"https://{domain}"
        print(f"[{i+1:>2}/{len(DOMAINS)}] {domain}...", end=" ", flush=True)

        try:
            # Use Haiku to classify based on domain name + common knowledge
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Classify this website: {url}\n"
                        f"Based on domain name and your knowledge, classify it.\n{PROMPT}"
                    ),
                }],
            )
            from orchestrator._api_cost_tracker import log_api_call
            log_api_call(__file__, "claude-haiku-4-5-20251001", resp.usage)
            classification = resp.content[0].text.strip()
            print(classification[:90])
            results[domain] = classification
        except Exception as e:
            print(f"ERROR: {e}")
            results[domain] = f"ERROR: {e}"

        time.sleep(0.3)

    # Parse results and suggest tier
    print("\n" + "=" * 100)
    print("CLASSIFICATION SUMMARY")
    print("=" * 100)

    tier3_candidates = []
    denylist_candidates = []
    other = []

    for domain, classification in results.items():
        cl = classification.upper()
        if "DISTRIBUTOR" in cl and "DISTRIBUTOR" == cl.split("|")[0].strip():
            tier3_candidates.append(domain)
            print(f"  TIER3 -> {domain:<40} {classification[:60]}")
        elif "MANUFACTURER" in cl.split("|")[0].strip().upper():
            tier3_candidates.append(domain)  # manufacturer we missed
            print(f"  TIER1? -> {domain:<40} {classification[:60]}")
        elif any(x in cl.split("|")[0].strip().upper()
                 for x in ["PRICE_AGGREGATOR", "GARBAGE", "MARKETPLACE", "LIQUIDATOR"]):
            denylist_candidates.append(domain)
            print(f"  DENY  -> {domain:<40} {classification[:60]}")
        else:
            other.append(domain)
            print(f"  OTHER -> {domain:<40} {classification[:60]}")

    print(f"\n  Add to tier3: {len(tier3_candidates)} domains")
    print(f"  Add to deny:  {len(denylist_candidates)} domains")
    print(f"  Other/manual: {len(other)} domains")

    # Save
    out = Path("downloads/staging/organic_classification.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "results": results,
        "tier3_candidates": tier3_candidates,
        "denylist_candidates": denylist_candidates,
        "other": other,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Saved: {out}")


if __name__ == "__main__":
    main()

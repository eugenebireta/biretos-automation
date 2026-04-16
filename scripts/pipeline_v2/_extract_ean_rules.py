"""Use Claude Sonnet 4.5 to discover EAN construction rules per brand.

Sends Claude all known EAN-PN pairs for each brand and asks:
- What is the formula to construct EAN from PN?
- Which products fit the rule, which are exceptions?

Returns Python predicate functions that can predict EANs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
OUT_FILE = ROOT / "config" / "ean_construction_rules.json"


PROMPT = """Find the EAN-13 construction rule from these PN→EAN pairs for brand {brand}:

{pairs}

EAN-13 has format: 7-digit company prefix + 5-digit product code + 1 check digit.

Tasks:
1. Identify the company prefix (first 7 digits)
2. Find the formula: how does the 5-digit product code derive from PN?
   Common patterns: first_5_of_PN, last_5_of_PN, PN_padded_to_5, custom_mapping
3. List exceptions (PNs that don't fit the rule)
4. Verify checksum (each EAN should have valid EAN-13 check digit)

Return ONLY a JSON object:
{{
    "brand": "{brand}",
    "company_prefixes": ["7312550", "7312553"],
    "rule_description": "Plain English",
    "python_formula": "PN_TO_PRODUCT_CODE: lambda pn: pn[-5:].zfill(5)",
    "fits_pattern": ["PN1", "PN2"],
    "exceptions": [{{"pn": "X", "ean": "Y", "reason": "why doesn't fit"}}],
    "confidence": "high|medium|low",
    "applicable_to": "Which PN patterns this rule applies to (e.g. 'numeric 7-digit PNs')"
}}"""


def main():
    from scripts.app_secrets import get_secret
    import anthropic

    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    # Collect all known EANs per brand from evidence (excluding predicted ones)
    brand_pairs = defaultdict(list)
    for f in sorted(EV_DIR.glob("evidence_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        if not pn or pn.strip("-_") == "" or pn in {"---", "--", "_", "PN", "-----"}:
            continue
        si = d.get("structured_identity") or {}
        sub = d.get("subbrand", "")
        brand = sub or d.get("brand", "") or si.get("confirmed_manufacturer", "")
        if not brand:
            continue
        from_ds = d.get("from_datasheet", {})
        ean = from_ds.get("ean", "")
        # Skip predicted/rule-based EANs
        if from_ds.get("ean_source") in ("peha_rule_predicted",):
            continue
        if str(ean).isdigit() and len(str(ean)) == 13:
            brand_pairs[brand].append({"pn": pn, "ean": str(ean)})

    print("=" * 80)
    print("EAN Rule Discovery (Claude Sonnet 4.5)")
    print("=" * 80)

    rules = {}
    total_cost = 0

    for brand, pairs in sorted(brand_pairs.items(), key=lambda x: -len(x[1])):
        if len(pairs) < 2:
            print(f"\n  {brand}: only {len(pairs)} pairs — skip")
            continue

        print(f"\n  {brand}: {len(pairs)} pairs")
        pairs_str = "\n".join(f"  PN={p['pn']:<20}  EAN={p['ean']}" for p in pairs)

        prompt = PROMPT.format(brand=brand, pairs=pairs_str)
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            if "```" in text:
                parts = text.split("```")
                text = parts[1] if len(parts) > 1 else text
                if text.startswith("json"): text = text[4:]
            text = text.strip()

            try:
                rule = json.loads(text)
                rules[brand] = rule
                cost = (response.usage.input_tokens * 3.00 + response.usage.output_tokens * 15.00) / 1_000_000
                total_cost += cost
                conf = rule.get("confidence", "?")
                fits = len(rule.get("fits_pattern", []))
                excs = len(rule.get("exceptions", []))
                print(f"    Confidence: {conf}, fits: {fits}, exceptions: {excs}, cost: ${cost:.4f}")
                print(f"    Rule: {rule.get('rule_description', '')[:100]}")
            except Exception:
                rules[brand] = {"error": "json_parse", "raw": text[:500]}
                print("    PARSE ERROR")

        except Exception as e:
            rules[brand] = {"error": str(e)[:200]}
            print(f"    ERROR: {str(e)[:60]}")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nTotal cost: ${total_cost:.4f}")
    print(f"Rules saved: {OUT_FILE}")


if __name__ == "__main__":
    main()

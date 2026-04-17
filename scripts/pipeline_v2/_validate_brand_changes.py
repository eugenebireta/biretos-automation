"""Critical re-validation of auto-fix brand changes.

Previous auto-fix trusted single-pass Sonnet decisions without evidence check.
Result: FX808313 -> OBO Bettermann (wrong, FX is Esser/Honeywell series),
3240197 -> OBO Bettermann (conflicts with sibling 3240199 -> PEHA), etc.

This script:
1. Reads auto_fix_log.jsonl for all applied brand changes
2. For each, loads FULL evidence (datasheet title, seed name, DR results, domains seen)
3. Asks Sonnet with explicit instruction: validate with evidence, be critical
4. Classifies: keep_new / revert_to_old / propose_different_brand
5. Applies verdicts to evidence files + writes validation_log.jsonl
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
LOG_FILE = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "auto_fix_log.jsonl"
OUT_FILE = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "brand_validation_log.jsonl"


VALIDATE_PROMPT = """You are a catalog QA auditor. A previous automated pass changed this product's brand.
Your job: VALIDATE whether the change is correct, using evidence. Be critical — the previous pass made many mistakes.

ORIGINAL: brand was "{old_brand}"
CHANGED TO: brand is now "{new_brand}"

EVIDENCE FOR THIS SKU:
{evidence}

SIBLING PNs in same series (for cross-check):
{siblings}

Known brand-PN patterns:
- FX***** series = Esser (Honeywell Fire Safety)
- 3240*** and similar 6-digit = PEHA (Honeywell PEHA line)
- 2904*** = Phoenix Contact
- PCD*.* = Saia-Burgess (now Honeywell but brand is still Saia-Burgess)
- HVAC**C5 = Honeywell HVAC controller series
- NE-*** = NEC
- EVCS-* = Honeywell Notifier
- P2***, U2*** monitor codes = Dell or HP
- Howard Leight/Sperian = Honeywell safety brands (keep subbrand)

Return ONLY JSON:
{{
  "verdict": "keep_new" | "revert_to_old" | "different_brand",
  "final_brand": "correct brand name",
  "confidence": "high" | "medium" | "low",
  "reasoning": "one sentence citing specific evidence",
  "red_flags": ["list any concerns about the change"]
}}

BE CRITICAL. If evidence is insufficient, vote revert_to_old."""


def load_brand_changes():
    lines = LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
    changes = []
    for line in lines:
        d = json.loads(line)
        if d.get("action") == "update_brand" and d.get("applied"):
            changes.append(d)
    return changes


def build_evidence_for_sku(pn: str) -> tuple[dict, list[str]]:
    """Return (evidence dict, list of sibling PNs)."""
    ev_file = EV_DIR / f"evidence_{pn}.json"
    if not ev_file.exists():
        return None, []

    d = json.loads(ev_file.read_text(encoding="utf-8"))
    fd = d.get("from_datasheet", {})
    si = d.get("structured_identity", {})
    norm = d.get("normalized", {})
    content = d.get("content", {})

    evidence = {
        "pn": pn,
        "current_brand": d.get("brand"),
        "current_subbrand": d.get("subbrand"),
        "seed_name_from_excel": content.get("seed_name", "") or d.get("name", ""),
        "title_from_datasheet": fd.get("title", ""),
        "datasheet_url": (d.get("documents") or {}).get("datasheet", {}).get("url", ""),
        "series": fd.get("series", ""),
        "product_type_hint": si.get("product_type", ""),
        "dr_brand_confirmed": si.get("confirmed_manufacturer", ""),
        "dr_brand_source": si.get("brand_source", ""),
        "best_description_sample": (norm.get("best_description") or "")[:300],
        "best_price": norm.get("best_price"),
        "best_price_currency": norm.get("best_price_currency"),
        "ean": fd.get("ean", ""),
    }

    # Find siblings: same 6-digit prefix or FX prefix etc.
    prefix = ""
    if pn.startswith("FX"):
        prefix = "FX"
    elif len(pn) >= 4 and pn[:4].isdigit():
        prefix = pn[:4]
    elif pn.startswith("3240"):
        prefix = "3240"
    elif pn.startswith("HVAC"):
        prefix = "HVAC"

    siblings = []
    if prefix:
        for f in EV_DIR.glob(f"evidence_{prefix}*.json"):
            sib_pn = f.stem.replace("evidence_", "")
            if sib_pn == pn:
                continue
            try:
                sib = json.loads(f.read_text(encoding="utf-8"))
                siblings.append(f"  {sib_pn}: brand={sib.get('brand')} | subbrand={sib.get('subbrand')} | title={sib.get('from_datasheet', {}).get('title', '')[:80]}")
            except Exception:
                pass
            if len(siblings) >= 5:
                break

    return evidence, siblings


def validate_via_sonnet(client, change: dict, evidence: dict, siblings: list[str]) -> dict:
    prompt = VALIDATE_PROMPT.format(
        old_brand=change["old_brand"],
        new_brand=change["new_brand"],
        evidence=json.dumps(evidence, indent=2, ensure_ascii=False),
        siblings="\n".join(siblings) if siblings else "  (none)",
    )

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    if "```" in text:
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    try:
        result = json.loads(text)
    except Exception:
        return {"error": "parse_failed", "raw": text[:500]}

    cost = (response.usage.input_tokens * 3.00 + response.usage.output_tokens * 15.00) / 1_000_000
    result["_cost_usd"] = round(cost, 5)
    return result


def apply_verdict(pn: str, verdict: dict, change: dict):
    """Update evidence file based on verdict."""
    ev_file = EV_DIR / f"evidence_{pn}.json"
    if not ev_file.exists():
        return False

    d = json.loads(ev_file.read_text(encoding="utf-8"))

    if verdict["verdict"] == "revert_to_old":
        d["brand"] = change["old_brand"]
        d["subbrand"] = ""
    elif verdict["verdict"] == "different_brand":
        d["brand"] = verdict["final_brand"]
        d["subbrand"] = ""
    # keep_new: no change needed

    # Record validation metadata
    d.setdefault("_brand_validation", {})
    d["_brand_validation"] = {
        "validator": "sonnet_4_5",
        "verdict": verdict["verdict"],
        "final_brand": verdict.get("final_brand"),
        "confidence": verdict.get("confidence"),
        "original_auto_fix_new_brand": change["new_brand"],
    }

    ev_file.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def main():
    from scripts.app_secrets import get_secret
    import anthropic

    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    changes = load_brand_changes()
    print(f"Validating {len(changes)} brand changes via Sonnet")
    print("=" * 90)

    total_cost = 0
    stats = {"keep_new": 0, "revert_to_old": 0, "different_brand": 0, "error": 0}

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as log_f:
        for idx, change in enumerate(changes, 1):
            pn = change["pn"]
            evidence, siblings = build_evidence_for_sku(pn)
            if not evidence:
                print(f"  [{idx}/{len(changes)}] {pn}: no evidence file, skip")
                continue

            print(f"  [{idx}/{len(changes)}] {pn}: {change['old_brand']} -> {change['new_brand']} ... ", end="", flush=True)

            verdict = validate_via_sonnet(client, change, evidence, siblings)
            if "error" in verdict:
                print(f"ERROR: {verdict['error']}")
                stats["error"] += 1
                continue

            total_cost += verdict.get("_cost_usd", 0)
            stats[verdict["verdict"]] = stats.get(verdict["verdict"], 0) + 1

            print(f"{verdict['verdict']} -> {verdict.get('final_brand')} ({verdict.get('confidence')})")

            apply_verdict(pn, verdict, change)
            log_entry = {"pn": pn, "change": change, "verdict": verdict}
            log_f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            log_f.flush()

    print("=" * 90)
    print(f"Verdicts: {stats}")
    print(f"Total cost: ${total_cost:.4f}")
    print(f"Log: {OUT_FILE}")


if __name__ == "__main__":
    main()

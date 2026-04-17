"""Auto-fix issues found by Sonnet quality check.

For each SKU with verdict=NEEDS_FIX or REJECT:
- Brand mismatch → ask Sonnet "what's the correct brand?" → update evidence
- Wrong datasheet → mark for re-download
- Data contamination → move to review_bucket

Writes corrections to evidence, logs all changes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.pipeline_v2.t1_brand_guard import should_skip_brand_autofix

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
QC_FILE = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "quality_check.json"
FIX_LOG = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "auto_fix_log.jsonl"


FIX_PROMPT = """You are a product data corrector. A previous audit found issues with this product record.

Product data:
{data}

Issues found:
{issues}

Your task: Determine the CORRECT values. Return ONLY JSON:
{{
  "correct_brand": "<real brand, e.g. Dell, ABB, Honeywell>",
  "correct_product_type": "<what this product actually is>",
  "correct_pn": "<if PN was wrong, the correct one>",
  "confidence": "high|medium|low",
  "action": "update_brand|remove_bad_datasheet|needs_new_datasheet|mark_as_wrong|no_fix_possible",
  "reasoning": "brief explanation"
}}

Use common sense: if PN format is 2CDG110146R0011 → ABB; if title says 'Dell 24 Monitor' → Dell.
PEHA PNs are 6-8 digit numeric. Honeywell's are diverse.
P2421D is a Dell monitor, not Honeywell.
SK8115 is Honeywell docking station."""


def main():
    from scripts.app_secrets import get_secret
    import anthropic

    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    qc = json.loads(QC_FILE.read_text(encoding="utf-8"))

    fixes = []
    stats = {"brand_fixed": 0, "marked_wrong": 0, "needs_new_datasheet": 0,
             "no_fix": 0, "errors": 0}
    total_cost = 0

    problem_skus = [(pn, r) for pn, r in qc.items()
                     if r.get("overall_verdict", "").upper() in ("REJECT", "NEEDS_FIX")]

    print(f"Auto-fix: processing {len(problem_skus)} problematic SKUs")
    print("=" * 90)

    for idx, (pn, r) in enumerate(problem_skus):
        # Load evidence
        ev_file = EV_DIR / f"evidence_{pn}.json"
        if not ev_file.exists():
            ev_file = EV_DIR / f"evidence_{pn.replace('_','/')}.json"
        if not ev_file.exists():
            continue

        d = json.loads(ev_file.read_text(encoding="utf-8"))
        fd = d.get("from_datasheet", {})

        data = {
            "pn": pn,
            "current_brand": d.get("brand", ""),
            "seed_name": (d.get("content") or {}).get("seed_name", "") or d.get("name", ""),
            "title_from_datasheet": fd.get("title", ""),
            "datasheet_pdf": fd.get("datasheet_pdf", ""),
        }

        issues_str = "\n".join(f"- {i}" for i in r.get("issues", [])[:5])

        print(f"  [{idx+1}/{len(problem_skus)}] {pn:<22}... ", end="", flush=True)

        try:
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=600,
                messages=[{"role": "user", "content": FIX_PROMPT.format(data=json.dumps(data, indent=2, ensure_ascii=False), issues=issues_str)}],
            )
            text = response.content[0].text.strip()
            if "```" in text:
                parts = text.split("```")
                text = parts[1] if len(parts) > 1 else text
                if text.startswith("json"): text = text[4:]
            text = text.strip()
            fix = json.loads(text)

            cost = (response.usage.input_tokens * 3.00 + response.usage.output_tokens * 15.00) / 1_000_000
            total_cost += cost

            action = fix.get("action", "")
            correct_brand = fix.get("correct_brand", "").strip()
            current_brand = data["current_brand"]

            # Apply fix
            applied = False
            # T1 Sync Guard (hotfix 2026-04-17): LLM brand proposals are rejected
            # for SKUs with structured_identity.confirmed_manufacturer populated.
            # Empirically, 19/19 prior wrong corrections were on such SKUs.
            if action == "update_brand":
                skip, skip_reason = should_skip_brand_autofix(d)
                if skip:
                    stats["no_fix"] += 1
                    print(f"T1_GUARD_SKIP: {skip_reason}")
                    # Log that we blocked the proposal for audit trail
                    fix_record = {
                        "pn": pn, "timestamp": datetime.now(timezone.utc).isoformat(),
                        "action": "update_brand", "applied": False,
                        "blocked_by": "t1_brand_guard",
                        "old_brand": current_brand,
                        "proposed_new_brand": correct_brand,
                        "reasoning": fix.get("reasoning", ""),
                        "confidence": fix.get("confidence", ""),
                        "guard_reason": skip_reason,
                        "cost_usd": round(cost, 5),
                    }
                    with open(FIX_LOG, "a", encoding="utf-8") as lf:
                        lf.write(json.dumps(fix_record, ensure_ascii=False) + "\n")
                    continue

            if action == "update_brand" and correct_brand and correct_brand != current_brand:
                # Save old brand + update
                fd_old = fd.get("_corrections", {})
                fd_old["original_brand"] = current_brand
                fd_old["brand_correction_reason"] = fix.get("reasoning", "")
                fd_old["brand_correction_confidence"] = fix.get("confidence", "")
                fd["_corrections"] = fd_old
                d["brand"] = correct_brand
                d["from_datasheet"] = fd
                ev_file.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
                stats["brand_fixed"] += 1
                applied = True
                print(f"BRAND: {current_brand} → {correct_brand}")
            elif action == "mark_as_wrong":
                fd["_corrections"] = fd.get("_corrections", {})
                fd["_corrections"]["marked_wrong"] = True
                fd["_corrections"]["reason"] = fix.get("reasoning", "")
                d["from_datasheet"] = fd
                ev_file.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
                stats["marked_wrong"] += 1
                applied = True
                print(f"MARKED WRONG: {fix.get('reasoning','')[:50]}")
            elif action == "needs_new_datasheet":
                fd["_corrections"] = fd.get("_corrections", {})
                fd["_corrections"]["needs_new_datasheet"] = True
                fd["_corrections"]["reason"] = fix.get("reasoning", "")
                d["from_datasheet"] = fd
                ev_file.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
                stats["needs_new_datasheet"] += 1
                applied = True
                print(f"NEEDS_NEW_PDF: {fix.get('reasoning','')[:50]}")
            else:
                stats["no_fix"] += 1
                print(f"no_fix ({action})")

            # Log
            fixes.append({
                "pn": pn, "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": action, "applied": applied,
                "old_brand": current_brand, "new_brand": correct_brand,
                "reasoning": fix.get("reasoning", ""),
                "confidence": fix.get("confidence", ""),
                "cost_usd": round(cost, 5),
            })

        except Exception as e:
            stats["errors"] += 1
            print(f"ERROR: {str(e)[:60]}")

    # Write log
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(FIX_LOG, "a", encoding="utf-8") as f:
        for r in fixes:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print()
    print("=" * 90)
    print("Fixes applied:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"Total cost: ${total_cost:.4f}")
    print(f"Log: {FIX_LOG}")


if __name__ == "__main__":
    main()

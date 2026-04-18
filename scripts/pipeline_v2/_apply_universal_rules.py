"""Apply universal rules engine to all 370 SKUs. No AI calls.

For each SKU:
- Detect brand from PN pattern
- Predict EAN if brand has formula
- Check red flags
- Write results to evidence as 'universal_rules_check' block
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"

from scripts.pipeline_v2.universal_rules_engine import (
    detect_brand_from_pn, predict_ean, check_red_flags, validate_ean13
)


def main():
    now = datetime.now(timezone.utc).isoformat()

    stats = {
        "processed": 0,
        "brand_detected": 0,
        "brand_mismatch": 0,
        "ean_predicted": 0,
        "ean_applied_new": 0,
        "red_flags_total": 0,
    }

    for f in sorted(EV_DIR.glob("evidence_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        if not pn or pn.strip("-_") == "" or pn in {"---", "--", "_", "PN", "-----"}:
            continue
        stats["processed"] += 1

        si = d.get("structured_identity") or {}
        sub = d.get("subbrand", "")
        brand = sub or d.get("brand", "") or si.get("confirmed_manufacturer", "")
        fd = d.get("from_datasheet", {})

        # Brand detection from PN
        detected = detect_brand_from_pn(pn)
        if detected:
            stats["brand_detected"] += 1

        # Red flags
        record = {
            "pn": pn,
            "brand": brand,
            "ean": fd.get("ean", ""),
            "datasheet_title": fd.get("title", ""),
            "seed_name": (d.get("content") or {}).get("seed_name", "") or d.get("name", ""),
            "specs_count": len(fd.get("specs", {})) if isinstance(fd.get("specs"), dict) else 0,
            "datasheet_size_kb": fd.get("datasheet_size_kb", 0),
        }
        flags = check_red_flags(record)
        stats["red_flags_total"] += len(flags)

        if any(fl["rule"] == "brand_mismatch" for fl in flags):
            stats["brand_mismatch"] += 1

        # Predict EAN if brand matches rule
        predicted = None
        predict_brand = detected["brand"] if detected and detected.get("brand") and not detected.get("needs_disambiguation") else brand
        predicted = predict_ean(pn, predict_brand)
        if predicted:
            stats["ean_predicted"] += 1
            # Only apply if no EAN yet
            if not fd.get("ean") and predicted.get("ean") and validate_ean13(predicted["ean"]):
                fd["ean"] = predicted["ean"]
                fd["ean_source"] = predicted.get("source", "rule_predicted")
                fd["ean_confidence"] = predicted.get("confidence", "")
                fd["ean_tier"] = 1  # brand rule = tier1
                stats["ean_applied_new"] += 1

        # Save universal_rules block
        d["universal_rules_check"] = {
            "checked_at": now,
            "detected_brand": detected,
            "red_flags": flags,
            "predicted_ean": predicted,
        }
        d["from_datasheet"] = fd
        f.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 70)
    print("Universal Rules Check Complete")
    print("=" * 70)
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

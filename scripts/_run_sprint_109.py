"""One-shot script: run Gemini sprint for 109 remaining weak SKUs."""
from __future__ import annotations
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from identity_checker import check_identity_via_gemini

CP_PATH = Path(__file__).parent.parent / "downloads" / "checkpoint.json"
SPRINT_DIR = Path(__file__).parent.parent / "research_results" / "identity_sprint"
SPRINT_DIR.mkdir(exist_ok=True)

cp = json.loads(CP_PATH.read_text("utf-8"))

sprinted_pns: set[str] = set()
for f in SPRINT_DIR.glob("*_identity.json"):
    try:
        d = json.loads(f.read_text("utf-8"))
        if d.get("pn"):
            sprinted_pns.add(d["pn"])
    except Exception:
        pass

cohort = [
    (pn, cp[pn].get("brand", "Honeywell"))
    for pn in cp
    if cp[pn].get("policy_decision_v2", {}).get("identity_level") == "weak"
    and pn not in sprinted_pns
]

print(f"Starting Gemini sprint for {len(cohort)} SKUs (~${len(cohort)*0.003:.2f})...")

confirmed = 0
not_found = 0
errors = 0
total_cost = 0.0

for i, (pn, brand) in enumerate(cohort):
    safe_pn = pn.replace("/", "_").replace("\\", "_")
    out_path = SPRINT_DIR / f"{safe_pn}_identity.json"

    try:
        artifact = check_identity_via_gemini(pn, brand)
        ia_dict = dataclasses.asdict(artifact)
        ia_dict["pn"] = pn  # Ensure original PN stored
        out_path.write_text(json.dumps(ia_dict, ensure_ascii=False, indent=2), encoding="utf-8")
        total_cost += 0.003

        if artifact.accept_for_pipeline:
            confirmed += 1
            label = "CONFIRMED"
        else:
            not_found += 1
            label = artifact.identity_status or "not_found"

        print(f"[{i+1}/{len(cohort)}] {pn}: {label}")
    except Exception as exc:
        errors += 1
        print(f"[{i+1}/{len(cohort)}] {pn}: ERROR - {exc}")
        out_path.write_text(
            json.dumps({
                "pn": pn, "brand": brand, "identity_status": "error",
                "error": str(exc), "accept_for_pipeline": False,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

print()
print(f"Sprint complete: {len(cohort)} total")
print(f"  Confirmed (accepted): {confirmed}")
print(f"  Not found / other:    {not_found}")
print(f"  Errors:               {errors}")
print(f"  Estimated cost:       ${total_cost:.3f}")

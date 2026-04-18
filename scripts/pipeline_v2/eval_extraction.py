"""Evaluate LLM spec extraction against golden regression set.

Compares current model's output on golden PDFs against frozen expected
output. Gate model upgrades on this script passing.

Usage:
    # Run current extraction against golden set (expensive — uses API)
    python scripts/pipeline_v2/eval_extraction.py --model gemini-2.5-flash \\
        --limit 20 --threshold 0.85

    # Compare a pre-computed extraction dir against golden (free)
    python scripts/pipeline_v2/eval_extraction.py --from-dir path/to/extractions/

Metrics:
    key_recall   — fraction of golden specs keys found in new output
    key_precision — fraction of new output keys that are in golden
    scalar_match  — weight_g/dimensions_mm/ean/series exact equality
    pass_rate    — count where all of the above pass a threshold

Exit 1 if overall pass_rate below --threshold (default 0.85).

Rationale per 4th reviewer (2026-04-18): ~3-5% silent behavioral
regression per major LLM version bump. Gate merges on this signal.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent.parent
GOLDEN_DIR = ROOT / "golden" / "specs_extraction"
PDF_DIR = ROOT / "downloads" / "datasheets_v2"


def compare_specs(expected: dict, actual: dict) -> dict:
    """Compute recall/precision on spec keys (case-insensitive, normalized).

    Returns {key_recall, key_precision, scalar_matches, scalar_total}.
    """
    def norm(k):
        return (k or "").lower().strip().replace(" ", "_")

    exp_keys = {norm(k) for k in (expected.get("specs") or {}).keys()}
    act_keys = {norm(k) for k in (actual.get("specs") or {}).keys()}

    if not exp_keys and not act_keys:
        key_recall = 1.0  # both empty — match
        key_precision = 1.0
    elif not exp_keys:
        key_recall = 1.0
        key_precision = 0.0  # new model produced specs where there should be none
    elif not act_keys:
        key_recall = 0.0  # new model missed all specs
        key_precision = 1.0
    else:
        hits = exp_keys & act_keys
        key_recall = len(hits) / len(exp_keys)
        key_precision = len(hits) / len(act_keys)

    scalar_fields = ["weight_g", "dimensions_mm", "ean", "series"]
    matches = 0
    checked = 0
    for field in scalar_fields:
        e = str(expected.get(field, "") or "").strip().lower()
        a = str(actual.get(field, "") or "").strip().lower()
        if e or a:  # only count field if at least one side has value
            checked += 1
            if e == a:
                matches += 1

    return {
        "key_recall": round(key_recall, 3),
        "key_precision": round(key_precision, 3),
        "scalar_matches": matches,
        "scalar_total": checked,
    }


def load_golden() -> list[dict]:
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(GOLDEN_DIR.glob("*.json"))]


def pdf_sha256(pdf_path: Path) -> str:
    h = hashlib.sha256()
    h.update(pdf_path.read_bytes())
    return h.hexdigest()


def eval_from_dir(from_dir: Path, golden: list[dict]) -> list[dict]:
    """Load pre-computed extractions from directory and diff against golden.

    Expected format: <from_dir>/<pn>.json with {pn, output: {specs, weight_g, ...}}.
    """
    results = []
    for g in golden:
        pn = g["pn"]
        new_file = from_dir / f"{pn}.json"
        if not new_file.exists():
            results.append({"pn": pn, "status": "MISSING",
                            "key_recall": 0.0, "key_precision": 0.0,
                            "scalar_matches": 0, "scalar_total": 0})
            continue
        try:
            new_data = json.loads(new_file.read_text(encoding="utf-8"))
        except Exception as e:
            results.append({"pn": pn, "status": f"INVALID_JSON:{e}",
                            "key_recall": 0.0, "key_precision": 0.0,
                            "scalar_matches": 0, "scalar_total": 0})
            continue

        actual_output = new_data.get("output") or new_data  # support both wrap styles
        metrics = compare_specs(g["expected_output"], actual_output)
        results.append({"pn": pn, "status": "OK", **metrics})
    return results


def summarize(results: list[dict], threshold: float) -> tuple[bool, dict]:
    total = len(results)
    missing = sum(1 for r in results if r["status"] == "MISSING")
    invalid = sum(1 for r in results if r["status"].startswith("INVALID"))
    ok = [r for r in results if r["status"] == "OK"]

    if not ok:
        return False, {"total": total, "missing": missing, "invalid": invalid, "pass_rate": 0.0}

    def passes(r):
        # Pass if key_recall >= threshold AND (no scalars checked OR all scalars match)
        return (r["key_recall"] >= threshold and
                (r["scalar_total"] == 0 or r["scalar_matches"] == r["scalar_total"]))

    passing = [r for r in ok if passes(r)]
    pass_rate = len(passing) / total

    avg_recall = sum(r["key_recall"] for r in ok) / len(ok)
    avg_precision = sum(r["key_precision"] for r in ok) / len(ok)

    summary = {
        "total": total,
        "missing": missing,
        "invalid": invalid,
        "checked": len(ok),
        "passing": len(passing),
        "failing": len(ok) - len(passing),
        "pass_rate": round(pass_rate, 3),
        "avg_key_recall": round(avg_recall, 3),
        "avg_key_precision": round(avg_precision, 3),
        "threshold": threshold,
    }
    return pass_rate >= threshold, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-dir", type=Path, required=True,
                        help="Directory with <pn>.json extraction files to evaluate")
    parser.add_argument("--threshold", type=float, default=0.85,
                        help="Minimum pass_rate to exit 0 (default 0.85)")
    parser.add_argument("--verbose", action="store_true", help="Show per-SKU details")
    args = parser.parse_args()

    golden = load_golden()
    if not golden:
        print("ERROR: golden set is empty. Run _promote_to_golden.py first.", file=sys.stderr)
        sys.exit(2)

    print(f"Golden set: {len(golden)} entries")
    print(f"Comparing against: {args.from_dir}")
    print("=" * 80)

    results = eval_from_dir(args.from_dir, golden)
    passed, summary = summarize(results, args.threshold)

    if args.verbose:
        failing_results = [r for r in results if r["status"] != "OK" or
                           (r.get("key_recall", 0) < args.threshold or
                            (r.get("scalar_total", 0) > 0 and r.get("scalar_matches", 0) < r.get("scalar_total", 0)))]
        for r in failing_results[:30]:
            print(f"  FAIL {r['pn']:<22}  {r['status']:<15}  "
                  f"recall={r.get('key_recall', 0):.2f}  prec={r.get('key_precision', 0):.2f}  "
                  f"scalar={r.get('scalar_matches', 0)}/{r.get('scalar_total', 0)}")

    print()
    print("=" * 80)
    print(f"SUMMARY  total={summary['total']}  checked={summary['checked']}  "
          f"passing={summary['passing']}  failing={summary['failing']}  "
          f"missing={summary['missing']}  invalid={summary['invalid']}")
    print(f"pass_rate={summary['pass_rate']:.3f}  threshold={summary['threshold']:.3f}  "
          f"avg_recall={summary.get('avg_key_recall', 0):.3f}  avg_precision={summary.get('avg_key_precision', 0):.3f}")
    print("=" * 80)

    if not passed:
        print(f"\nFAIL: pass_rate {summary['pass_rate']:.3f} below threshold {summary['threshold']:.3f}")
        sys.exit(1)
    print(f"\nPASS: pass_rate {summary['pass_rate']:.3f} >= threshold {summary['threshold']:.3f}")


if __name__ == "__main__":
    main()

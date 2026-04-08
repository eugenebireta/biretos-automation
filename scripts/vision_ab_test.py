"""vision_ab_test.py — Compare Gemini vision verdicts with existing checkpoint verdicts.

Selects a balanced sample of KEEP/REJECT SKUs from checkpoint, runs Gemini vision
on each, and reports agreement rate. No changes are written to checkpoint.

Usage:
    python scripts/vision_ab_test.py [--limit 20] [--seed 42]
"""
from __future__ import annotations

import json
import logging
import os
import random
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
PHOTOS_DIR = DOWNLOADS / "photos"
CHECKPOINT_FILE = DOWNLOADS / "checkpoint.json"


def load_ab_candidates(checkpoint_path: Path = CHECKPOINT_FILE) -> list[dict]:
    """Load SKUs with existing verdicts and image files on disk."""
    cp = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    candidates = []
    for pn, bundle in cp.items():
        photo = bundle.get("photo", {})
        verdict = photo.get("verdict", "")
        if verdict not in ("KEEP", "REJECT"):
            continue
        name = bundle.get("name", pn)
        # Find image file
        img_path = ""
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            candidate_path = PHOTOS_DIR / f"{pn}{ext}"
            if candidate_path.exists():
                img_path = str(candidate_path)
                break
        if not img_path:
            continue
        candidates.append({
            "pn": pn,
            "name": name,
            "original_verdict": verdict,
            "original_reason": photo.get("reason", ""),
            "image_path": img_path,
        })
    return candidates


def run_ab_test(limit: int = 20, seed: int = 42) -> dict:
    """Run vision A/B test.

    Returns report dict with agreement stats.
    """
    from dotenv import load_dotenv
    load_dotenv(DOWNLOADS / ".env")

    from gemini_provider import vision_verdict_gemini, get_rate_limiter

    candidates = load_ab_candidates()
    log.info(f"Found {len(candidates)} candidates with images")

    # Balanced sample: half KEEP, half REJECT
    keeps = [c for c in candidates if c["original_verdict"] == "KEEP"]
    rejects = [c for c in candidates if c["original_verdict"] == "REJECT"]
    rng = random.Random(seed)
    rng.shuffle(keeps)
    rng.shuffle(rejects)

    half = limit // 2
    sample = keeps[:half] + rejects[:limit - half]
    rng.shuffle(sample)

    log.info(
        f"Sample: {len(sample)} SKUs "
        f"({sum(1 for s in sample if s['original_verdict'] == 'KEEP')} KEEP, "
        f"{sum(1 for s in sample if s['original_verdict'] == 'REJECT')} REJECT)"
    )

    results = []
    agree = 0
    disagree = 0

    for i, item in enumerate(sample, 1):
        pn = item["pn"]
        log.info(f"  [{i}/{len(sample)}] {pn} (original={item['original_verdict']})")

        gemini_result = vision_verdict_gemini(
            image_path=item["image_path"],
            pn=pn,
            name=item["name"],
        )

        gemini_verdict = gemini_result.get("verdict", "UNKNOWN")
        match = gemini_verdict == item["original_verdict"]
        if match:
            agree += 1
        else:
            disagree += 1

        entry = {
            "pn": pn,
            "name": item["name"],
            "original_verdict": item["original_verdict"],
            "original_reason": item["original_reason"],
            "gemini_verdict": gemini_verdict,
            "gemini_reason": gemini_result.get("reason", ""),
            "match": match,
        }
        results.append(entry)
        status = "MATCH" if match else "DISAGREE"
        log.info(
            f"    gemini={gemini_verdict} ({gemini_result.get('reason', '')[:60]}) -> {status}"
        )

    total = agree + disagree
    agreement_pct = (agree / total * 100) if total > 0 else 0

    rate_stats = get_rate_limiter().get_stats()

    report = {
        "total_tested": total,
        "agreement": agree,
        "disagreement": disagree,
        "agreement_pct": round(agreement_pct, 1),
        "results": results,
        "rate_limiter": rate_stats,
        "disagreements": [r for r in results if not r["match"]],
    }

    # Save report
    report_path = ROOT / "shadow_log" / "vision_ab_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info(f"Report saved to {report_path}")

    return report


def main():
    import argparse
    p = argparse.ArgumentParser(description="Vision A/B test: Gemini vs existing verdicts")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    report = run_ab_test(limit=args.limit, seed=args.seed)

    print(f"\n=== Vision A/B Test Results ===")
    print(f"  Tested:      {report['total_tested']}")
    print(f"  Agreement:   {report['agreement']} ({report['agreement_pct']}%)")
    print(f"  Disagreement:{report['disagreement']}")
    print(f"  RPD used:    {report['rate_limiter']['daily_plain']}")

    if report["disagreements"]:
        print(f"\n  Disagreements:")
        for d in report["disagreements"]:
            print(
                f"    {d['pn']:20s} original={d['original_verdict']} "
                f"gemini={d['gemini_verdict']} ({d['gemini_reason'][:50]})"
            )


if __name__ == "__main__":
    main()

"""R1.2 — Confidence Recalculator.

Recomputes confidence.overall_label in evidence files based on current
signal state (identity, photo, price). Fixes stale labels left after
R1.4 photo promotion or other enrichment passes.

Signal model (simplified from confidence.py for bulk recalculation):
    HIGH:     identity_strong AND photo_ok AND price_available
    MEDIUM:   (identity_strong AND photo_ok) OR (identity_strong AND price_available)
    LOW:      identity_strong OR photo_ok
    VERY_LOW: none of the above

Usage:
    python scripts/confidence_recalculator.py               # dry-run report
    python scripts/confidence_recalculator.py --apply        # update evidence
    python scripts/confidence_recalculator.py --apply -v     # update + per-item log
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# ── Constants ──────────────────────────────────────────────────────────────

LABEL_HIGH = "HIGH"
LABEL_MEDIUM = "MEDIUM"
LABEL_LOW = "LOW"
LABEL_VERY_LOW = "VERY_LOW"


# ── Signal extraction ──────────────────────────────────────────────────────

def extract_signals(evidence: dict[str, Any]) -> dict[str, bool]:
    """Extract boolean quality signals from an evidence bundle.

    Returns dict with:
        identity_strong: identity_level == "strong"
        photo_ok: photo verdict in (ACCEPT, KEEP)
        price_available: price_status suggests usable price data
    """
    identity = evidence.get("identity_level", "")
    photo = evidence.get("photo", {})
    photo_verdict = photo.get("verdict", "")
    price = evidence.get("price", {})
    price_status = price.get("price_status", "")

    return {
        "identity_strong": identity == "strong",
        "photo_ok": photo_verdict in ("ACCEPT", "KEEP"),
        "price_available": price_status in (
            "public_price", "rfq_only", "hidden_price",
        ),
    }


# ── Label computation ──────────────────────────────────────────────────────

def compute_label(signals: dict[str, bool]) -> str:
    """Compute confidence label from boolean signals.

    Rules (ordered, first match wins):
        HIGH:     all three signals true
        MEDIUM:   identity + photo, OR identity + price
        LOW:      any one signal true
        VERY_LOW: none true
    """
    id_ok = signals["identity_strong"]
    photo_ok = signals["photo_ok"]
    price_ok = signals["price_available"]

    if id_ok and photo_ok and price_ok:
        return LABEL_HIGH
    if id_ok and (photo_ok or price_ok):
        return LABEL_MEDIUM
    if id_ok or photo_ok or price_ok:
        return LABEL_LOW
    return LABEL_VERY_LOW


# ── Evidence processing ────────────────────────────────────────────────────

def recalculate_confidence(
    evidence: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    """Recalculate confidence label for a single evidence bundle.

    Returns (updated_evidence, new_label, old_label).
    """
    old_conf = evidence.get("confidence", {})
    old_label = old_conf.get("overall_label", LABEL_VERY_LOW)

    signals = extract_signals(evidence)
    new_label = compute_label(signals)

    # Update confidence object
    conf = evidence.get("confidence", {})
    conf["overall_label"] = new_label
    conf["overall_label_prior"] = old_label
    conf["recalculated"] = True
    conf["signals"] = signals
    evidence["confidence"] = conf

    return evidence, new_label, old_label


# ── Main runner ────────────────────────────────────────────────────────────

def run_recalculator(
    evidence_dir: Path,
    output_dir: Path,
    *,
    apply: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run confidence recalculation across all evidence files.

    Returns a report dict with stats.
    """
    evidence_dir = Path(evidence_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(evidence_dir.glob("evidence_*.json"))

    total = 0
    upgraded = 0
    downgraded = 0
    unchanged = 0
    skipped = 0

    old_distribution: dict[str, int] = {}
    new_distribution: dict[str, int] = {}
    transitions: dict[str, int] = {}

    for f in files:
        total += 1
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            skipped += 1
            continue

        updated, new_label, old_label = recalculate_confidence(data)

        # Track distributions
        old_distribution[old_label] = old_distribution.get(old_label, 0) + 1
        new_distribution[new_label] = new_distribution.get(new_label, 0) + 1

        # Track transitions
        transition = f"{old_label}->{new_label}"
        transitions[transition] = transitions.get(transition, 0) + 1

        label_order = [LABEL_VERY_LOW, LABEL_LOW, LABEL_MEDIUM, LABEL_HIGH]
        old_idx = label_order.index(old_label) if old_label in label_order else 0
        new_idx = label_order.index(new_label) if new_label in label_order else 0

        if new_idx > old_idx:
            upgraded += 1
        elif new_idx < old_idx:
            downgraded += 1
        else:
            unchanged += 1

        if apply:
            f.write_text(
                json.dumps(updated, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        if verbose:
            if new_label != old_label:
                print(f"  {old_label:8s} -> {new_label:8s}  {f.stem.replace('evidence_', '')}")

    report = {
        "total_evidence": total,
        "upgraded": upgraded,
        "downgraded": downgraded,
        "unchanged": unchanged,
        "skipped": skipped,
        "applied": apply,
        "old_distribution": dict(sorted(old_distribution.items())),
        "new_distribution": dict(sorted(new_distribution.items())),
        "transitions": dict(sorted(transitions.items(), key=lambda x: -x[1])),
    }

    report_path = output_dir / "confidence_recalc_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return report


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="R1.2 Confidence Recalculator — recompute evidence labels",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=ROOT / "downloads" / "evidence",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "downloads" / "staging",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()
    report = run_recalculator(
        evidence_dir=args.evidence_dir,
        output_dir=args.output_dir,
        apply=args.apply,
        verbose=args.verbose,
    )

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"\n=== Confidence Recalculator [{mode}] ===")
    print(f"Total:      {report['total_evidence']}")
    print(f"Upgraded:   {report['upgraded']}")
    print(f"Downgraded: {report['downgraded']}")
    print(f"Unchanged:  {report['unchanged']}")

    print("\nOld distribution:")
    for label, count in sorted(report["old_distribution"].items()):
        print(f"  {label}: {count}")

    print("\nNew distribution:")
    for label, count in sorted(report["new_distribution"].items()):
        print(f"  {label}: {count}")

    print("\nTop transitions:")
    for t, count in sorted(report["transitions"].items(), key=lambda x: -x[1])[:10]:
        print(f"  {t}: {count}")

    print(f"\nReport: {args.output_dir / 'confidence_recalc_report.json'}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    main()

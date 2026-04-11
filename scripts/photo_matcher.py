"""R1.4 — Photo Matcher / Quality Gate.

Validates existing photos in evidence bundles, promotes KEEP→ACCEPT
for photos that pass the quality gate, and generates a re-search queue
for items that still need photos.

Usage:
    python scripts/photo_matcher.py --dry-run          # report only
    python scripts/photo_matcher.py --apply            # update evidence files
    python scripts/photo_matcher.py --apply --verbose   # update + per-item log
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# ── Constants ──────────────────────────────────────────────────────────────

VERDICT_KEEP = "KEEP"
VERDICT_ACCEPT = "ACCEPT"
VERDICT_REJECT = "REJECT"
VERDICT_NO_PHOTO = "NO_PHOTO"

# Quality gate thresholds
MIN_WIDTH = 200
MIN_HEIGHT = 200
MIN_SIZE_KB = 3

# Promotion reasons
PROMOTED = "promoted_by_quality_gate"
SKIP_FILE_MISSING = "local_file_missing"
SKIP_TOO_SMALL = "below_min_dimensions"
SKIP_TOO_LIGHT = "below_min_filesize"

# Queue reasons
QUEUE_REJECT = "verdict_reject"
QUEUE_NO_PHOTO = "no_photo_data"
QUEUE_EMPTY = "empty_photo_object"
QUEUE_QUALITY_FAIL = "quality_gate_fail"


# ── Source URL extraction ──────────────────────────────────────────────────

def extract_source_url(source: str) -> str | None:
    """Extract URL from 'prefix:url' source format.

    Evidence photos store source as 'google:https://...' or 'jsonld:https://...'.
    Returns the URL part, or None if no valid URL found.
    """
    if not source:
        return None
    # Handle prefix:url format
    if "://" in source:
        # Find the first :// to locate the actual URL
        idx = source.find("://")
        # Walk back to find the prefix separator ':'
        prefix_end = source.rfind(":", 0, idx)
        if prefix_end > 0:
            url = source[prefix_end + 1:]
        else:
            url = source
        return url if url.startswith("http") else None
    return None


# ── Quality gate ───────────────────────────────────────────────────────────

def check_photo_quality(
    photo: dict[str, Any],
    photos_dir: Path | None = None,
) -> tuple[bool, str]:
    """Validate photo against quality thresholds.

    Checks: file exists, dimensions, file size.
    Returns (passed, reason).
    """
    # Check local file exists
    local_path = photo.get("path", "")
    if local_path:
        p = Path(local_path)
        if not p.exists():
            return False, SKIP_FILE_MISSING
    elif photos_dir:
        # Fallback: no path but we have a photos_dir
        return False, SKIP_FILE_MISSING
    else:
        return False, SKIP_FILE_MISSING

    # Dimensions
    w = photo.get("width", 0) or 0
    h = photo.get("height", 0) or 0
    if w < MIN_WIDTH and h < MIN_HEIGHT:
        return False, SKIP_TOO_SMALL

    # File size
    size_kb = photo.get("size_kb", 0) or 0
    if size_kb < MIN_SIZE_KB:
        return False, SKIP_TOO_LIGHT

    return True, PROMOTED


# ── Evidence processing ────────────────────────────────────────────────────

def process_evidence(
    evidence: dict[str, Any],
) -> tuple[dict[str, Any], str, str | None]:
    """Process a single evidence bundle for photo promotion.

    Returns (updated_evidence, action, detail).
    Actions: 'promoted', 'already_accepted', 'queued', 'skipped'.
    """
    photo = evidence.get("photo", {})

    if not photo:
        return evidence, "queued", QUEUE_EMPTY

    verdict = photo.get("verdict", "")

    # Already accepted — nothing to do
    if verdict == VERDICT_ACCEPT:
        return evidence, "already_accepted", None

    # REJECT or NO_PHOTO → queue for re-search
    if verdict == VERDICT_REJECT:
        return evidence, "queued", QUEUE_REJECT
    if verdict == VERDICT_NO_PHOTO:
        return evidence, "queued", QUEUE_NO_PHOTO

    # KEEP → run quality gate
    if verdict == VERDICT_KEEP:
        passed, reason = check_photo_quality(photo)

        if not passed:
            return evidence, "queued", QUEUE_QUALITY_FAIL + ":" + reason

        # Promote: KEEP → ACCEPT
        photo["verdict"] = VERDICT_ACCEPT
        photo["verdict_prior"] = VERDICT_KEEP
        photo["promotion_reason"] = PROMOTED

        # Set photo_url from source if available
        source_url = extract_source_url(photo.get("source", ""))
        if source_url:
            photo["photo_url"] = source_url

        evidence["photo"] = photo
        return evidence, "promoted", reason

    # Unknown verdict → queue
    return evidence, "queued", f"unknown_verdict:{verdict}"


# ── Main runner ────────────────────────────────────────────────────────────

def run_photo_matcher(
    evidence_dir: Path,
    output_dir: Path,
    *,
    apply: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run photo matcher across all evidence files.

    Returns a report dict with stats and queues.
    """
    evidence_dir = Path(evidence_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(evidence_dir.glob("evidence_*.json"))

    # Stats
    total = 0
    promoted = 0
    already_accepted = 0
    queued = 0
    skipped = 0
    queue_items: list[dict[str, str]] = []
    promoted_items: list[dict[str, str]] = []
    queue_reasons: dict[str, int] = {}

    for f in files:
        total += 1
        pn = f.stem.replace("evidence_", "")

        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            skipped += 1
            continue

        updated, action, detail = process_evidence(data)

        if action == "promoted":
            promoted += 1
            promoted_items.append({"part_number": pn, "detail": detail or ""})
            if apply:
                f.write_text(
                    json.dumps(updated, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            if verbose:
                print(f"  ACCEPT  {pn}")

        elif action == "already_accepted":
            already_accepted += 1
            if verbose:
                print(f"  SKIP    {pn} (already accepted)")

        elif action == "queued":
            queued += 1
            reason_key = (detail or "unknown").split(":")[0]
            queue_reasons[reason_key] = queue_reasons.get(reason_key, 0) + 1
            queue_items.append({
                "part_number": pn,
                "brand": data.get("brand", ""),
                "reason": detail or "unknown",
                "current_verdict": data.get("photo", {}).get("verdict", ""),
            })
            if verbose:
                print(f"  QUEUE   {pn} ({detail})")

        else:
            skipped += 1

    # Build report
    report = {
        "total_evidence": total,
        "promoted": promoted,
        "already_accepted": already_accepted,
        "queued_for_research": queued,
        "skipped": skipped,
        "applied": apply,
        "queue_reasons": dict(sorted(queue_reasons.items(), key=lambda x: -x[1])),
        "promoted_items": promoted_items,
    }

    # Write outputs
    report_path = output_dir / "photo_match_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if queue_items:
        queue_path = output_dir / "photo_research_queue.json"
        queue_path.write_text(
            json.dumps(queue_items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return report


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="R1.4 Photo Matcher — validate and promote KEEP→ACCEPT",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=ROOT / "downloads" / "evidence",
        help="Evidence directory (default: downloads/evidence)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "downloads" / "staging",
        help="Output directory for reports (default: downloads/staging)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes to evidence files (default: dry-run)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print per-item actions",
    )

    args = parser.parse_args()
    report = run_photo_matcher(
        evidence_dir=args.evidence_dir,
        output_dir=args.output_dir,
        apply=args.apply,
        verbose=args.verbose,
    )

    # Print summary
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"\n=== Photo Matcher [{mode}] ===")
    print(f"Total evidence:     {report['total_evidence']}")
    print(f"Promoted KEEP->ACCEPT: {report['promoted']}")
    print(f"Already accepted:   {report['already_accepted']}")
    print(f"Queued for research: {report['queued_for_research']}")
    print(f"Skipped:            {report['skipped']}")

    print("\nQueue reasons:")
    for reason, count in sorted(
        report["queue_reasons"].items(), key=lambda x: -x[1],
    ):
        print(f"  {reason}: {count}")

    print(f"\nReport: {args.output_dir / 'photo_match_report.json'}")
    if report["queued_for_research"] > 0:
        print(f"Queue:  {args.output_dir / 'photo_research_queue.json'}")

    # Auto-normalize: update normalized{} blocks after evidence modification
    if args.apply and report.get("promoted", 0) > 0:
        print("\n[auto-normalize] Updating normalized{} blocks...")
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "evidence_normalize.py")],
            check=False,
        )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    main()

"""prepare_rerun.py — Mark DRAFT_ONLY SKUs for re-processing by the pipeline.

Does NOT delete data — only marks checkpoint entries with _status="needs_rerun"
so the pipeline will re-process them on next run.

Usage:
    python scripts/prepare_rerun.py [--checkpoint PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

_DEFAULT_CHECKPOINT = Path(__file__).parent.parent / "downloads" / "checkpoint.json"


def prepare_rerun(
    checkpoint_path: Path = _DEFAULT_CHECKPOINT,
    dry_run: bool = False,
) -> dict:
    """Mark DRAFT_ONLY SKUs for re-processing.

    Returns summary dict.
    """
    data = json.loads(checkpoint_path.read_text("utf-8"))

    # Backup
    now_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = checkpoint_path.parent / f"checkpoint_backup_{now_str}.json"
    if not dry_run:
        shutil.copy2(checkpoint_path, backup_path)

    rerun_count = 0
    skip_count = 0
    status_counts = {}

    for pn, bundle in data.items():
        pdv2 = bundle.get("policy_decision_v2", {})
        card_status = pdv2.get("card_status", "MISSING")
        status_counts[card_status] = status_counts.get(card_status, 0) + 1

        if card_status == "DRAFT_ONLY":
            if not dry_run:
                bundle["_status"] = "needs_rerun"
            rerun_count += 1
        else:
            skip_count += 1

    if not dry_run:
        checkpoint_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return {
        "total": len(data),
        "marked_for_rerun": rerun_count,
        "skipped_non_draft": skip_count,
        "status_counts": status_counts,
        "backup": str(backup_path) if not dry_run else "(dry run)",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare DRAFT_ONLY SKUs for pipeline re-run")
    parser.add_argument("--checkpoint", default=str(_DEFAULT_CHECKPOINT))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    summary = prepare_rerun(Path(args.checkpoint), dry_run=args.dry_run)
    print(f"Total: {summary['total']}")
    print(f"Marked for rerun: {summary['marked_for_rerun']}")
    print(f"Skipped (non-DRAFT): {summary['skipped_non_draft']}")
    print(f"Status counts: {summary['status_counts']}")
    if not args.dry_run:
        print(f"Backup: {summary['backup']}")
    else:
        print("[DRY RUN] No changes written.")

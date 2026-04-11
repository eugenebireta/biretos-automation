"""
SS-1.6 — Migration: legacy evidence.datasheet -> versioned storage.

Idempotent: running twice on the same evidence produces no duplicate versions
(dedup via content_hash idempotency_key).

Usage:
    python -m scripts.datasheet_layer.migrate [--dry-run] [--evidence-dir PATH]
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .ingestion import ingest_from_evidence
from .store import _structured_log

logger = logging.getLogger(__name__)

_DEFAULT_EVIDENCE_DIR = (
    Path(__file__).resolve().parent.parent.parent / "downloads" / "evidence"
)
_DEFAULT_BASE = (
    Path(__file__).resolve().parent.parent.parent / "downloads" / "datasheets"
)


def migrate_all(
    evidence_dir: Path | None = None,
    base_dir: Path | None = None,
    dry_run: bool = False,
    trace_id: str = "migrate",
) -> dict:
    """
    Migrate all evidence files with datasheet data to versioned storage.

    Returns:
        {
            "scanned": int,
            "found": int,        # had datasheet_status=found
            "ingested": int,     # new versions created
            "dedup_skipped": int, # already existed (idempotent)
            "errors": int,
        }
    """
    if evidence_dir is None:
        evidence_dir = _DEFAULT_EVIDENCE_DIR
    if base_dir is None:
        base_dir = _DEFAULT_BASE

    stats = {
        "scanned": 0,
        "found": 0,
        "ingested": 0,
        "dedup_skipped": 0,
        "errors": 0,
    }

    if not evidence_dir.exists():
        _structured_log(
            trace_id, "migrate_no_evidence_dir",
            error_class="PERMANENT", severity="WARNING",
            path=str(evidence_dir),
        )
        return stats

    for efile in sorted(evidence_dir.glob("evidence_*.json")):
        stats["scanned"] += 1
        try:
            evidence = json.loads(efile.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            _structured_log(
                trace_id, "migrate_read_error",
                error_class="TRANSIENT", severity="WARNING", retriable=True,
                file=efile.name, error=str(exc),
            )
            stats["errors"] += 1
            continue

        ds = evidence.get("datasheet", {})
        if not ds or ds.get("datasheet_status") != "found":
            continue

        stats["found"] += 1

        if dry_run:
            # Only count as ingested if pdf_local_path exists —
            # mirror what ingest_from_evidence would actually do.
            pdf_path = ds.get("pdf_local_path")
            if pdf_path and Path(pdf_path).exists():
                stats["ingested"] += 1
            else:
                stats["dedup_skipped"] += 1  # would be skipped: no content hash
            continue

        try:
            result = ingest_from_evidence(
                evidence, trace_id=trace_id, base_dir=base_dir,
            )
            if result is not None:
                stats["ingested"] += 1
            else:
                stats["dedup_skipped"] += 1
        except Exception as exc:
            _structured_log(
                trace_id, "migrate_ingest_error",
                error_class="TRANSIENT", severity="ERROR", retriable=True,
                file=efile.name, error=str(exc),
            )
            stats["errors"] += 1

    _structured_log(
        trace_id, "migrate_complete",
        **{k: v for k, v in stats.items()},
    )
    return stats


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Migrate evidence datasheets to versioned storage")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--evidence-dir", type=Path, default=None)
    parser.add_argument("--base-dir", type=Path, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    result = migrate_all(
        evidence_dir=args.evidence_dir,
        base_dir=args.base_dir,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["errors"] == 0 else 1)

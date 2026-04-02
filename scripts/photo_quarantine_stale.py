"""Quarantine stale rejected derivative photos from photos_enhanced.

Reads a photo_enhance manifest, finds rows marked cleanup_recommended with
stale_existing_derivative_path, and moves those files into a quarantine folder.
The move is lineage-safe and recorded in a structured manifest.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
ENHANCED_DIR = DOWNLOADS / "photos_enhanced"
QUARANTINE_DIR = DOWNLOADS / "photos_enhanced_quarantine"
SCOUT_CACHE_DIR = DOWNLOADS / "scout_cache"

DEFAULT_INPUT_MANIFEST = SCOUT_CACHE_DIR / "photo_enhance_manifest_all25_recheck.jsonl"
DEFAULT_OUTPUT_MANIFEST = SCOUT_CACHE_DIR / "photo_quarantine_manifest.jsonl"
DEFAULT_SUMMARY_FILE = SCOUT_CACHE_DIR / "photo_quarantine_summary.json"


def load_manifest_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _normalize(path: Path) -> Path:
    return path.resolve()


def _is_within(child: Path, parent: Path) -> bool:
    try:
        _normalize(child).relative_to(_normalize(parent))
        return True
    except Exception:
        return False


def quarantine_one(row: dict[str, Any], *, enhanced_dir: Path, quarantine_dir: Path) -> dict[str, Any]:
    part_number = str(row.get("part_number", "")).strip()
    source_path_raw = str(row.get("stale_existing_derivative_path", "")).strip()
    source_path = Path(source_path_raw) if source_path_raw else Path()
    cleanup_recommended = bool(row.get("cleanup_recommended"))
    source_photo_verdict = str(row.get("source_photo_verdict", "")).strip()

    result = {
        "part_number": part_number,
        "cleanup_recommended": cleanup_recommended,
        "source_photo_verdict": source_photo_verdict,
        "source_path": str(source_path) if source_path_raw else "",
        "quarantine_path": "",
        "action": "skipped",
        "reason": "",
        "moved": False,
    }

    if not cleanup_recommended or not source_path_raw:
        result["reason"] = "not_a_cleanup_candidate"
        return result

    if not _is_within(source_path, enhanced_dir):
        result["action"] = "blocked"
        result["reason"] = "source_outside_enhanced_dir"
        return result

    quarantine_path = quarantine_dir / source_path.name
    result["quarantine_path"] = str(quarantine_path)

    source_exists = source_path.exists()
    quarantine_exists = quarantine_path.exists()

    if source_exists and not quarantine_exists:
        quarantine_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(quarantine_path))
        result["action"] = "moved_to_quarantine"
        result["reason"] = "cleanup_recommended_rejected_derivative"
        result["moved"] = True
        return result

    if not source_exists and quarantine_exists:
        result["action"] = "already_quarantined"
        result["reason"] = "destination_exists_source_missing"
        return result

    if source_exists and quarantine_exists:
        result["action"] = "blocked"
        result["reason"] = "destination_already_exists"
        return result

    result["action"] = "missing_source"
    result["reason"] = "source_missing_and_not_quarantined"
    return result


def run(
    input_manifest: Path,
    output_manifest: Path,
    summary_file: Path,
    *,
    enhanced_dir: Path = ENHANCED_DIR,
    quarantine_dir: Path = QUARANTINE_DIR,
) -> dict[str, Any]:
    rows = load_manifest_rows(input_manifest)
    results = [quarantine_one(row, enhanced_dir=enhanced_dir, quarantine_dir=quarantine_dir) for row in rows]

    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    with open(output_manifest, "w", encoding="utf-8") as fh:
        for row in results:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "input_manifest": str(input_manifest),
        "output_manifest": str(output_manifest),
        "enhanced_dir": str(enhanced_dir),
        "quarantine_dir": str(quarantine_dir),
        "rows": len(results),
        "cleanup_candidates": sum(1 for row in results if row["cleanup_recommended"]),
        "moved_to_quarantine": sum(1 for row in results if row["action"] == "moved_to_quarantine"),
        "already_quarantined": sum(1 for row in results if row["action"] == "already_quarantined"),
        "blocked": sum(1 for row in results if row["action"] == "blocked"),
        "missing_source": sum(1 for row in results if row["action"] == "missing_source"),
        "skipped": sum(1 for row in results if row["action"] == "skipped"),
    }
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Move stale rejected enhanced photos into quarantine.")
    parser.add_argument("--input-manifest", default=str(DEFAULT_INPUT_MANIFEST))
    parser.add_argument("--output-manifest", default=str(DEFAULT_OUTPUT_MANIFEST))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY_FILE))
    args = parser.parse_args()

    summary = run(
        Path(args.input_manifest),
        Path(args.output_manifest),
        Path(args.summary),
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

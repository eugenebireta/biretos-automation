from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import photo_quarantine_stale as quarantine  # noqa: E402


def test_run_moves_cleanup_candidate_to_quarantine(tmp_path):
    enhanced_dir = tmp_path / "photos_enhanced"
    quarantine_dir = tmp_path / "photos_enhanced_quarantine"
    scout_cache = tmp_path / "scout_cache"
    source_path = enhanced_dir / "121679-L3__catalog_placeholder_v1__deadbeef.jpg"
    input_manifest = scout_cache / "photo_enhance_manifest.jsonl"
    output_manifest = scout_cache / "photo_quarantine_manifest.jsonl"
    summary_file = scout_cache / "photo_quarantine_summary.json"

    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"fake-jpg")
    input_manifest.parent.mkdir(parents=True, exist_ok=True)
    input_manifest.write_text(
        json.dumps(
            {
                "part_number": "121679-L3",
                "cleanup_recommended": True,
                "source_photo_verdict": "REJECT",
                "stale_existing_derivative_path": str(source_path),
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = quarantine.run(
        input_manifest,
        output_manifest,
        summary_file,
        enhanced_dir=enhanced_dir,
        quarantine_dir=quarantine_dir,
    )

    moved_path = quarantine_dir / source_path.name
    assert summary["moved_to_quarantine"] == 1
    assert source_path.exists() is False
    assert moved_path.exists() is True

    rows = quarantine.load_manifest_rows(output_manifest)
    assert len(rows) == 1
    assert rows[0]["action"] == "moved_to_quarantine"
    assert rows[0]["quarantine_path"] == str(moved_path)


def test_run_blocks_source_outside_enhanced_dir(tmp_path):
    enhanced_dir = tmp_path / "photos_enhanced"
    quarantine_dir = tmp_path / "photos_enhanced_quarantine"
    scout_cache = tmp_path / "scout_cache"
    outside_path = tmp_path / "elsewhere" / "bad.jpg"
    input_manifest = scout_cache / "photo_enhance_manifest.jsonl"
    output_manifest = scout_cache / "photo_quarantine_manifest.jsonl"
    summary_file = scout_cache / "photo_quarantine_summary.json"

    outside_path.parent.mkdir(parents=True, exist_ok=True)
    outside_path.write_bytes(b"fake-jpg")
    input_manifest.parent.mkdir(parents=True, exist_ok=True)
    input_manifest.write_text(
        json.dumps(
            {
                "part_number": "010130.10",
                "cleanup_recommended": True,
                "stale_existing_derivative_path": str(outside_path),
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = quarantine.run(
        input_manifest,
        output_manifest,
        summary_file,
        enhanced_dir=enhanced_dir,
        quarantine_dir=quarantine_dir,
    )

    assert summary["blocked"] == 1
    rows = quarantine.load_manifest_rows(output_manifest)
    assert rows[0]["action"] == "blocked"
    assert rows[0]["reason"] == "source_outside_enhanced_dir"

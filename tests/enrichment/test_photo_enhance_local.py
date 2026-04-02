from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import photo_enhance_local as enhancer  # noqa: E402


def _set_verdict_file(monkeypatch, path: Path) -> None:
    monkeypatch.setattr(enhancer, "PHOTO_VERDICT_FILE", path)
    enhancer.load_photo_verdict_index.cache_clear()


def _make_test_image(path: Path, *, size: tuple[int, int] = (180, 120)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", size, (255, 255, 255))
    for x in range(30, size[0] - 30):
        for y in range(20, size[1] - 20):
            canvas.putpixel((x, y), (40, 80, 140))
    canvas.save(path, format="JPEG", quality=90)


def test_materialize_seed_record_creates_derivative_with_lineage(tmp_path, monkeypatch):
    raw_dir = tmp_path / "photos"
    enhanced_dir = tmp_path / "photos_enhanced"
    raw_path = raw_dir / "1000106.jpg"
    _make_test_image(raw_path)

    monkeypatch.setattr(enhancer, "RAW_PHOTOS_DIR", raw_dir)
    monkeypatch.setattr(enhancer, "ENHANCED_PHOTOS_DIR", enhanced_dir)
    _set_verdict_file(monkeypatch, tmp_path / "photo_verdict.json")

    row = enhancer.materialize_seed_record(
        {
            "part_number": "1000106",
            "brand": "Honeywell",
            "product_name": "304L",
            "source_local_path": str(raw_path),
            "source_photo_status": "placeholder",
            "enhancement_profile": "catalog_placeholder_v1",
            "background_hex": "#F4F1EB",
            "canvas_px": 1200,
            "content_ratio": 0.82,
            "notes": "test",
        }
    )

    assert row["enhanced_exists"] is True
    assert row["output_photo_status"] == "placeholder"
    assert row["lineage_preserved"] is True
    assert row["raw_photo_canonical_preserved"] is True
    assert row["review_required"] is False
    assert Path(row["enhanced_local_path"]).exists()
    assert row["enhanced_width"] == 1200
    assert row["enhanced_height"] == 1200


def test_materialize_seed_record_marks_non_placeholder_source_for_review(tmp_path, monkeypatch):
    raw_dir = tmp_path / "photos"
    enhanced_dir = tmp_path / "photos_enhanced"
    raw_path = raw_dir / "033588.17.jpg"
    _make_test_image(raw_path, size=(140, 140))

    monkeypatch.setattr(enhancer, "RAW_PHOTOS_DIR", raw_dir)
    monkeypatch.setattr(enhancer, "ENHANCED_PHOTOS_DIR", enhanced_dir)
    _set_verdict_file(monkeypatch, tmp_path / "photo_verdict.json")

    row = enhancer.materialize_seed_record(
        {
            "part_number": "033588.17",
            "source_local_path": str(raw_path),
            "source_photo_status": "exact_evidence",
            "enhancement_profile": "catalog_placeholder_v1",
        }
    )

    assert row["enhanced_exists"] is True
    assert row["review_required"] is True
    assert row["policy_reason_code"] == "non_placeholder_source_requires_review"
    assert row["output_identity_proof"] is False


def test_run_preserves_existing_derivative_by_source_sha(tmp_path, monkeypatch):
    raw_dir = tmp_path / "photos"
    enhanced_dir = tmp_path / "photos_enhanced"
    cache_dir = tmp_path / "scout_cache"
    seed_path = cache_dir / "seed.jsonl"
    manifest_path = cache_dir / "manifest.jsonl"
    raw_path = raw_dir / "1012539.jpg"
    _make_test_image(raw_path)

    monkeypatch.setattr(enhancer, "RAW_PHOTOS_DIR", raw_dir)
    monkeypatch.setattr(enhancer, "ENHANCED_PHOTOS_DIR", enhanced_dir)
    _set_verdict_file(monkeypatch, tmp_path / "photo_verdict.json")

    seed_path.parent.mkdir(parents=True, exist_ok=True)
    seed_path.write_text(
        json.dumps(
            {
                "part_number": "1012539",
                "source_local_path": str(raw_path),
                "source_photo_status": "placeholder",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    first = enhancer.run(seed_path, manifest_path)
    second = enhancer.run(seed_path, manifest_path)

    assert len(first) == 1
    assert len(second) == 1
    assert first[0]["enhanced_local_path"] == second[0]["enhanced_local_path"]
    assert second[0]["used_existing_derivative"] is True
    assert second[0]["generation_reason"] == "existing_derivative_preserved"
    assert second[0]["enhancement_steps"] == enhancer.PLACEHOLDER_ENHANCEMENT_STEPS


def test_materialize_seed_record_blocks_rejected_source_and_flags_stale_derivative(tmp_path, monkeypatch):
    raw_dir = tmp_path / "photos"
    enhanced_dir = tmp_path / "photos_enhanced"
    verdict_path = tmp_path / "photo_verdict.json"
    raw_path = raw_dir / "121679-L3.jpg"
    _make_test_image(raw_path, size=(350, 286))

    monkeypatch.setattr(enhancer, "RAW_PHOTOS_DIR", raw_dir)
    monkeypatch.setattr(enhancer, "ENHANCED_PHOTOS_DIR", enhanced_dir)
    _set_verdict_file(monkeypatch, verdict_path)

    source_sha1 = enhancer.compute_sha1(raw_path)
    stale_derivative_path = enhancer.output_path_for_record("121679-L3", "catalog_placeholder_v1", source_sha1)
    stale_derivative_path.parent.mkdir(parents=True, exist_ok=True)
    _make_test_image(stale_derivative_path, size=(1400, 1400))

    verdict_path.write_text(
        json.dumps(
            {
                "121679-L3": {
                    "verdict": "REJECT",
                    "reason": "logo-only image",
                    "path": str(raw_path),
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    enhancer.load_photo_verdict_index.cache_clear()

    row = enhancer.materialize_seed_record(
        {
            "part_number": "121679-L3",
            "source_local_path": str(raw_path),
            "source_photo_status": "placeholder",
            "enhancement_profile": "catalog_placeholder_v1",
        }
    )

    assert row["source_photo_verdict"] == "REJECT"
    assert row["enhanced_exists"] is False
    assert row["output_photo_status"] == "rejected"
    assert row["policy_reason_code"] == "source_photo_verdict_reject"
    assert row["review_required"] is False
    assert row["stale_existing_derivative_found"] is True
    assert row["stale_existing_derivative_path"] == str(stale_derivative_path)
    assert row["generation_reason"] == "blocked_by_source_photo_verdict"


def test_load_seed_records_accepts_utf8_bom(tmp_path):
    seed_path = tmp_path / "seed_bom.jsonl"
    seed_path.write_text(
        json.dumps(
            {
                "part_number": "010130.10",
                "source_local_path": "d:\\BIRETOS\\projects\\biretos-automation\\downloads\\photos\\010130.10.jpg",
                "source_photo_status": "placeholder",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8-sig",
    )

    rows = enhancer.load_seed_records(seed_path)

    assert len(rows) == 1
    assert rows[0]["part_number"] == "010130.10"

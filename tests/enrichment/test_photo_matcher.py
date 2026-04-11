"""R1.4 — Photo Matcher: deterministic tests.

Covers: source URL extraction, quality gate, evidence promotion,
queue generation, and full pipeline dry-run / apply modes.

No live API, no unmocked time/randomness.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from photo_matcher import (  # noqa: E402
    PROMOTED,
    QUEUE_EMPTY,
    QUEUE_NO_PHOTO,
    QUEUE_QUALITY_FAIL,
    QUEUE_REJECT,
    SKIP_FILE_MISSING,
    SKIP_TOO_LIGHT,
    SKIP_TOO_SMALL,
    VERDICT_ACCEPT,
    VERDICT_KEEP,
    VERDICT_NO_PHOTO,
    VERDICT_REJECT,
    check_photo_quality,
    extract_source_url,
    process_evidence,
    run_photo_matcher,
)


# =============================================================================
# Source URL extraction
# =============================================================================

class TestExtractSourceUrl:
    """Source field uses prefix:url format."""

    def test_google_prefix(self):
        url = extract_source_url("google:https://www.example.com/page")
        assert url == "https://www.example.com/page"

    def test_jsonld_prefix(self):
        url = extract_source_url("jsonld:https://shop.example.com/product/123")
        assert url == "https://shop.example.com/product/123"

    def test_yandex_prefix(self):
        url = extract_source_url("yandex:https://market.yandex.ru/item/42")
        assert url == "https://market.yandex.ru/item/42"

    def test_img_prefix(self):
        url = extract_source_url("img:https://cdn.example.com/photo.jpg")
        assert url == "https://cdn.example.com/photo.jpg"

    def test_empty_source(self):
        assert extract_source_url("") is None

    def test_none_source(self):
        assert extract_source_url(None) is None

    def test_no_url(self):
        assert extract_source_url("cached") is None

    def test_bare_url(self):
        url = extract_source_url("https://example.com/photo.jpg")
        assert url == "https://example.com/photo.jpg"


# =============================================================================
# Quality gate
# =============================================================================

class TestQualityGate:
    """Photo quality checks: file exists, dimensions, size."""

    def test_passes_good_photo(self, tmp_path):
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"x" * 4096)
        photo = {
            "path": str(img),
            "width": 300,
            "height": 300,
            "size_kb": 10,
        }
        passed, reason = check_photo_quality(photo)
        assert passed is True
        assert reason == PROMOTED

    def test_fails_missing_file(self, tmp_path):
        photo = {
            "path": str(tmp_path / "nonexistent.jpg"),
            "width": 300,
            "height": 300,
            "size_kb": 10,
        }
        passed, reason = check_photo_quality(photo)
        assert passed is False
        assert reason == SKIP_FILE_MISSING

    def test_fails_no_path(self):
        photo = {"width": 300, "height": 300, "size_kb": 10}
        passed, reason = check_photo_quality(photo)
        assert passed is False
        assert reason == SKIP_FILE_MISSING

    def test_fails_small_dimensions(self, tmp_path):
        img = tmp_path / "tiny.jpg"
        img.write_bytes(b"x" * 4096)
        photo = {
            "path": str(img),
            "width": 100,
            "height": 100,
            "size_kb": 10,
        }
        passed, reason = check_photo_quality(photo)
        assert passed is False
        assert reason == SKIP_TOO_SMALL

    def test_passes_one_dimension_ok(self, tmp_path):
        """At least one dimension >= threshold passes."""
        img = tmp_path / "narrow.jpg"
        img.write_bytes(b"x" * 4096)
        photo = {
            "path": str(img),
            "width": 400,
            "height": 150,
            "size_kb": 10,
        }
        passed, reason = check_photo_quality(photo)
        assert passed is True

    def test_fails_tiny_filesize(self, tmp_path):
        img = tmp_path / "icon.jpg"
        img.write_bytes(b"x" * 1024)
        photo = {
            "path": str(img),
            "width": 300,
            "height": 300,
            "size_kb": 1,
        }
        passed, reason = check_photo_quality(photo)
        assert passed is False
        assert reason == SKIP_TOO_LIGHT

    def test_passes_boundary_dimensions(self, tmp_path):
        img = tmp_path / "exact.jpg"
        img.write_bytes(b"x" * 4096)
        photo = {
            "path": str(img),
            "width": 200,
            "height": 200,
            "size_kb": 3,
        }
        passed, reason = check_photo_quality(photo)
        assert passed is True

    def test_null_dimensions_fail(self, tmp_path):
        img = tmp_path / "nodata.jpg"
        img.write_bytes(b"x" * 4096)
        photo = {
            "path": str(img),
            "width": None,
            "height": None,
            "size_kb": 10,
        }
        passed, reason = check_photo_quality(photo)
        assert passed is False
        assert reason == SKIP_TOO_SMALL


# =============================================================================
# Evidence processing
# =============================================================================

class TestProcessEvidence:
    """Single evidence bundle processing."""

    def _make_evidence(self, tmp_path, verdict, **kwargs):
        """Create evidence with a local photo file."""
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"x" * 4096)
        photo = {
            "verdict": verdict,
            "path": str(img),
            "width": 300,
            "height": 300,
            "size_kb": 10,
            "source": "google:https://example.com/product",
            **kwargs,
        }
        return {"part_number": "TEST-001", "brand": "ACME", "photo": photo}

    def test_promotes_keep_to_accept(self, tmp_path):
        evidence = self._make_evidence(tmp_path, VERDICT_KEEP)
        updated, action, detail = process_evidence(evidence)
        assert action == "promoted"
        assert updated["photo"]["verdict"] == VERDICT_ACCEPT
        assert updated["photo"]["verdict_prior"] == VERDICT_KEEP
        assert updated["photo"]["promotion_reason"] == PROMOTED
        assert updated["photo"]["photo_url"] == "https://example.com/product"

    def test_keeps_already_accepted(self, tmp_path):
        evidence = self._make_evidence(tmp_path, VERDICT_ACCEPT)
        updated, action, _ = process_evidence(evidence)
        assert action == "already_accepted"

    def test_queues_reject(self, tmp_path):
        evidence = self._make_evidence(tmp_path, VERDICT_REJECT)
        _, action, detail = process_evidence(evidence)
        assert action == "queued"
        assert detail == QUEUE_REJECT

    def test_queues_no_photo(self, tmp_path):
        evidence = self._make_evidence(tmp_path, VERDICT_NO_PHOTO)
        _, action, detail = process_evidence(evidence)
        assert action == "queued"
        assert detail == QUEUE_NO_PHOTO

    def test_queues_empty_photo(self):
        evidence = {"part_number": "X", "photo": {}}
        _, action, detail = process_evidence(evidence)
        assert action == "queued"
        assert detail == QUEUE_EMPTY

    def test_queues_no_photo_key(self):
        evidence = {"part_number": "X"}
        _, action, detail = process_evidence(evidence)
        assert action == "queued"
        assert detail == QUEUE_EMPTY

    def test_queues_quality_fail(self):
        evidence = {
            "photo": {
                "verdict": VERDICT_KEEP,
                "path": "/nonexistent/photo.jpg",
                "width": 300,
                "height": 300,
                "size_kb": 10,
            },
        }
        _, action, detail = process_evidence(evidence)
        assert action == "queued"
        assert QUEUE_QUALITY_FAIL in detail

    def test_no_source_url_still_promotes(self, tmp_path):
        """KEEP photo with no source URL still promotes but photo_url stays None."""
        evidence = self._make_evidence(tmp_path, VERDICT_KEEP, source="cached")
        updated, action, _ = process_evidence(evidence)
        assert action == "promoted"
        assert updated["photo"]["verdict"] == VERDICT_ACCEPT
        assert updated["photo"].get("photo_url") is None


# =============================================================================
# Full pipeline
# =============================================================================

class TestFullPipeline:
    """End-to-end photo matcher runs."""

    def _write_evidence(self, evidence_dir, photos_dir, pn, verdict, **kwargs):
        """Write evidence file with optional local photo."""
        photo_path = None
        if verdict in (VERDICT_KEEP, VERDICT_ACCEPT):
            img = photos_dir / f"{pn}.jpg"
            img.write_bytes(b"x" * 4096)
            photo_path = str(img)

        photo = {"verdict": verdict, "width": 300, "height": 300, "size_kb": 10}
        if photo_path:
            photo["path"] = photo_path
        photo["source"] = kwargs.pop("source", "google:https://example.com")
        photo.update(kwargs)

        data = {"part_number": pn, "brand": "ACME", "photo": photo}
        path = evidence_dir / f"evidence_{pn}.json"
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_dry_run_does_not_modify(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        photos_dir = tmp_path / "photos"
        photos_dir.mkdir()
        output_dir = tmp_path / "output"

        self._write_evidence(evidence_dir, photos_dir, "A001", VERDICT_KEEP)
        original = (evidence_dir / "evidence_A001.json").read_text(encoding="utf-8")

        report = run_photo_matcher(evidence_dir, output_dir, apply=False)

        after = (evidence_dir / "evidence_A001.json").read_text(encoding="utf-8")
        assert original == after  # No modification
        assert report["promoted"] == 1
        assert report["applied"] is False
        assert (output_dir / "photo_match_report.json").exists()

    def test_apply_modifies_evidence(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        photos_dir = tmp_path / "photos"
        photos_dir.mkdir()
        output_dir = tmp_path / "output"

        self._write_evidence(evidence_dir, photos_dir, "B001", VERDICT_KEEP)

        report = run_photo_matcher(evidence_dir, output_dir, apply=True)

        data = json.loads(
            (evidence_dir / "evidence_B001.json").read_text(encoding="utf-8"),
        )
        assert data["photo"]["verdict"] == VERDICT_ACCEPT
        assert report["promoted"] == 1
        assert report["applied"] is True

    def test_mixed_verdicts(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        photos_dir = tmp_path / "photos"
        photos_dir.mkdir()
        output_dir = tmp_path / "output"

        self._write_evidence(evidence_dir, photos_dir, "C001", VERDICT_KEEP)
        self._write_evidence(evidence_dir, photos_dir, "C002", VERDICT_REJECT)
        self._write_evidence(evidence_dir, photos_dir, "C003", VERDICT_NO_PHOTO)
        # Empty photo
        (evidence_dir / "evidence_C004.json").write_text(
            json.dumps({"part_number": "C004", "photo": {}}), encoding="utf-8",
        )

        report = run_photo_matcher(evidence_dir, output_dir, apply=False)

        assert report["total_evidence"] == 4
        assert report["promoted"] == 1
        assert report["queued_for_research"] == 3

    def test_queue_file_generated(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        photos_dir = tmp_path / "photos"
        photos_dir.mkdir()
        output_dir = tmp_path / "output"

        self._write_evidence(evidence_dir, photos_dir, "D001", VERDICT_REJECT)

        run_photo_matcher(evidence_dir, output_dir, apply=False)

        queue_path = output_dir / "photo_research_queue.json"
        assert queue_path.exists()
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        assert len(queue) == 1
        assert queue[0]["part_number"] == "D001"
        assert queue[0]["reason"] == QUEUE_REJECT

    def test_all_promoted_no_queue_file(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        photos_dir = tmp_path / "photos"
        photos_dir.mkdir()
        output_dir = tmp_path / "output"

        self._write_evidence(evidence_dir, photos_dir, "E001", VERDICT_KEEP)

        run_photo_matcher(evidence_dir, output_dir, apply=False)

        # Queue file should not exist (or be empty) — actually it shouldn't be
        # written at all since queue_items is empty
        # But the logic writes it if queue_items is non-empty
        # With 0 queued items, file should not exist
        queue_path = output_dir / "photo_research_queue.json"
        assert not queue_path.exists()

    def test_idempotent_double_apply(self, tmp_path):
        """Running apply twice should not double-promote."""
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        photos_dir = tmp_path / "photos"
        photos_dir.mkdir()
        output_dir = tmp_path / "output"

        self._write_evidence(evidence_dir, photos_dir, "F001", VERDICT_KEEP)

        run_photo_matcher(evidence_dir, output_dir, apply=True)
        report2 = run_photo_matcher(evidence_dir, output_dir, apply=True)

        assert report2["promoted"] == 0
        assert report2["already_accepted"] == 1

    def test_report_has_queue_reasons(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        photos_dir = tmp_path / "photos"
        photos_dir.mkdir()
        output_dir = tmp_path / "output"

        self._write_evidence(evidence_dir, photos_dir, "G001", VERDICT_REJECT)
        self._write_evidence(evidence_dir, photos_dir, "G002", VERDICT_REJECT)
        self._write_evidence(evidence_dir, photos_dir, "G003", VERDICT_NO_PHOTO)

        report = run_photo_matcher(evidence_dir, output_dir, apply=False)

        assert report["queue_reasons"]["verdict_reject"] == 2
        assert report["queue_reasons"]["no_photo_data"] == 1

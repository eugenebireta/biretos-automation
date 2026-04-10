"""R1.1 — Catalog Import Pipeline: deterministic tests.

Covers: parsing, normalization, validation, dedup, evidence enrichment,
confidence gating, classification, and full pipeline dry-run.

No live API, no unmocked time/randomness.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from catalog_import import (  # noqa: E402
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    REASON_DUPLICATE_PN,
    REASON_LOW_CONFIDENCE,
    REASON_MISSING_PRICE,
    REASON_NO_EVIDENCE,
    REASON_NO_PHOTO,
    REASON_TITLE_CONFIDENCE_LOW,
    STATUS_ACCEPTED,
    STATUS_REVIEW_REQUIRED,
    build_import_record,
    classify_row,
    enrich_from_evidence,
    normalize_row,
    parse_csv,
    parse_input,
    run_import,
    validate_row,
)


# =============================================================================
# Normalization
# =============================================================================

class TestNormalization:
    """PN and brand must be stripped + uppercased."""

    def test_uppercase_pn_and_brand(self):
        row = normalize_row({"part_number": " abc-123 ", "brand": " honeywell "})
        assert row["part_number"] == "ABC-123"
        assert row["brand"] == "HONEYWELL"

    def test_quantity_coercion(self):
        row = normalize_row({"part_number": "X", "brand": "Y", "quantity": 5.7})
        assert row["quantity"] == 5

    def test_quantity_none_to_zero(self):
        row = normalize_row({"part_number": "X", "brand": "Y", "quantity": None})
        assert row["quantity"] == 0

    def test_price_coercion(self):
        row = normalize_row({"part_number": "X", "brand": "Y", "unit_price": "123.45"})
        assert row["unit_price"] == 123.45

    def test_price_none_stays_none(self):
        row = normalize_row({"part_number": "X", "brand": "Y", "unit_price": None})
        assert row["unit_price"] is None

    def test_missing_fields_default(self):
        row = normalize_row({})
        assert row["part_number"] == ""
        assert row["brand"] == ""
        assert row["quantity"] == 0
        assert row["unit_price"] is None


# =============================================================================
# Validation
# =============================================================================

class TestValidation:
    """Input contract: PN + brand + qty>0 required."""

    def test_valid_row(self):
        valid, reason = validate_row({
            "part_number": "ABC", "brand": "HONEYWELL", "quantity": 10,
        })
        assert valid is True
        assert reason is None

    def test_missing_pn(self):
        valid, reason = validate_row({
            "part_number": "", "brand": "HONEYWELL", "quantity": 10,
        })
        assert valid is False
        assert "part_number" in reason

    def test_missing_brand(self):
        valid, reason = validate_row({
            "part_number": "ABC", "brand": "", "quantity": 10,
        })
        assert valid is False
        assert "brand" in reason

    def test_zero_quantity(self):
        valid, reason = validate_row({
            "part_number": "ABC", "brand": "HONEYWELL", "quantity": 0,
        })
        assert valid is False
        assert "quantity" in reason

    def test_negative_quantity(self):
        valid, reason = validate_row({
            "part_number": "ABC", "brand": "HONEYWELL", "quantity": -1,
        })
        assert valid is False

    def test_price_not_required(self):
        """unit_price is optional — should pass without it."""
        valid, _ = validate_row({
            "part_number": "ABC", "brand": "HONEYWELL", "quantity": 5,
            "unit_price": None,
        })
        assert valid is True


# =============================================================================
# Evidence enrichment
# =============================================================================

class TestEvidenceEnrichment:
    """Evidence lookup and field extraction."""

    def _write_evidence(self, tmp_path, pn, data):
        path = tmp_path / f"evidence_{pn}.json"
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_no_evidence_marks_low(self, tmp_path):
        row = {"part_number": "MISSING", "brand": "X", "unit_price": None}
        result = enrich_from_evidence(row, tmp_path)
        assert result["confidence"] == CONFIDENCE_LOW
        assert result["evidence_found"] is False
        assert REASON_NO_EVIDENCE in result["review_reasons"]

    def test_high_confidence_with_photo(self, tmp_path):
        self._write_evidence(tmp_path, "GOOD", {
            "confidence": {"overall_label": "HIGH"},
            "photo": {"verdict": "ACCEPT", "photo_url": "http://img/1.jpg"},
            "price": {"price_status": "public_price"},
            "identity_level": "strong",
        })
        row = {"part_number": "GOOD", "brand": "X", "unit_price": 100.0}
        result = enrich_from_evidence(row, tmp_path)
        assert result["confidence"] == CONFIDENCE_HIGH
        assert result["photo_url"] == "http://img/1.jpg"
        assert result["review_reasons"] == []

    def test_rejected_photo_adds_reason(self, tmp_path):
        self._write_evidence(tmp_path, "NOPHOTO", {
            "confidence": {"overall_label": "MEDIUM"},
            "photo": {"verdict": "REJECT"},
            "price": {"price_status": "public_price"},
            "identity_level": "strong",
        })
        row = {"part_number": "NOPHOTO", "brand": "X", "unit_price": 50.0}
        result = enrich_from_evidence(row, tmp_path)
        assert result["photo_url"] is None
        assert REASON_NO_PHOTO in result["review_reasons"]

    def test_weak_identity_adds_reason(self, tmp_path):
        self._write_evidence(tmp_path, "WEAK", {
            "confidence": {"overall_label": "LOW"},
            "photo": {"verdict": "ACCEPT", "photo_url": "http://img/2.jpg"},
            "price": {"price_status": "public_price"},
            "identity_level": "weak",
        })
        row = {"part_number": "WEAK", "brand": "X", "unit_price": 50.0}
        result = enrich_from_evidence(row, tmp_path)
        assert REASON_TITLE_CONFIDENCE_LOW in result["review_reasons"]

    def test_missing_price_adds_reason(self, tmp_path):
        self._write_evidence(tmp_path, "NOPRICE", {
            "confidence": {"overall_label": "MEDIUM"},
            "photo": {"verdict": "ACCEPT", "photo_url": "http://img/3.jpg"},
            "price": {"price_status": "rfq_only"},
            "identity_level": "strong",
        })
        row = {"part_number": "NOPRICE", "brand": "X", "unit_price": None}
        result = enrich_from_evidence(row, tmp_path)
        assert REASON_MISSING_PRICE in result["review_reasons"]


# =============================================================================
# Classification
# =============================================================================

class TestClassification:
    """Confidence-driven routing."""

    def test_high_no_issues_accepted(self):
        row = {"confidence": CONFIDENCE_HIGH, "review_reasons": []}
        result = classify_row(row)
        assert result["status"] == STATUS_ACCEPTED

    def test_high_with_issues_review(self):
        row = {"confidence": CONFIDENCE_HIGH, "review_reasons": [REASON_NO_PHOTO]}
        result = classify_row(row)
        assert result["status"] == STATUS_REVIEW_REQUIRED

    def test_medium_always_review(self):
        row = {"confidence": CONFIDENCE_MEDIUM, "review_reasons": []}
        result = classify_row(row)
        assert result["status"] == STATUS_REVIEW_REQUIRED

    def test_low_always_review(self):
        row = {"confidence": CONFIDENCE_LOW, "review_reasons": [REASON_NO_EVIDENCE]}
        result = classify_row(row)
        assert result["status"] == STATUS_REVIEW_REQUIRED

    def test_low_no_reasons_uses_low_confidence(self):
        """LOW confidence with empty review_reasons must use REASON_LOW_CONFIDENCE,
        not REASON_NO_EVIDENCE (which should only mean 'file not found')."""
        row = {"confidence": CONFIDENCE_LOW, "review_reasons": []}
        result = classify_row(row)
        assert result["status"] == STATUS_REVIEW_REQUIRED
        assert result["review_reason"] == REASON_LOW_CONFIDENCE


# =============================================================================
# Import record builder
# =============================================================================

class TestBuildImportRecord:
    """Record must match migration 021 schema."""

    def test_record_has_required_fields(self):
        row = {
            "part_number": "ABC-123", "brand": "HONEYWELL",
            "title_ru": "Test", "quantity": 5, "unit_price": 100.0,
            "confidence": CONFIDENCE_HIGH, "review_reason": None,
            "photo_url": "http://img.jpg", "status": STATUS_ACCEPTED,
            "error_class": None, "error": None,
        }
        record = build_import_record(row, "job-1", "trace-1")
        assert record["part_number"] == "ABC-123"
        assert record["brand"] == "HONEYWELL"
        assert record["job_id"] == "job-1"
        assert record["trace_id"] == "trace-1"
        assert len(record["idempotency_key"]) == 16
        assert record["id"]  # UUID present

    def test_idempotency_key_deterministic(self):
        row1 = {"part_number": "X", "brand": "Y"}
        row2 = {"part_number": "X", "brand": "Y"}
        r1 = build_import_record(row1, "j", "t")
        r2 = build_import_record(row2, "j", "t")
        assert r1["idempotency_key"] == r2["idempotency_key"]

    def test_idempotency_key_differs_by_brand(self):
        row1 = {"part_number": "X", "brand": "A"}
        row2 = {"part_number": "X", "brand": "B"}
        r1 = build_import_record(row1, "j", "t")
        r2 = build_import_record(row2, "j", "t")
        assert r1["idempotency_key"] != r2["idempotency_key"]


# =============================================================================
# CSV parsing
# =============================================================================

class TestCsvParsing:
    """CSV input must be parsed correctly."""

    def test_parse_csv(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(
            "part_number,brand,quantity,unit_price\n"
            "ABC-123,Honeywell,10,500.0\n"
            "DEF-456,PEHA,5,\n",
            encoding="utf-8",
        )
        rows = parse_csv(csv_file)
        assert len(rows) == 2
        assert rows[0]["part_number"] == "ABC-123"
        assert rows[1]["unit_price"] == ""

    def test_parse_input_csv(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(
            "part_number,brand,quantity,unit_price\n"
            "X,Y,1,100\n",
            encoding="utf-8",
        )
        rows = parse_input(csv_file)
        assert len(rows) == 1

    def test_unsupported_format_raises(self, tmp_path):
        bad = tmp_path / "data.xml"
        bad.write_text("<data/>", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported"):
            parse_input(bad)


# =============================================================================
# Dedup
# =============================================================================

class TestDedup:
    """Duplicate PN+brand rows must be rejected."""

    def test_dedup_rejects_second(self, tmp_path):
        csv_file = tmp_path / "dupes.csv"
        csv_file.write_text(
            "part_number,brand,quantity,unit_price\n"
            "ABC,Honeywell,10,100\n"
            "ABC,Honeywell,5,200\n",
            encoding="utf-8",
        )
        report = run_import(
            csv_file, evidence_dir=tmp_path, output_dir=tmp_path,
            dry_run=True,
        )
        assert report["rejected"] == 1
        assert report["total_after_dedup"] == 1
        assert REASON_DUPLICATE_PN in report["by_reason"]


# =============================================================================
# Full pipeline integration
# =============================================================================

class TestFullPipeline:
    """End-to-end import with dry-run."""

    def test_dry_run_writes_report_not_records(self, tmp_path):
        csv_file = tmp_path / "input.csv"
        csv_file.write_text(
            "part_number,brand,quantity,unit_price\n"
            "TEST-001,ACME,10,500\n"
            "TEST-002,ACME,5,\n",
            encoding="utf-8",
        )
        out = tmp_path / "output"
        report = run_import(
            csv_file, evidence_dir=tmp_path, output_dir=out, dry_run=True,
        )
        assert report["total_parsed"] == 2
        assert report["dry_run"] is True
        assert (out / "import_report.json").exists()
        assert not (out / "stg_catalog_imports.json").exists()

    def test_full_run_writes_records(self, tmp_path):
        csv_file = tmp_path / "input.csv"
        csv_file.write_text(
            "part_number,brand,quantity,unit_price\n"
            "REAL-001,BRAND,10,100\n",
            encoding="utf-8",
        )
        out = tmp_path / "output"
        run_import(
            csv_file, evidence_dir=tmp_path, output_dir=out, dry_run=False,
        )
        assert (out / "stg_catalog_imports.json").exists()
        records = json.loads((out / "stg_catalog_imports.json").read_text(encoding="utf-8"))
        assert len(records) == 1
        assert records[0]["part_number"] == "REAL-001"
        assert records[0]["brand"] == "BRAND"

    def test_validation_rejection(self, tmp_path):
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text(
            "part_number,brand,quantity,unit_price\n"
            ",ACME,10,500\n"
            "GOOD,ACME,10,500\n",
            encoding="utf-8",
        )
        out = tmp_path / "output"
        report = run_import(
            csv_file, evidence_dir=tmp_path, output_dir=out, dry_run=True,
        )
        assert report["rejected"] == 1
        assert report["total_after_dedup"] == 1

    def test_evidence_enrichment_in_pipeline(self, tmp_path):
        """Row with HIGH evidence should be classified as accepted."""
        # Write evidence
        evidence = {
            "confidence": {"overall_label": "HIGH"},
            "photo": {"verdict": "ACCEPT", "photo_url": "http://img.jpg"},
            "price": {"price_status": "public_price"},
            "identity_level": "strong",
        }
        (tmp_path / "evidence_GOOD-001.json").write_text(
            json.dumps(evidence), encoding="utf-8",
        )

        csv_file = tmp_path / "input.csv"
        csv_file.write_text(
            "part_number,brand,quantity,unit_price\n"
            "good-001,TestBrand,10,500\n",
            encoding="utf-8",
        )
        out = tmp_path / "output"
        report = run_import(
            csv_file, evidence_dir=tmp_path, output_dir=out, dry_run=False,
        )
        assert report["accepted"] == 1
        assert report["confidence_distribution"]["HIGH"] == 1

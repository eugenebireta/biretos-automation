"""Tests for golden_eval.py — schema validation, loader, and seed data integrity."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from golden_eval import (  # noqa: E402
    validate_record,
    load_golden_dataset,
    create_golden_record,
    save_golden_record,
    golden_summary,
    GOLDEN_EVAL_SCHEMA_VERSION,
    VALID_TASK_TYPES,
)


class TestValidateRecord:
    """Schema validation catches malformed records."""

    def test_valid_price_extraction(self):
        record = create_golden_record(
            task_type="price_extraction",
            pn="T7560B1024",
            expected_output={"price": 245.0, "currency": "EUR"},
            input_text="Some page text",
        )
        errors = validate_record(record)
        assert errors == []

    def test_valid_spec_extraction(self):
        record = create_golden_record(
            task_type="spec_extraction",
            pn="PN1",
            expected_output={"voltage": "24V"},
            input_text="<table>...</table>",
        )
        assert validate_record(record) == []

    def test_valid_image_validation(self):
        record = create_golden_record(
            task_type="image_validation",
            pn="PN1",
            expected_output={"verdict": "KEEP"},
        )
        assert validate_record(record) == []

    def test_missing_pn_rejected(self):
        record = {
            "task_type": "price_extraction", "expected_output": {},
            "verification_status": "verified", "input_text": "x",
        }
        errors = validate_record(record)
        assert any("pn" in e for e in errors)

    def test_missing_task_type_rejected(self):
        record = {"pn": "X", "expected_output": {}, "verification_status": "verified"}
        errors = validate_record(record)
        assert any("task_type" in e for e in errors)

    def test_invalid_task_type_rejected(self):
        record = {
            "task_type": "nonexistent_task",
            "pn": "X", "expected_output": {},
            "verification_status": "verified",
        }
        errors = validate_record(record)
        assert any("invalid task_type" in e for e in errors)

    def test_missing_expected_output_rejected(self):
        record = {"task_type": "price_extraction", "pn": "X", "verification_status": "verified", "input_text": "x"}
        errors = validate_record(record)
        assert any("expected_output" in e for e in errors)

    def test_invalid_verification_status_rejected(self):
        record = {
            "task_type": "price_extraction", "pn": "X",
            "expected_output": {}, "verification_status": "wrong",
            "input_text": "x",
        }
        errors = validate_record(record)
        assert any("verification_status" in e for e in errors)

    def test_price_extraction_needs_input_text(self):
        record = {
            "task_type": "price_extraction", "pn": "X",
            "expected_output": {}, "verification_status": "verified",
        }
        errors = validate_record(record)
        assert any("input_text" in e for e in errors)

    def test_image_validation_no_input_text_needed(self):
        record = {
            "task_type": "image_validation", "pn": "X",
            "expected_output": {"verdict": "KEEP"}, "verification_status": "verified",
        }
        errors = validate_record(record)
        assert errors == []

    def test_expected_output_must_be_dict_or_str(self):
        record = {
            "task_type": "image_validation", "pn": "X",
            "expected_output": [1, 2, 3], "verification_status": "verified",
        }
        errors = validate_record(record)
        assert any("dict or str" in e for e in errors)


class TestCreateGoldenRecord:
    """create_golden_record produces valid records."""

    def test_has_schema_version(self):
        r = create_golden_record("price_extraction", "PN1", {"price": 100}, input_text="t")
        assert r["schema_version"] == GOLDEN_EVAL_SCHEMA_VERSION

    def test_has_timestamps(self):
        r = create_golden_record("spec_extraction", "PN1", {"v": "24V"}, input_text="t")
        assert "created_at" in r
        assert "updated_at" in r

    def test_default_verification_pending(self):
        r = create_golden_record("price_extraction", "PN1", {}, input_text="t")
        assert r["verification_status"] == "pending"


class TestLoadGoldenDataset:
    """load_golden_dataset reads JSONL files and validates."""

    def test_loads_valid_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "price_extraction.jsonl"
            record = create_golden_record(
                "price_extraction", "PN1", {"price": 100}, input_text="text"
            )
            record["verification_status"] = "verified"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            dataset = load_golden_dataset("price_extraction", Path(tmp))
        assert len(dataset) == 1
        assert dataset[0]["pn"] == "PN1"

    def test_skips_invalid_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "price_extraction.jsonl"
            valid = create_golden_record(
                "price_extraction", "PN1", {"price": 100}, input_text="text"
            )
            invalid = {"bad": "record"}  # missing required fields
            path.write_text(
                json.dumps(valid) + "\n" + json.dumps(invalid) + "\n",
                encoding="utf-8",
            )

            dataset = load_golden_dataset("price_extraction", Path(tmp))
        assert len(dataset) == 1

    def test_verified_only_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spec_extraction.jsonl"
            verified = create_golden_record(
                "spec_extraction", "PN1", {"v": "24V"},
                input_text="t", verification_status="verified",
            )
            pending = create_golden_record(
                "spec_extraction", "PN2", {"v": "12V"},
                input_text="t", verification_status="pending",
            )
            path.write_text(
                json.dumps(verified) + "\n" + json.dumps(pending) + "\n",
                encoding="utf-8",
            )

            all_records = load_golden_dataset("spec_extraction", Path(tmp))
            verified_only = load_golden_dataset(
                "spec_extraction", Path(tmp), verified_only=True,
            )
        assert len(all_records) == 2
        assert len(verified_only) == 1

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset = load_golden_dataset("price_extraction", Path(tmp))
        assert dataset == []


class TestSaveGoldenRecord:
    """save_golden_record appends to JSONL."""

    def test_saves_valid_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = create_golden_record(
                "price_extraction", "PN1", {"price": 100}, input_text="t"
            )
            path = save_golden_record(record, Path(tmp))
            assert path.exists()
            loaded = load_golden_dataset("price_extraction", Path(tmp))
            assert len(loaded) == 1

    def test_rejects_invalid_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="Invalid"):
                save_golden_record({"bad": "record"}, Path(tmp))


class TestGoldenSummary:
    """golden_summary returns stats per task type."""

    def test_summary_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(3):
                r = create_golden_record(
                    "price_extraction", f"PN{i}", {"p": i},
                    input_text="t",
                    verification_status="verified" if i < 2 else "pending",
                )
                save_golden_record(r, Path(tmp))

            summary = golden_summary(Path(tmp))
        assert summary["price_extraction"]["total"] == 3
        assert summary["price_extraction"]["verified"] == 2
        assert summary["price_extraction"]["pending"] == 1


class TestSeedDataIntegrity:
    """Seed golden eval files are valid and loadable."""

    _golden_dir = Path(__file__).parent.parent.parent / "golden_eval"

    @pytest.mark.parametrize("task_type", list(VALID_TASK_TYPES))
    def test_seed_files_valid(self, task_type):
        records = load_golden_dataset(task_type, self._golden_dir)
        # Seed files should have at least 2 records each
        assert len(records) >= 2, f"{task_type} seed has only {len(records)} records"

    @pytest.mark.parametrize("task_type", list(VALID_TASK_TYPES))
    def test_all_seed_records_verified(self, task_type):
        records = load_golden_dataset(task_type, self._golden_dir, verified_only=True)
        all_records = load_golden_dataset(task_type, self._golden_dir)
        assert len(records) == len(all_records), (
            f"{task_type}: not all seed records are verified"
        )

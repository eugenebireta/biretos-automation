"""Tests for correction_logger.py (Block 9)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from correction_logger import (
    log_correction,
    log_price_sanity_warning,
    retrospective_peha_corrections,
    retrospective_sanity_warnings,
)


def _read_experience_records(tmp_dir: str) -> list[dict]:
    import datetime
    month = datetime.datetime.utcnow().strftime("%Y-%m")
    path = Path(tmp_dir) / f"experience_{month}.jsonl"
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


class TestLogCorrection:
    def test_writes_record_to_experience_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_correction(
                pn="153711", brand="Honeywell",
                field_corrected="expected_category",
                original_value="Датчик",
                corrected_value="Рамки PEHA",
                reason="PEHA electrical item mislabeled",
                shadow_log_dir=Path(tmp),
            )
            records = _read_experience_records(tmp)

        assert len(records) == 1
        r = records[0]
        assert r["pn"] == "153711"
        assert r["field_corrected"] == "expected_category"
        assert r["original_value"] == "Датчик"
        assert r["corrected_value"] == "Рамки PEHA"
        assert r["salience_score"] == 9
        assert r["task_type"] == "correction"

    def test_summary_max_200_chars(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_correction(
                pn="X" * 100, brand="B",
                field_corrected="f" * 100,
                original_value="o" * 100,
                corrected_value="c" * 100,
                reason="r",
                shadow_log_dir=Path(tmp),
            )
            records = _read_experience_records(tmp)

        assert len(records[0]["summary"]) <= 200

    def test_corrected_by_stored(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_correction(
                pn="111", brand="H",
                field_corrected="price",
                original_value="9999",
                corrected_value="99",
                reason="box price not unit",
                corrected_by="owner",
                shadow_log_dir=Path(tmp),
            )
            records = _read_experience_records(tmp)

        assert records[0]["corrected_by"] == "owner"

    def test_multiple_corrections_appended(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(3):
                log_correction(
                    pn=f"PN{i}", brand="H",
                    field_corrected="field",
                    original_value="wrong",
                    corrected_value="right",
                    reason="test",
                    shadow_log_dir=Path(tmp),
                )
            records = _read_experience_records(tmp)
        assert len(records) == 3


class TestLogPriceSanityWarning:
    def test_writes_warning_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_price_sanity_warning(
                pn="1000106", brand="Honeywell",
                price_usd=0.05,
                flags=["EXOTIC_CURRENCY_HIGH_PIECE_PRICE", "ABSOLUTE_LOW_BOUND"],
                source_url="https://example.com",
                shadow_log_dir=Path(tmp),
            )
            records = _read_experience_records(tmp)

        assert len(records) == 1
        r = records[0]
        assert r["salience_score"] == 7
        assert r["task_type"] == "price_sanity_warning"
        assert "EXOTIC_CURRENCY_HIGH_PIECE_PRICE" in r["flags"]

    def test_warning_summary_max_200_chars(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_price_sanity_warning(
                pn="PN", brand="B", price_usd=1.0,
                flags=["FLAG_" + "X" * 100],
                shadow_log_dir=Path(tmp),
            )
            records = _read_experience_records(tmp)
        assert len(records[0]["summary"]) <= 200


class TestRetrospectivePehaCorrections:
    def test_reads_category_fix_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            fix_path = Path(tmp) / "category_fix_2026-04.jsonl"
            records = [
                {"pn": "153711", "brand": "Honeywell",
                 "original_category": "Датчик",
                 "corrected_category": "Рамки PEHA"},
                {"pn": "155111", "brand": "Honeywell",
                 "old_expected_category": "Вентиль",
                 "new_expected_category": "Клавиши PEHA"},
                {"pn": "157413", "brand": "Honeywell",
                 "original_category": "same", "corrected_category": "same"},  # Should skip
            ]
            with open(fix_path, "w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r) + "\n")

            count = retrospective_peha_corrections(shadow_log_dir=Path(tmp))
            exp_records = _read_experience_records(tmp)

        # 2 real corrections (skips the same->same one)
        assert count == 2
        correction_records = [r for r in exp_records if r.get("task_type") == "correction"]
        assert len(correction_records) == 2
        # All corrections have salience=9
        assert all(r["salience_score"] == 9 for r in correction_records)

    def test_empty_fix_log_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            count = retrospective_peha_corrections(shadow_log_dir=Path(tmp))
        assert count == 0


class TestRetrospectiveSanityWarnings:
    def test_reads_sanity_audit_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            sanity_path = Path(tmp) / "price_sanity_audit_2026-04.jsonl"
            records = [
                {"pn": "1000106", "brand": "Honeywell",
                 "sanity_status": "WARNING", "price_usd": 0.05,
                 "flags": ["EXOTIC_CURRENCY_HIGH_PIECE_PRICE"]},
                {"pn": "1000107", "brand": "Honeywell",
                 "sanity_status": "PASS", "price_usd": 100.0,
                 "flags": []},  # Should skip PASS
            ]
            with open(sanity_path, "w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r) + "\n")

            count = retrospective_sanity_warnings(shadow_log_dir=Path(tmp))
            exp_records = _read_experience_records(tmp)

        assert count == 1
        warning_records = [r for r in exp_records if r.get("task_type") == "price_sanity_warning"]
        assert len(warning_records) == 1
        assert warning_records[0]["salience_score"] == 7

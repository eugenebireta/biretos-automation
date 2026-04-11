"""Tests for correct.py CLI entrypoint."""
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

from correct import main  # noqa: E402


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


class TestCorrectCLI:
    """CLI correction command writes valid records."""

    def test_basic_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            import correction_logger
            orig = correction_logger._SHADOW_LOG_DIR
            correction_logger._SHADOW_LOG_DIR = Path(tmp)
            try:
                code = main([
                    "--pn", "153711",
                    "--field", "expected_category",
                    "--old", "Датчик",
                    "--new", "Рамки PEHA",
                    "--reason", "PEHA electrical item",
                ])
            finally:
                correction_logger._SHADOW_LOG_DIR = orig

            assert code == 0
            records = _read_experience_records(tmp)
            assert len(records) == 1
            r = records[0]
            assert r["pn"] == "153711"
            assert r["field_corrected"] == "expected_category"
            assert r["original_value"] == "Датчик"
            assert r["corrected_value"] == "Рамки PEHA"
            assert r["salience_score"] == 9

    def test_all_optional_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            import correction_logger
            orig = correction_logger._SHADOW_LOG_DIR
            correction_logger._SHADOW_LOG_DIR = Path(tmp)
            try:
                code = main([
                    "--pn", "185191",
                    "--field", "price",
                    "--old", "450.0",
                    "--new", "45.0",
                    "--reason", "pack price not unit",
                    "--brand", "PEHA",
                    "--source", "dr_gemini",
                    "--trace-id", "trace_abc",
                    "--ai-model", "gemini-2.5-pro",
                    "--ai-output", '{"price": 450}',
                    "--corrected-by", "owner",
                ])
            finally:
                correction_logger._SHADOW_LOG_DIR = orig

            assert code == 0
            records = _read_experience_records(tmp)
            r = records[0]
            assert r["brand"] == "PEHA"
            assert r["source"] == "dr_gemini"
            assert r["trace_id"] == "trace_abc"
            assert r["ai_model"] == "gemini-2.5-pro"
            assert r["ai_output_raw"] == '{"price": 450}'
            assert r["corrected_by"] == "owner"

    def test_json_output(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            import correction_logger
            orig = correction_logger._SHADOW_LOG_DIR
            correction_logger._SHADOW_LOG_DIR = Path(tmp)
            try:
                main([
                    "--pn", "PN1", "--field", "f",
                    "--old", "a", "--new", "b",
                    "--reason", "test", "--json",
                ])
            finally:
                correction_logger._SHADOW_LOG_DIR = orig

            output = json.loads(capsys.readouterr().out)
            assert output["status"] == "ok"
            assert output["pn"] == "PN1"

    def test_default_brand_is_honeywell(self):
        with tempfile.TemporaryDirectory() as tmp:
            import correction_logger
            orig = correction_logger._SHADOW_LOG_DIR
            correction_logger._SHADOW_LOG_DIR = Path(tmp)
            try:
                main(["--pn", "X", "--field", "f", "--old", "a", "--new", "b", "--reason", "r"])
            finally:
                correction_logger._SHADOW_LOG_DIR = orig

            records = _read_experience_records(tmp)
            assert records[0]["brand"] == "Honeywell"

    def test_optional_fields_default_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            import correction_logger
            orig = correction_logger._SHADOW_LOG_DIR
            correction_logger._SHADOW_LOG_DIR = Path(tmp)
            try:
                main(["--pn", "X", "--field", "f", "--old", "a", "--new", "b", "--reason", "r"])
            finally:
                correction_logger._SHADOW_LOG_DIR = orig

            r = _read_experience_records(tmp)[0]
            assert r["trace_id"] is None
            assert r["source"] is None
            assert r["ai_model"] is None
            assert r["ai_output_raw"] is None

    def test_missing_required_args_exits(self):
        with pytest.raises(SystemExit):
            main(["--pn", "X"])  # missing --field, --old, --new, --reason

    def test_schema_version_is_v2(self):
        with tempfile.TemporaryDirectory() as tmp:
            import correction_logger
            orig = correction_logger._SHADOW_LOG_DIR
            correction_logger._SHADOW_LOG_DIR = Path(tmp)
            try:
                main(["--pn", "X", "--field", "f", "--old", "a", "--new", "b", "--reason", "r"])
            finally:
                correction_logger._SHADOW_LOG_DIR = orig

            r = _read_experience_records(tmp)[0]
            assert r["schema_version"] == "correction_v2"

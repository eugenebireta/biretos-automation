"""Tests for spec extraction shadow logging and training export.

Proves that:
1. spec_extractor.py extracts specs from HTML (heuristic, no LLM)
2. shadow_log receives spec extraction records with page_text_snippet
3. training_dataset_export includes spec_extraction dataset
4. SPEC_EXTRACTION_VERSION constant is defined and well-formed
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


class TestSpecExtractor:
    """spec_extractor.py heuristic extraction from HTML."""

    def test_extracts_from_two_column_table(self):
        from spec_extractor import extract_specs_from_html

        html = """
        <html><body>
        <table>
            <tr><td>Voltage</td><td>24V DC</td></tr>
            <tr><td>Power</td><td>15W</td></tr>
            <tr><td>Weight</td><td>0.5 kg</td></tr>
        </table>
        </body></html>
        """
        specs = extract_specs_from_html(html, "TEST-PN")
        assert len(specs) >= 2
        assert "voltage" in specs
        assert specs["voltage"] == "24V DC"

    def test_extracts_from_definition_list(self):
        from spec_extractor import extract_specs_from_html

        html = """
        <html><body>
        <dl>
            <dt>Protocol</dt><dd>BACnet</dd>
            <dt>Temperature Range</dt><dd>-20 to 60°C</dd>
        </dl>
        </body></html>
        """
        specs = extract_specs_from_html(html)
        assert len(specs) >= 2
        assert "protocol" in specs
        assert specs["protocol"] == "BACnet"

    def test_returns_empty_for_no_specs(self):
        from spec_extractor import extract_specs_from_html

        html = "<html><body><p>No specs here</p></body></html>"
        specs = extract_specs_from_html(html)
        assert specs == {}

    def test_never_raises(self):
        from spec_extractor import extract_specs_from_html

        # Garbage input should not raise
        result = extract_specs_from_html("not html at all <<<>>>")
        assert isinstance(result, dict)

    def test_caps_at_max_specs(self):
        from spec_extractor import extract_specs_from_html, _MAX_SPECS

        rows = "\n".join(
            f"<tr><td>Param{i}</td><td>Value{i}</td></tr>"
            for i in range(_MAX_SPECS + 20)
        )
        html = f"<html><body><table>{rows}</table></body></html>"
        specs = extract_specs_from_html(html)
        assert len(specs) <= _MAX_SPECS


class TestSpecExtractionShadowLog:
    """shadow_log() receives spec extraction records."""

    def test_spec_extraction_record_written(self):
        import photo_pipeline as pp

        with tempfile.TemporaryDirectory() as tmp:
            orig_dir = pp.SHADOW_LOG_DIR
            pp.SHADOW_LOG_DIR = Path(tmp)
            try:
                pp.shadow_log(
                    task_type="spec_extraction",
                    pn="TEST-PN",
                    brand="Honeywell",
                    model="heuristic",
                    provider="local",
                    model_alias="spec_extractor",
                    model_resolved="spec_extractor_v1",
                    prompt="Sample page text with specs table",
                    response_raw='{"voltage": "24V"}',
                    response_parsed={"voltage": "24V"},
                    parse_success=True,
                    source_url="https://example.com/product",
                    prompt_version=pp.SPEC_EXTRACTION_VERSION,
                    pipeline_stage="spec_extraction",
                )
            finally:
                pp.SHADOW_LOG_DIR = orig_dir

            month = datetime.datetime.utcnow().strftime("%Y-%m")
            path = Path(tmp) / f"spec_extraction_{month}.jsonl"
            assert path.exists()
            record = json.loads(path.read_text(encoding="utf-8").strip())

        assert record["task_type"] == "spec_extraction"
        assert record["pn"] == "TEST-PN"
        assert record["prompt_version"] == "spec_heuristic_v1"
        assert record["pipeline_stage"] == "spec_extraction"
        assert record["provider"] == "local"
        assert record["model"] == "heuristic"
        assert record["response_parsed"] == {"voltage": "24V"}
        assert record["prompt"] == "Sample page text with specs table"
        assert record["schema_version"] == "photo_pipeline_shadow_log_record_v2"

    def test_page_text_snippet_preserved(self):
        """The raw page text (input signal) is stored as prompt field."""
        import photo_pipeline as pp

        long_text = "x" * 5000
        with tempfile.TemporaryDirectory() as tmp:
            orig_dir = pp.SHADOW_LOG_DIR
            pp.SHADOW_LOG_DIR = Path(tmp)
            try:
                pp.shadow_log(
                    task_type="spec_extraction",
                    pn="PN", brand="B",
                    model="heuristic", provider="local",
                    model_alias="spec_extractor",
                    model_resolved="spec_extractor_v1",
                    prompt=long_text[:pp._MAX_PAGE_TEXT_SNIPPET],
                    response_raw="{}",
                    response_parsed={},
                    parse_success=True,
                    prompt_version=pp.SPEC_EXTRACTION_VERSION,
                )
            finally:
                pp.SHADOW_LOG_DIR = orig_dir

            month = datetime.datetime.utcnow().strftime("%Y-%m")
            path = Path(tmp) / f"spec_extraction_{month}.jsonl"
            record = json.loads(path.read_text(encoding="utf-8").strip())

        assert len(record["prompt"]) == pp._MAX_PAGE_TEXT_SNIPPET


class TestSpecExtractionVersionConstant:
    """SPEC_EXTRACTION_VERSION exists and is well-formed."""

    def test_constant_defined(self):
        import photo_pipeline as pp
        assert isinstance(pp.SPEC_EXTRACTION_VERSION, str)
        assert len(pp.SPEC_EXTRACTION_VERSION) > 0
        assert pp.SPEC_EXTRACTION_VERSION.startswith("spec_")

    def test_max_page_text_snippet_defined(self):
        import photo_pipeline as pp
        assert isinstance(pp._MAX_PAGE_TEXT_SNIPPET, int)
        assert pp._MAX_PAGE_TEXT_SNIPPET >= 1000


class TestSpecExtractionExport:
    """training_dataset_export includes spec_extraction dataset."""

    def test_spec_export_from_shadow_log(self):
        from training_dataset_export import export_spec_extraction_dataset

        with tempfile.TemporaryDirectory() as tmp:
            month = datetime.datetime.utcnow().strftime("%Y-%m")
            path = Path(tmp) / f"spec_extraction_{month}.jsonl"
            record = {
                "pn": "PN1", "brand": "Honeywell",
                "prompt": "page text here",
                "response_raw": '{"voltage": "24V"}',
                "response_parsed": {"voltage": "24V"},
                "model": "heuristic",
                "model_resolved": "spec_extractor_v1",
                "prompt_version": "spec_heuristic_v1",
                "pipeline_stage": "spec_extraction",
                "source_url": "https://example.com",
                "ts": "2026-04-10T00:00:00Z",
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            dataset = export_spec_extraction_dataset(Path(tmp))

        assert len(dataset) == 1
        assert dataset[0]["dataset"] == "spec_extraction"
        assert dataset[0]["pn"] == "PN1"
        assert dataset[0]["page_text_snippet"] == "page text here"
        assert dataset[0]["extracted_specs"] == {"voltage": "24V"}
        assert dataset[0]["spec_count"] == 1
        assert dataset[0]["prompt_version"] == "spec_heuristic_v1"

    def test_empty_specs_skipped(self):
        from training_dataset_export import export_spec_extraction_dataset

        with tempfile.TemporaryDirectory() as tmp:
            month = datetime.datetime.utcnow().strftime("%Y-%m")
            path = Path(tmp) / f"spec_extraction_{month}.jsonl"
            record = {
                "pn": "PN1", "brand": "B",
                "prompt": "text",
                "response_raw": "{}",
                "response_parsed": {},
                "ts": "2026-04-10T00:00:00Z",
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            dataset = export_spec_extraction_dataset(Path(tmp))

        assert len(dataset) == 0  # empty specs skipped

    def test_old_records_without_v2_fields(self):
        from training_dataset_export import export_spec_extraction_dataset

        with tempfile.TemporaryDirectory() as tmp:
            month = datetime.datetime.utcnow().strftime("%Y-%m")
            path = Path(tmp) / f"spec_extraction_{month}.jsonl"
            record = {
                "pn": "PN1", "brand": "B",
                "prompt": "text",
                "response_parsed": {"key": "val"},
                "ts": "2026-04-10T00:00:00Z",
                # NO prompt_version, model_resolved, pipeline_stage
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            dataset = export_spec_extraction_dataset(Path(tmp))

        assert len(dataset) == 1
        assert dataset[0]["prompt_version"] is None
        assert dataset[0]["model_resolved"] == ""
        assert dataset[0]["pipeline_stage"] == ""


class TestTrainingLoggerRemoved:
    """training_logger.py has been deleted — no imports should work."""

    def test_training_logger_not_importable(self):
        with pytest.raises(ImportError):
            import training_logger  # noqa: F401

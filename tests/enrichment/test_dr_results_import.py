"""Tests for dr_results_import.py — DR markdown file importer."""
from __future__ import annotations

import json
import sys
import os
import tempfile
from pathlib import Path

_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from dr_results_import import (  # noqa: E402
    _parse_table_rows,
    _clean_value,
    _is_not_found,
    _build_price_value,
    _build_result_json,
    _determine_confidence,
    _determine_provider,
    _parse_table2_rows,
    import_file,
)

GPT_TABLE1 = """
### Table 1 — Product data

| # | PN | Price | Currency | Price_Type | Source URL | Category | Image URL | Alias | Specs | Notes |
|---|----|----|---|---|---|---|---|---|---|---|
| 1 | N05010 | 176.78 | USD | distributor | https://example.com/n05010 | Damper actuator | https://example.com/img.jpg | HON228 | 5Nm; 24VAC | Refurbished |
| 2 | N05230 | not found |  | not found | not found | not found | not found |  |  |  |
"""

CLAUDE_TABLE1 = """
## Таблица результатов

| # | PN | Price | Currency | Source URL | Category | Image URL | Notes |
|---|----|----|---|---|---|---|---|
| 1 | V5050A1090 | 2060.10 | CHF | https://example.com | 3-ходовой клапан | https://example.com/img.jpg | Фланцевый DN100 |
| 2 | PANC300-03 | not found |  | not found | not found | not found |  |
"""

TABLE2_SAMPLE = """
### Table 2 — Every URL visited (for training local AI)

| # | PN | URL | Page_Type | Has_Price | Has_Specs | Has_Photo | Domain |
|---|----|----|---|---|---|---|---|
| 1 | N05010 | https://example.com/n05010 | distributor | yes | yes | yes | example.com |
| 2 | N05010 | https://mfr.com/n05010 | manufacturer | no | yes | no | mfr.com |
"""


class TestCleanValue:
    def test_strips_citations(self):
        assert _clean_value("176.78【6†L785-L789】") == "176.78"

    def test_strips_whitespace(self):
        assert _clean_value("  hello  ") == "hello"

    def test_empty_string(self):
        assert _clean_value("") == ""


class TestIsNotFound:
    def test_not_found_string(self):
        assert _is_not_found("not found")

    def test_dash(self):
        assert _is_not_found("–")

    def test_empty(self):
        assert _is_not_found("")

    def test_valid_value(self):
        assert not _is_not_found("176.78")

    def test_url(self):
        assert not _is_not_found("https://example.com")


class TestParseTableRows:
    def test_gpt_table_parsed(self):
        lines = GPT_TABLE1.splitlines()
        rows = _parse_table_rows(lines)
        assert len(rows) == 2
        assert rows[0]["PN"] == "N05010"
        assert rows[0]["Price"] == "176.78"
        assert rows[1]["PN"] == "N05230"

    def test_claude_table_parsed(self):
        lines = CLAUDE_TABLE1.splitlines()
        rows = _parse_table_rows(lines)
        assert len(rows) == 2
        assert rows[0]["PN"] == "V5050A1090"
        assert rows[0]["Price"] == "2060.10"


class TestBuildPriceValue:
    def test_gpt_row_with_price(self):
        row = {"Price": "176.78【6†L785】", "Currency": "USD", "Source URL": "https://x.com", "Price_Type": "distributor"}
        result = _build_price_value(row)
        assert result is not None
        assert result["amount"] == 176.78
        assert result["currency"] == "USD"

    def test_not_found_returns_none(self):
        row = {"Price": "not found", "Currency": "", "Source URL": ""}
        assert _build_price_value(row) is None

    def test_chf_price(self):
        row = {"Price": "2060.10", "Currency": "CHF", "Source URL": "https://x.com"}
        result = _build_price_value(row)
        assert result["currency"] == "CHF"
        assert result["amount"] == 2060.10


class TestDetermineConfidence:
    def test_price_and_image_is_medium(self):
        row = {"Price": "100", "Currency": "USD", "Image URL": "https://img.jpg", "Category": "not found"}
        assert _determine_confidence(row) == "medium"

    def test_all_found_is_medium(self):
        row = {"Price": "100", "Currency": "USD", "Image URL": "https://img.jpg", "Category": "Valve"}
        assert _determine_confidence(row) == "medium"

    def test_only_category_is_low(self):
        row = {"Price": "not found", "Currency": "", "Image URL": "not found", "Category": "Valve"}
        assert _determine_confidence(row) == "low"


class TestDetermineProvider:
    def test_compass_is_gpt(self):
        assert _determine_provider("compass_artifact_wf-abc.md") == "dr_gpt"

    def test_deep_research_is_gemini(self):
        assert _determine_provider("deep-research-report.md") == "dr_gemini"


class TestBuildResultJson:
    def test_gpt_row_builds_result(self):
        row = {
            "PN": "N05010", "Price": "176.78", "Currency": "USD",
            "Price_Type": "distributor", "Source URL": "https://x.com",
            "Category": "Damper actuator", "Image URL": "https://img.jpg",
            "Alias": "HON228", "Specs": "5Nm; 24VAC", "Notes": "Refurbished",
        }
        result = _build_result_json(row, "dr_gpt", "compass_test.md")
        assert result is not None
        assert result["entity_id"] == "N05010"
        assert result["final_recommendation"]["price_value"]["amount"] == 176.78
        assert result["final_recommendation"]["photo_url"] == "https://img.jpg"
        assert result["provider"] == "dr_gpt"

    def test_not_found_row_returns_none(self):
        row = {"PN": "PANC300", "Price": "not found", "Currency": "", "Source URL": "not found",
               "Category": "not found", "Image URL": "not found"}
        assert _build_result_json(row, "dr_gpt", "test.md") is None

    def test_surplus_price_type_is_ambiguous(self):
        row = {"PN": "X1", "Price": "100", "Currency": "USD", "Price_Type": "surplus",
               "Source URL": "https://x.com", "Category": "Tool", "Image URL": "not found"}
        result = _build_result_json(row, "dr_gpt", "test.md")
        assert result["final_recommendation"]["price_assessment"] == "ambiguous_offer"
        assert result["confidence"] == "low"


class TestParseTable2Rows:
    def test_table2_parsed(self):
        rows = _parse_table2_rows(TABLE2_SAMPLE, "test.md", "dr_gpt")
        assert len(rows) == 2
        assert rows[0]["pn"] == "N05010"
        assert rows[0]["has_price"] is True
        assert rows[0]["has_photo"] is True
        assert rows[1]["has_price"] is False

    def test_no_table2_returns_empty(self):
        rows = _parse_table2_rows("No table 2 here", "test.md", "dr_gpt")
        assert rows == []


class TestImportFile:
    def _make_markdown_file(self, content: str) -> Path:
        tmp = tempfile.mktemp(suffix=".md")
        Path(tmp).write_text(content, encoding="utf-8")
        return Path(tmp)

    def test_import_gpt_file(self):
        md = self._make_markdown_file(GPT_TABLE1 + "\n\n" + TABLE2_SAMPLE)
        with tempfile.TemporaryDirectory() as results_tmp, \
             tempfile.TemporaryDirectory() as training_tmp:
            stats = import_file(
                md,
                Path(results_tmp),
                Path(training_tmp),
                dry_run=False,
            )
        assert stats["written"] == 1  # N05010 has data, N05230 is skipped
        assert stats["urls"] == 2     # 2 Table 2 rows
        md.unlink(missing_ok=True)

    def test_dry_run_does_not_write(self):
        md = self._make_markdown_file(GPT_TABLE1)
        with tempfile.TemporaryDirectory() as results_tmp, \
             tempfile.TemporaryDirectory() as training_tmp:
            stats = import_file(md, Path(results_tmp), Path(training_tmp), dry_run=True)
            result_files = list(Path(results_tmp).glob("*.json"))
        assert stats["written"] == 1  # counted but not written
        assert len(result_files) == 0  # nothing actually written
        md.unlink(missing_ok=True)

    def test_result_json_has_required_fields(self):
        md = self._make_markdown_file(GPT_TABLE1)
        with tempfile.TemporaryDirectory() as results_tmp, \
             tempfile.TemporaryDirectory() as training_tmp:
            import_file(md, Path(results_tmp), Path(training_tmp))
            files = list(Path(results_tmp).glob("*.json"))
            assert len(files) == 1
            data = json.loads(files[0].read_text())
        assert "entity_id" in data
        assert "final_recommendation" in data
        assert "confidence" in data
        assert "timestamp" in data
        md.unlink(missing_ok=True)

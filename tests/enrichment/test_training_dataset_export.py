"""Tests for training_dataset_export.py (Block 8)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from training_dataset_export import (
    export_price_extraction_dataset,
    export_photo_verdict_dataset,
    export_category_classification_dataset,
    export_search_strategy_dataset,
    export_all_datasets,
    _read_jsonl,
)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class TestReadJsonl:
    def test_reads_valid_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.jsonl"
            _write_jsonl(p, [{"a": 1}, {"b": 2}])
            records = _read_jsonl(p)
        assert len(records) == 2

    def test_missing_file_returns_empty(self):
        records = _read_jsonl(Path("/nonexistent/file.jsonl"))
        assert records == []

    def test_skips_malformed_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.jsonl"
            p.write_text('{"a": 1}\nNOT JSON\n{"b": 2}\n', encoding="utf-8")
            records = _read_jsonl(p)
        assert len(records) == 2


class TestExportPriceExtraction:
    def test_skips_null_response_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "price_extraction_2026-04.jsonl"
            _write_jsonl(p, [
                {"pn": "A", "brand": "B", "response_raw": None,
                 "parse_success": True, "response_parsed": {"pn_found": True}},
                {"pn": "C", "brand": "D", "response_raw": '{"pn_found": true}',
                 "parse_success": True, "response_parsed": {"pn_found": True}},
            ])
            result = export_price_extraction_dataset(shadow_dir=Path(tmp))
        assert len(result) == 1
        assert result[0]["pn"] == "C"

    def test_skips_empty_response_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "price_extraction_2026-04.jsonl"
            _write_jsonl(p, [
                {"pn": "A", "brand": "B", "response_raw": "",
                 "parse_success": False, "response_parsed": {}},
            ])
            result = export_price_extraction_dataset(shadow_dir=Path(tmp))
        assert result == []

    def test_includes_valid_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "price_extraction_2026-04.jsonl"
            _write_jsonl(p, [
                {"pn": "153711", "brand": "Honeywell",
                 "response_raw": '{"pn_found": true, "price_per_unit": 12.5}',
                 "parse_success": True,
                 "response_parsed": {"pn_found": True, "pn_exact_confirmed": True},
                 "prompt": "Extract price...", "model": "claude-haiku",
                 "source_url": "https://shop.de", "source_type": "web", "ts": "2026-04-08"},
            ])
            result = export_price_extraction_dataset(shadow_dir=Path(tmp))
        assert len(result) == 1
        assert result[0]["pn"] == "153711"
        assert "prompt" in result[0]
        assert "response_raw" in result[0]


class TestExportPhotoVerdict:
    def test_includes_verdict_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "image_validation_2026-04.jsonl"
            _write_jsonl(p, [
                {"pn": "153711", "brand": "H",
                 "response_raw": "KEEP",
                 "parse_success": True,
                 "response_parsed": {"verdict": "KEEP", "reason": "matches"},
                 "model": "claude-sonnet", "ts": "2026-04-08"},
            ])
            result = export_photo_verdict_dataset(shadow_dir=Path(tmp))
        assert len(result) == 1
        assert result[0]["verdict"] == "KEEP"

    def test_skips_null_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "image_validation_2026-04.jsonl"
            _write_jsonl(p, [
                {"pn": "X", "response_raw": None,
                 "response_parsed": {"verdict": "KEEP"}},
            ])
            result = export_photo_verdict_dataset(shadow_dir=Path(tmp))
        assert result == []


class TestExportCategoryClassification:
    def test_reads_from_evidence_bundles(self):
        with tempfile.TemporaryDirectory() as tmp_ev:
            ev_dir = Path(tmp_ev)
            bundle = {
                "pn": "153711", "brand": "Honeywell",
                "assembled_title": "Рамка PEHA NOVA",
                "expected_category": "Рамки PEHA",
                "card_status": "REVIEW_REQUIRED",
                "price": {"page_product_class": "Electrical"},
            }
            (ev_dir / "evidence_153711.json").write_text(
                json.dumps(bundle), encoding="utf-8"
            )
            with tempfile.TemporaryDirectory() as tmp_sh:
                result = export_category_classification_dataset(
                    evidence_dir=ev_dir, shadow_dir=Path(tmp_sh)
                )
        assert len(result) == 1
        assert result[0]["correct_category"] == "Рамки PEHA"
        assert result[0]["correction"] is False

    def test_includes_corrections_from_fix_log(self):
        with tempfile.TemporaryDirectory() as tmp_sh:
            p = Path(tmp_sh) / "category_fix_2026-04.jsonl"
            _write_jsonl(p, [
                {"pn": "153711", "brand": "Honeywell",
                 "original_category": "Датчик",
                 "corrected_category": "Рамки PEHA",
                 "assembled_title": "Frame PEHA"},
            ])
            with tempfile.TemporaryDirectory() as tmp_ev:
                result = export_category_classification_dataset(
                    evidence_dir=Path(tmp_ev), shadow_dir=Path(tmp_sh)
                )
        corrections = [r for r in result if r.get("correction")]
        assert len(corrections) == 1
        assert corrections[0]["original_category"] == "Датчик"


class TestExportSearchStrategy:
    def test_reads_brand_enrichment_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "experience_2026-04.jsonl"
            _write_jsonl(p, [
                {"task_type": "brand_enrichment", "pn": "153711", "brand": "Honeywell",
                 "pn_family": "PEHA",
                 "sources_worked": ["conrad.de"],
                 "sources_failed": ["honeywell.com"],
                 "price_found": True, "training_label": "partial",
                 "decision": "REVIEW_REQUIRED", "ts": "2026-04-08"},
            ])
            result = export_search_strategy_dataset(shadow_dir=Path(tmp))
        assert len(result) == 1
        assert result[0]["pn_family"] == "PEHA"
        assert "sources_worked" in result[0]

    def test_skips_non_brand_enrichment(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "experience_2026-04.jsonl"
            _write_jsonl(p, [
                {"task_type": "card_finalization", "pn": "X",
                 "sources_worked": ["site.com"]},
            ])
            result = export_search_strategy_dataset(shadow_dir=Path(tmp))
        assert result == []


class TestExportAllDatasets:
    def test_creates_output_files(self):
        with tempfile.TemporaryDirectory() as tmp_out, \
             tempfile.TemporaryDirectory() as tmp_sh, \
             tempfile.TemporaryDirectory() as tmp_ev:
            stats = export_all_datasets(
                output_dir=Path(tmp_out),
                shadow_dir=Path(tmp_sh),
                evidence_dir=Path(tmp_ev),
            )
        assert isinstance(stats, dict)
        assert "price_extraction" in stats
        assert "photo_verdict" in stats
        assert "category_classification" in stats
        assert "search_strategy" in stats

    def test_summary_file_written(self):
        with tempfile.TemporaryDirectory() as tmp_out, \
             tempfile.TemporaryDirectory() as tmp_sh, \
             tempfile.TemporaryDirectory() as tmp_ev:
            export_all_datasets(
                output_dir=Path(tmp_out),
                shadow_dir=Path(tmp_sh),
                evidence_dir=Path(tmp_ev),
            )
            summary_path = Path(tmp_out) / "export_summary.json"
            assert summary_path.exists()
            summary = json.loads(summary_path.read_text())
        assert "total" in summary
        assert "datasets" in summary

    def test_roundtrip_readable(self):
        with tempfile.TemporaryDirectory() as tmp_out, \
             tempfile.TemporaryDirectory() as tmp_sh, \
             tempfile.TemporaryDirectory() as tmp_ev:
            # Write a sample price extraction record
            p = Path(tmp_sh) / "price_extraction_2026-04.jsonl"
            _write_jsonl(p, [{
                "pn": "153711", "brand": "Honeywell",
                "response_raw": '{"pn_found": true}',
                "parse_success": True,
                "response_parsed": {"pn_found": True, "pn_exact_confirmed": True},
                "prompt": "test", "model": "haiku", "ts": "2026-04-08",
            }])
            export_all_datasets(
                output_dir=Path(tmp_out),
                shadow_dir=Path(tmp_sh),
                evidence_dir=Path(tmp_ev),
            )
            out_path = Path(tmp_out) / "price_extraction.json"
            data = json.loads(out_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert data[0]["pn"] == "153711"

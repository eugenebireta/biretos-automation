"""Tests for corpus_status.py — corpus readiness report."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from corpus_status import corpus_status, format_report  # noqa: E402


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


class TestCorpusStatus:
    """corpus_status() counts records correctly."""

    def test_counts_price_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_jsonl(Path(tmp) / "price_extraction_2026-04.jsonl", [
                {"pn": "PN1", "response_raw": '{"ok": true}',
                 "prompt_version": "v11", "ts": "2026-04-10T00:00:00Z"},
                {"pn": "PN2", "response_raw": None, "ts": "2026-04-10T00:00:00Z"},
                {"pn": "PN3", "response_raw": '{"ok": true}',
                 "prompt_version": "v11", "trace_id": "t1",
                 "ts": "2026-04-10T00:00:00Z"},
            ])
            report = corpus_status(shadow_dir=Path(tmp), golden_dir=Path(tmp))

        pe = report["tasks"]["price_extraction"]
        assert pe["total"] == 3
        assert pe["with_response"] == 2
        assert pe["with_prompt_version"] == 2
        assert pe["with_trace_id"] == 1

    def test_counts_spec_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_jsonl(Path(tmp) / "spec_extraction_2026-04.jsonl", [
                {"pn": "PN1", "response_raw": "{}", "prompt_version": "spec_v1", "ts": "2026-04-10T00:00:00Z"},
            ])
            report = corpus_status(shadow_dir=Path(tmp), golden_dir=Path(tmp))

        assert report["tasks"]["spec_extraction"]["total"] == 1

    def test_counts_corrections(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_jsonl(Path(tmp) / "experience_2026-04.jsonl", [
                {"task_type": "correction", "pn": "PN1", "trace_id": "t1",
                 "source": "dr_gemini", "ai_model": "gemini",
                 "ts": "2026-04-10T00:00:00Z"},
                {"task_type": "correction", "pn": "PN2", "ts": "2026-04-10T00:00:00Z"},
                {"task_type": "price_sanity_warning", "pn": "PN3", "ts": "2026-04-10T00:00:00Z"},
                {"task_type": "brand_enrichment", "pn": "PN4", "ts": "2026-04-10T00:00:00Z"},
            ])
            report = corpus_status(shadow_dir=Path(tmp), golden_dir=Path(tmp))

        corr = report["tasks"]["correction"]
        assert corr["total"] == 2
        assert corr["with_trace_id"] == 1
        assert corr["with_source"] == 1
        assert corr["with_ai_model"] == 1
        assert corr["sanity_warnings"] == 1

    def test_empty_dir_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = corpus_status(shadow_dir=Path(tmp), golden_dir=Path(tmp))

        assert report["totals"]["total_records"] == 0
        assert report["totals"]["overall_ready"] is False

    def test_finetune_readiness_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Write enough records to pass threshold
            records = [
                {"pn": f"PN{i}", "response_raw": "{}", "ts": "2026-04-10T00:00:00Z"}
                for i in range(600)
            ]
            _write_jsonl(Path(tmp) / "price_extraction_2026-04.jsonl", records)

            report = corpus_status(shadow_dir=Path(tmp), golden_dir=Path(tmp))

        pe = report["tasks"]["price_extraction"]
        assert pe["finetune_ready"] is True
        assert pe["records_needed"] == 0

    def test_totals_computed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_jsonl(Path(tmp) / "price_extraction_2026-04.jsonl", [
                {"pn": "PN1", "ts": "2026-04-10T00:00:00Z"},
            ])
            _write_jsonl(Path(tmp) / "spec_extraction_2026-04.jsonl", [
                {"pn": "PN2", "ts": "2026-04-10T00:00:00Z"},
            ])
            report = corpus_status(shadow_dir=Path(tmp), golden_dir=Path(tmp))

        assert report["totals"]["total_records"] >= 2


class TestFormatReport:
    """format_report produces readable output."""

    def test_format_includes_task_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = corpus_status(shadow_dir=Path(tmp), golden_dir=Path(tmp))
            text = format_report(report)

        assert "price_extraction" in text
        assert "spec_extraction" in text
        assert "CORPUS STATUS" in text
        assert "TOTAL" in text

    def test_format_shows_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = corpus_status(shadow_dir=Path(tmp), golden_dir=Path(tmp))
            text = format_report(report)

        assert "NOT READY" in text or "READY" in text


class TestCorpusStatusOnRealData:
    """Run corpus_status on actual shadow_log/ for smoke test."""

    _shadow_dir = Path(__file__).parent.parent.parent / "shadow_log"

    def test_real_shadow_log_loads(self):
        if not self._shadow_dir.exists():
            return  # Skip if no real data
        report = corpus_status(shadow_dir=self._shadow_dir)
        # Price extraction should have records from production
        assert report["tasks"]["price_extraction"]["total"] > 0

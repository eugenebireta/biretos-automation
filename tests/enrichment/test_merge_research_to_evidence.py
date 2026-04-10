"""
test_merge_research_to_evidence.py — Deterministic tests for merge script.

All tests use tmp dirs — no real files touched.
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path

import pytest

_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import merge_research_to_evidence as merge


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_dirs(tmp_path):
    """Redirect RESULTS_DIR and EVIDENCE_DIR to temp."""
    orig_results = merge.RESULTS_DIR
    orig_evidence = merge.EVIDENCE_DIR

    results_dir = tmp_path / "research_results"
    evidence_dir = tmp_path / "evidence"
    results_dir.mkdir()
    evidence_dir.mkdir()

    merge.RESULTS_DIR = results_dir
    merge.EVIDENCE_DIR = evidence_dir

    yield tmp_path, results_dir, evidence_dir

    merge.RESULTS_DIR = orig_results
    merge.EVIDENCE_DIR = orig_evidence


def _write_result(results_dir: Path, pn: str, fr: dict, **kwargs) -> None:
    data = {
        "result_version": "v1",
        "entity_id": pn,
        "confidence": kwargs.get("confidence", "medium"),
        "final_recommendation": fr,
    }
    (results_dir / f"result_{pn}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def _write_evidence(evidence_dir: Path, pn: str, **kwargs) -> None:
    data = {
        "schema_version": "evidence_v2",
        "pn": pn,
        "brand": kwargs.get("brand", "Honeywell"),
        "assembled_title": kwargs.get("assembled_title", f"Product {pn}"),
        "card_status": kwargs.get("card_status", "DRAFT_ONLY"),
    }
    data.update(kwargs.get("extra", {}))
    (evidence_dir / f"evidence_{pn}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# _is_empty
# ---------------------------------------------------------------------------

class TestIsEmpty:
    def test_none_is_empty(self):
        assert merge._is_empty(None) is True

    def test_blank_string_is_empty(self):
        assert merge._is_empty("") is True
        assert merge._is_empty("  ") is True

    def test_not_found_is_empty(self):
        assert merge._is_empty("NOT_FOUND") is True
        assert merge._is_empty("not found") is True

    def test_real_value_not_empty(self):
        assert merge._is_empty("Клапан Honeywell") is False

    def test_empty_dict_is_empty(self):
        assert merge._is_empty({}) is True

    def test_filled_dict_not_empty(self):
        assert merge._is_empty({"a": 1}) is False

    def test_number_not_empty(self):
        assert merge._is_empty(42) is False


# ---------------------------------------------------------------------------
# _is_garbage_description
# ---------------------------------------------------------------------------

class TestIsGarbageDescription:
    def test_empty_is_garbage(self):
        assert merge._is_garbage_description("") is True

    def test_short_is_garbage(self):
        assert merge._is_garbage_description("abc") is True

    def test_citeturn_is_garbage(self):
        assert merge._is_garbage_description("citeturn42view0turn43view0") is True

    def test_citeturn_with_unicode_pua_is_garbage(self):
        assert merge._is_garbage_description("\ue200cite\ue202turn42view0\ue202turn43view0\ue201") is True

    def test_normal_description_not_garbage(self):
        assert merge._is_garbage_description(
            "Двухходовой линейный регулирующий клапан PN16 с резьбовым подключением"
        ) is False


# ---------------------------------------------------------------------------
# merge_one
# ---------------------------------------------------------------------------

class TestMergeOne:
    def test_no_result_returns_no_result(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_evidence(evidence_dir, "ABC123")
        status = merge.merge_one("ABC123")
        assert status["action"] == "no_result"

    def test_no_evidence_returns_no_evidence(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "ABC123", {"identity_confirmed": True, "title_ru": "Test"})
        status = merge.merge_one("ABC123")
        assert status["action"] == "no_evidence"

    def test_identity_false_skipped(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "ABC123", {
            "identity_confirmed": False,
            "title_ru": "Fake product",
        })
        _write_evidence(evidence_dir, "ABC123")
        status = merge.merge_one("ABC123")
        assert status["action"] == "skipped"
        assert "identity" in status["reason"]

    def test_merge_title_ru(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "V5011", {
            "identity_confirmed": True,
            "title_ru": "Двухходовой клапан PN16",
        })
        _write_evidence(evidence_dir, "V5011")
        status = merge.merge_one("V5011")
        assert status["action"] == "merged"
        assert "title_ru" in status["fields_added"]
        # Verify written
        ev = json.loads((evidence_dir / "evidence_V5011.json").read_text("utf-8"))
        assert ev["deep_research"]["title_ru"] == "Двухходовой клапан PN16"

    def test_merge_description_ru(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "V5011", {
            "identity_confirmed": True,
            "description_ru": "Клапан для систем отопления и кондиционирования, резьбовое подключение.",
        })
        _write_evidence(evidence_dir, "V5011")
        status = merge.merge_one("V5011")
        assert "description_ru" in status["fields_added"]

    def test_garbage_description_skipped(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "V5011", {
            "identity_confirmed": True,
            "description_ru": "citeturn42view0",
        })
        _write_evidence(evidence_dir, "V5011")
        status = merge.merge_one("V5011")
        assert "description_ru" not in status["fields_added"]

    def test_merge_category(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "V5011", {
            "identity_confirmed": True,
            "category_suggestion": "Регулирующие клапаны",
        })
        _write_evidence(evidence_dir, "V5011")
        status = merge.merge_one("V5011")
        assert "dr_category" in status["fields_added"]
        ev = json.loads((evidence_dir / "evidence_V5011.json").read_text("utf-8"))
        assert ev["dr_category"] == "Регулирующие клапаны"

    def test_existing_category_not_overwritten(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "V5011", {
            "identity_confirmed": True,
            "category_suggestion": "New Category",
        })
        _write_evidence(evidence_dir, "V5011", extra={"dr_category": "Old Category"})
        status = merge.merge_one("V5011")
        assert "dr_category" not in status["fields_added"]
        ev = json.loads((evidence_dir / "evidence_V5011.json").read_text("utf-8"))
        assert ev["dr_category"] == "Old Category"

    def test_merge_price_admissible(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "V5011", {
            "identity_confirmed": True,
            "price_assessment": "admissible_public_price",
            "price_value": {"amount": 235.6, "currency": "CHF", "source_url": "https://example.com"},
        })
        _write_evidence(evidence_dir, "V5011")
        status = merge.merge_one("V5011")
        assert "dr_price" in status["fields_added"]
        ev = json.loads((evidence_dir / "evidence_V5011.json").read_text("utf-8"))
        assert ev["dr_price"] == 235.6
        assert ev["dr_currency"] == "CHF"

    def test_non_admissible_price_not_merged(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "V5011", {
            "identity_confirmed": True,
            "price_assessment": "ambiguous_offer",
            "price_value": {"amount": 100, "currency": "USD"},
        })
        _write_evidence(evidence_dir, "V5011")
        status = merge.merge_one("V5011")
        assert "dr_price" not in status["fields_added"]

    def test_existing_price_not_overwritten(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "V5011", {
            "identity_confirmed": True,
            "price_assessment": "admissible_public_price",
            "price_value": {"amount": 999, "currency": "EUR"},
        })
        _write_evidence(evidence_dir, "V5011", extra={"dr_price": 100})
        status = merge.merge_one("V5011")
        assert "dr_price" not in status["fields_added"]
        ev = json.loads((evidence_dir / "evidence_V5011.json").read_text("utf-8"))
        assert ev["dr_price"] == 100  # old value preserved

    def test_merge_photo_url(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "V5011", {
            "identity_confirmed": True,
            "photo_url": "https://example.com/photo.jpg",
        })
        _write_evidence(evidence_dir, "V5011")
        status = merge.merge_one("V5011")
        assert "dr_image_url" in status["fields_added"]

    def test_merge_specs(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "V5011", {
            "identity_confirmed": True,
            "specs": {"DN": "15", "Kvs": "0.63"},
        })
        _write_evidence(evidence_dir, "V5011")
        status = merge.merge_one("V5011")
        assert "specs" in status["fields_added"]
        ev = json.loads((evidence_dir / "evidence_V5011.json").read_text("utf-8"))
        assert ev["deep_research"]["specs"]["DN"] == "15"

    def test_merge_key_findings(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "V5011", {
            "identity_confirmed": True,
            "key_findings": ["Finding 1", "Finding 2"],
        })
        _write_evidence(evidence_dir, "V5011")
        status = merge.merge_one("V5011")
        assert "key_findings" in status["fields_added"]

    def test_dry_run_does_not_write(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "V5011", {
            "identity_confirmed": True,
            "title_ru": "Test Title",
        })
        _write_evidence(evidence_dir, "V5011")
        original = (evidence_dir / "evidence_V5011.json").read_text("utf-8")
        merge.merge_one("V5011", dry_run=True)
        after = (evidence_dir / "evidence_V5011.json").read_text("utf-8")
        assert original == after

    def test_all_fields_populated_skips(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "V5011", {
            "identity_confirmed": True,
            "title_ru": "Title",
            "category_suggestion": "Cat",
        })
        _write_evidence(evidence_dir, "V5011", extra={
            "dr_category": "Existing Cat",
            "deep_research": {
                "title_ru": "Existing Title",
                "identity_confirmed": True,
                "confidence": "high",
            },
        })
        status = merge.merge_one("V5011")
        assert status["action"] == "skipped"
        assert "already populated" in status["reason"]

    def test_merge_records_metadata(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "V5011", {
            "identity_confirmed": True,
            "title_ru": "New title",
        })
        _write_evidence(evidence_dir, "V5011")
        merge.merge_one("V5011")
        ev = json.loads((evidence_dir / "evidence_V5011.json").read_text("utf-8"))
        assert "merge_ts" in ev["deep_research"]
        assert ev["deep_research"]["merge_source"] == "result_V5011.json"


# ---------------------------------------------------------------------------
# run (batch)
# ---------------------------------------------------------------------------

class TestRunBatch:
    def test_run_merges_multiple(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        for pn in ("A1", "B2", "C3"):
            _write_result(results_dir, pn, {
                "identity_confirmed": True,
                "title_ru": f"Title {pn}",
            })
            _write_evidence(evidence_dir, pn)
        summary = merge.run()
        assert summary["merged"] == 3
        assert summary["total"] == 3

    def test_run_pn_filter(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        for pn in ("A1", "B2"):
            _write_result(results_dir, pn, {
                "identity_confirmed": True,
                "title_ru": f"Title {pn}",
            })
            _write_evidence(evidence_dir, pn)
        summary = merge.run(pn_filter="A1")
        assert summary["merged"] == 1
        assert summary["total"] == 1

    def test_run_dry_run(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "X1", {
            "identity_confirmed": True,
            "title_ru": "Test",
        })
        _write_evidence(evidence_dir, "X1")
        summary = merge.run(dry_run=True)
        assert summary["dry_run"] is True
        assert summary["merged"] == 1
        # File should be unchanged
        ev = json.loads((evidence_dir / "evidence_X1.json").read_text("utf-8"))
        assert "deep_research" not in ev

    def test_run_counts_fields(self, tmp_dirs):
        _, results_dir, evidence_dir = tmp_dirs
        _write_result(results_dir, "A1", {
            "identity_confirmed": True,
            "title_ru": "T1",
            "category_suggestion": "Cat1",
        })
        _write_result(results_dir, "B2", {
            "identity_confirmed": True,
            "title_ru": "T2",
        })
        _write_evidence(evidence_dir, "A1")
        _write_evidence(evidence_dir, "B2")
        summary = merge.run()
        assert summary["field_counts"]["title_ru"] == 2
        assert summary["field_counts"]["dr_category"] == 1

    def test_empty_results_dir(self, tmp_dirs):
        summary = merge.run()
        assert summary["total"] == 0
        assert summary["merged"] == 0

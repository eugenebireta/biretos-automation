"""Deterministic tests for catalog.peha_reclassify_8sku.

No live API, no unmocked time/randomness.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "catalog" / "peha_reclassify_8sku.py"
_spec = importlib.util.spec_from_file_location("peha_reclassify_8sku", _MODULE_PATH)
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)

NEW_CATEGORY = mod.NEW_CATEGORY
OLD_CATEGORIES = mod.OLD_CATEGORIES
TARGET_SKUS = mod.TARGET_SKUS
BatchResult = mod.BatchResult
_patch_evidence_bundle = mod._patch_evidence_bundle
_patch_training_data = mod._patch_training_data
_write_evidence_bundle = mod._write_evidence_bundle
run = mod.run

TRACE_ID = "test_trace_001"


def _make_evidence_file(tmp_path: Path, sku: str, category: str) -> Path:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    data = {
        "schema_version": "1.2",
        "pn": sku,
        "brand": "Honeywell",
        "expected_category": category,
        "card_status": "REVIEW_REQUIRED",
    }
    path = evidence_dir / f"evidence_{sku}.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return evidence_dir


def _make_training_file(tmp_path: Path, entries: list[dict]) -> Path:
    path = tmp_path / "training.json"
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return path


class TestPatchEvidenceBundle:
    def test_applies_correction(self, tmp_path: Path) -> None:
        ev_dir = _make_evidence_file(tmp_path, "101411", "Датчик")
        result = _patch_evidence_bundle("101411", TRACE_ID, evidence_dir=ev_dir)
        assert result.status == "applied"
        assert result.old_category == "Датчик"
        assert result.new_category == NEW_CATEGORY
        reloaded = json.loads((ev_dir / "evidence_101411.json").read_text(encoding="utf-8"))
        assert reloaded["expected_category"] == NEW_CATEGORY

    def test_idempotent_on_second_run(self, tmp_path: Path) -> None:
        ev_dir = _make_evidence_file(tmp_path, "101411", NEW_CATEGORY)
        result = _patch_evidence_bundle("101411", TRACE_ID, evidence_dir=ev_dir)
        assert result.status == "already_correct"

    def test_skips_missing_file(self, tmp_path: Path) -> None:
        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()
        result = _patch_evidence_bundle("999999", TRACE_ID, evidence_dir=ev_dir)
        assert result.status == "skipped_not_found"

    def test_refuses_unexpected_category(self, tmp_path: Path) -> None:
        ev_dir = _make_evidence_file(tmp_path, "101411", "Беруши")
        result = _patch_evidence_bundle("101411", TRACE_ID, evidence_dir=ev_dir)
        assert result.status == "skipped_unexpected_category"
        reloaded = json.loads((ev_dir / "evidence_101411.json").read_text(encoding="utf-8"))
        assert reloaded["expected_category"] == "Беруши"

    def test_patches_ventil_category(self, tmp_path: Path) -> None:
        ev_dir = _make_evidence_file(tmp_path, "125711", "Вентиль")
        result = _patch_evidence_bundle("125711", TRACE_ID, evidence_dir=ev_dir)
        assert result.status == "applied"
        assert result.old_category == "Вентиль"


class TestPatchTrainingData:
    def test_patches_matching_skus(self, tmp_path: Path) -> None:
        entries = [
            {"pn": "101411", "correct_category": "Датчик", "correction": False},
            {"pn": "125711", "correct_category": "Вентиль", "correction": False},
            {"pn": "other_pn", "correct_category": "Беруши", "correction": False},
        ]
        path = _make_training_file(tmp_path, entries)
        results = _patch_training_data(
            ["101411", "125711"], TRACE_ID, training_path=path
        )
        assert len(results) == 2
        assert all(r.status == "applied" for r in results)

        reloaded = json.loads(path.read_text(encoding="utf-8"))
        assert reloaded[0]["correct_category"] == NEW_CATEGORY
        assert reloaded[0]["correction"] is True
        assert reloaded[1]["correct_category"] == NEW_CATEGORY
        # other_pn untouched
        assert reloaded[2]["correct_category"] == "Беруши"

    def test_idempotent_on_second_run(self, tmp_path: Path) -> None:
        entries = [
            {"pn": "101411", "correct_category": NEW_CATEGORY, "correction": True},
        ]
        path = _make_training_file(tmp_path, entries)
        results = _patch_training_data(["101411"], TRACE_ID, training_path=path)
        assert results[0].status == "already_correct"

    def test_missing_training_file(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        results = _patch_training_data(["101411"], TRACE_ID, training_path=path)
        assert results[0].status == "skipped_not_found"

    def test_sku_not_in_training_data(self, tmp_path: Path) -> None:
        entries = [{"pn": "other", "correct_category": "Датчик", "correction": False}]
        path = _make_training_file(tmp_path, entries)
        results = _patch_training_data(["101411"], TRACE_ID, training_path=path)
        assert results[0].status == "skipped_not_found"


class TestWriteEvidenceBundle:
    def test_writes_valid_json(self, tmp_path: Path) -> None:
        out_path = tmp_path / "bundle" / "evidence.json"
        batch = BatchResult(trace_id=TRACE_ID)
        _write_evidence_bundle(batch, out_path=out_path)
        assert out_path.exists()
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert data["trace_id"] == TRACE_ID
        assert data["task_id"] == "RECLASSIFY-PEHA-8SKU"
        assert data["new_category"] == NEW_CATEGORY


class TestFullRun:
    def test_end_to_end(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Set up evidence files
        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()
        for sku in TARGET_SKUS:
            cat = "Вентиль" if sku in ("125711", "127411") else "Датчик"
            data = {
                "schema_version": "1.2",
                "pn": sku,
                "brand": "Honeywell",
                "expected_category": cat,
            }
            (ev_dir / f"evidence_{sku}.json").write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )

        # Set up training data
        training_entries = [
            {"pn": sku, "correct_category": "Вентиль" if sku in ("125711", "127411") else "Датчик", "correction": False}
            for sku in TARGET_SKUS
        ]
        training_path = tmp_path / "training.json"
        training_path.write_text(
            json.dumps(training_entries, ensure_ascii=False), encoding="utf-8"
        )

        bundle_path = tmp_path / "bundle" / "evidence.json"

        monkeypatch.setattr(mod, "EVIDENCE_DIR", ev_dir)
        monkeypatch.setattr(mod, "TRAINING_DATA_PATH", training_path)
        monkeypatch.setattr(mod, "EVIDENCE_BUNDLE_OUT", bundle_path)

        batch = run(TRACE_ID)
        assert len(batch.errors) == 0
        # 8 evidence + 8 training = 16 results
        assert len(batch.results) == 16
        applied = [r for r in batch.results if r.status == "applied"]
        assert len(applied) == 16

        # Verify evidence files patched
        for sku in TARGET_SKUS:
            reloaded = json.loads(
                (ev_dir / f"evidence_{sku}.json").read_text(encoding="utf-8")
            )
            assert reloaded["expected_category"] == NEW_CATEGORY

        # Verify training data patched
        reloaded_training = json.loads(training_path.read_text(encoding="utf-8"))
        for entry in reloaded_training:
            assert entry["correct_category"] == NEW_CATEGORY
            assert entry["correction"] is True

        # Verify evidence bundle written
        assert bundle_path.exists()
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        assert bundle["trace_id"] == TRACE_ID
        assert len(bundle["results"]) == 16


class TestConstants:
    def test_target_skus_count(self) -> None:
        assert len(TARGET_SKUS) == 8

    def test_old_categories_are_known(self) -> None:
        assert OLD_CATEGORIES == frozenset({"Датчик", "Вентиль"})

    def test_new_category(self) -> None:
        assert NEW_CATEGORY == "electrical_switch_covers"

"""
Tests for evidence-first skip logic in photo_pipeline.run().

Covers:
- PN with existing evidence file + not in checkpoint → EVIDENCE_EXISTS (skip)
- PN with existing evidence file + force_reprocess=True → falls through to processing
- PN without evidence file → falls through to processing
- PN with corrupted evidence file → falls through to processing
- PN already in checkpoint → CHECKPOINT (skip), evidence file not consulted
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

import photo_pipeline


_STUB_BUNDLE = {
    "schema_version": "1.2",
    "pn": "TEST-PN-001",
    "card_status": "DRAFT_ONLY",
    "photo": {"verdict": "REJECT"},
    "price": {"price_status": "public_price"},
}

_DF_ROW = {
    "Параметр: Партномер": "TEST-PN-001",
    "Название товара или услуги": "Test Product",
    "Цена продажи": "0",
    "Параметр: Тип товара": "",
}


def _make_df(pn: str = "TEST-PN-001") -> pd.DataFrame:
    row = dict(_DF_ROW)
    row["Параметр: Партномер"] = pn
    return pd.DataFrame([row])


def _stub_bundle(pn: str) -> dict:
    b = dict(_STUB_BUNDLE)
    b["pn"] = pn
    return b


class TestEvidenceFirstSkip:
    def test_existing_evidence_skipped_when_not_in_checkpoint(
        self, tmp_path, monkeypatch
    ):
        """PN with existing evidence file and no checkpoint entry → EVIDENCE_EXISTS skip."""
        pn = "TEST-PN-001"
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        bundle = _stub_bundle(pn)
        (evidence_dir / f"evidence_{pn}.json").write_text(
            json.dumps(bundle), encoding="utf-8"
        )

        monkeypatch.setattr(photo_pipeline, "EVIDENCE_DIR", evidence_dir)
        monkeypatch.setattr(photo_pipeline, "load_run_dataframe", lambda **kw: _make_df(pn))
        monkeypatch.setattr(photo_pipeline, "load_checkpoint", lambda: {})
        monkeypatch.setattr(photo_pipeline, "save_checkpoint", lambda cp: None)
        monkeypatch.setattr(photo_pipeline, "allow_next_sku", lambda pn: (True, ""))

        api_called = []
        monkeypatch.setattr(
            photo_pipeline, "call_gpt", lambda *a, **kw: api_called.append(1) or "{}"
        )

        photo_pipeline.run(export=False, force_reprocess=False)

        assert not api_called, "API must not be called for existing evidence"

    def test_existing_evidence_reprocessed_with_force_flag(
        self, tmp_path, monkeypatch
    ):
        """PN with existing evidence + force_reprocess=True → falls through to processing."""
        pn = "TEST-PN-002"
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        bundle = _stub_bundle(pn)
        (evidence_dir / f"evidence_{pn}.json").write_text(
            json.dumps(bundle), encoding="utf-8"
        )

        monkeypatch.setattr(photo_pipeline, "EVIDENCE_DIR", evidence_dir)
        monkeypatch.setattr(photo_pipeline, "load_run_dataframe", lambda **kw: _make_df(pn))
        monkeypatch.setattr(photo_pipeline, "load_checkpoint", lambda: {})
        monkeypatch.setattr(photo_pipeline, "save_checkpoint", lambda cp: None)

        reached_processing = []
        monkeypatch.setattr(
            photo_pipeline, "allow_next_sku",
            lambda pn: reached_processing.append(pn) or (False, "test_stop"),
        )

        photo_pipeline.run(export=False, force_reprocess=True)

        assert pn in reached_processing, "force_reprocess must bypass evidence-first skip"

    def test_missing_evidence_falls_through_to_processing(self, tmp_path, monkeypatch):
        """PN without any evidence file → falls through to allow_next_sku check."""
        pn = "TEST-PN-003"
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()

        monkeypatch.setattr(photo_pipeline, "EVIDENCE_DIR", evidence_dir)
        monkeypatch.setattr(photo_pipeline, "load_run_dataframe", lambda **kw: _make_df(pn))
        monkeypatch.setattr(photo_pipeline, "load_checkpoint", lambda: {})
        monkeypatch.setattr(photo_pipeline, "save_checkpoint", lambda cp: None)

        reached_processing = []
        monkeypatch.setattr(
            photo_pipeline, "allow_next_sku",
            lambda pn: reached_processing.append(pn) or (False, "test_stop"),
        )

        photo_pipeline.run(export=False, force_reprocess=False)

        assert pn in reached_processing, "PN without evidence must reach processing"

    def test_corrupted_evidence_falls_through_to_processing(
        self, tmp_path, monkeypatch
    ):
        """PN with corrupted evidence file → falls through (not silently skipped)."""
        pn = "TEST-PN-004"
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        (evidence_dir / f"evidence_{pn}.json").write_text(
            "{{NOT VALID JSON", encoding="utf-8"
        )

        monkeypatch.setattr(photo_pipeline, "EVIDENCE_DIR", evidence_dir)
        monkeypatch.setattr(photo_pipeline, "load_run_dataframe", lambda **kw: _make_df(pn))
        monkeypatch.setattr(photo_pipeline, "load_checkpoint", lambda: {})
        monkeypatch.setattr(photo_pipeline, "save_checkpoint", lambda cp: None)

        reached_processing = []
        monkeypatch.setattr(
            photo_pipeline, "allow_next_sku",
            lambda pn: reached_processing.append(pn) or (False, "test_stop"),
        )

        photo_pipeline.run(export=False, force_reprocess=False)

        assert pn in reached_processing, "Corrupted evidence must not silently skip"

    def test_checkpoint_takes_priority_over_evidence_file(
        self, tmp_path, monkeypatch
    ):
        """PN already in checkpoint → CHECKPOINT skip, evidence file is not consulted."""
        pn = "TEST-PN-005"
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        # Evidence file exists but should be irrelevant — checkpoint wins
        bundle = _stub_bundle(pn)
        (evidence_dir / f"evidence_{pn}.json").write_text(
            json.dumps(bundle), encoding="utf-8"
        )

        checkpoint_bundle = dict(bundle)
        checkpoint_bundle["_from_checkpoint"] = True

        monkeypatch.setattr(photo_pipeline, "EVIDENCE_DIR", evidence_dir)
        monkeypatch.setattr(photo_pipeline, "load_run_dataframe", lambda **kw: _make_df(pn))
        monkeypatch.setattr(photo_pipeline, "load_checkpoint", lambda: {pn: checkpoint_bundle})
        monkeypatch.setattr(photo_pipeline, "save_checkpoint", lambda cp: None)

        reached_processing = []
        monkeypatch.setattr(
            photo_pipeline, "allow_next_sku",
            lambda pn: reached_processing.append(pn) or (False, "test_stop"),
        )

        photo_pipeline.run(export=False, force_reprocess=False)

        assert pn not in reached_processing, "Checkpoint PN must not reach processing"

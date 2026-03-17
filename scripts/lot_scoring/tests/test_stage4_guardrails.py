from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.lot_scoring import run_stage3_automation as stage3


def _write_unknown_intelligence(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ranking", "rank", "pn", "total_effective_usd", "lot_count", "line_count"],
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_llm_results(path: Path, rows: list[dict]) -> None:
    payload = {"status": "completed", "results": rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_delta(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "lot_id",
                "baseline_rank",
                "current_rank",
                "delta_rank",
                "delta_score_10",
                "delta_final_score",
                "delta_unknown_exposure",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def test_drift_report_deterministic(tmp_path):
    audits_dir = tmp_path / "audits"
    _write_delta(
        audits_dir / "delta_from_baseline.csv",
        [
            {
                "lot_id": "10",
                "baseline_rank": "1",
                "current_rank": "4",
                "delta_rank": "3",
                "delta_score_10": "-0.2",
                "delta_final_score": "-0.02",
                "delta_unknown_exposure": "0.03",
            },
            {
                "lot_id": "11",
                "baseline_rank": "2",
                "current_rank": "1",
                "delta_rank": "-1",
                "delta_score_10": "0.1",
                "delta_final_score": "0.01",
                "delta_unknown_exposure": "0.00",
            },
        ],
    )

    llm_rows = [
        {
            "lot_id": "10",
            "slice_rank": 1,
            "sku_code": "EDA1001",
            "category_engine": "unknown",
        },
        {
            "lot_id": "11",
            "slice_rank": 1,
            "sku_code": "ABC2000",
            "category_engine": "gas_safety",
        },
    ]
    sku_lookup = {"EDA1001": "gas_safety"}
    pn_patterns = [{"pattern": "^ABC[A-Z0-9]*$", "category": "gas_safety"}]

    path_1, report_1 = stage3._build_drift_report(
        audits_dir=audits_dir,
        llm_rows=llm_rows,
        sku_lookup=sku_lookup,
        pn_patterns=pn_patterns,
        source_signature="sig-1",
    )
    path_2, report_2 = stage3._build_drift_report(
        audits_dir=audits_dir,
        llm_rows=llm_rows,
        sku_lookup=sku_lookup,
        pn_patterns=pn_patterns,
        source_signature="sig-1",
    )

    assert path_1 == path_2
    assert report_1 == report_2
    assert report_1["category_change_pct"] == 50.0
    assert report_1["unknown_exposure_change_pct"] == 50.0
    assert report_1["top_rank_changes"][0]["lot_id"] == "10"


def test_dictionary_growth_guard_triggered(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    audits_dir = tmp_path / "audits"
    output_dir = tmp_path / "output"
    data_dir.mkdir(parents=True, exist_ok=True)
    audits_dir.mkdir(parents=True, exist_ok=True)

    sku_path = data_dir / "sku_lookup.json"
    pn_path = data_dir / "pn_patterns.json"
    version_path = data_dir / "taxonomy_version.json"
    lock_path = data_dir / "taxonomy_lock.json"
    sku_path.write_text("{}", encoding="utf-8")
    pn_path.write_text("[]", encoding="utf-8")
    version_path.write_text(
        json.dumps({"version": "v4.0-s1.0", "created_at": "2026-02-24", "sku_lookup_count": 0, "pn_patterns_count": 0}),
        encoding="utf-8",
    )

    _write_unknown_intelligence(
        audits_dir / "unknown_intelligence.csv",
        [
            {
                "ranking": "top_usd",
                "rank": "1",
                "pn": "EDA1001",
                "total_effective_usd": "100.0",
                "lot_count": "1",
                "line_count": "1",
            },
            {
                "ranking": "top_usd",
                "rank": "2",
                "pn": "EDA1002",
                "total_effective_usd": "90.0",
                "lot_count": "1",
                "line_count": "1",
            },
        ],
    )
    _write_llm_results(
        audits_dir / "llm_audit_results.json",
        [
            {
                "lot_id": "10",
                "sku_code": "EDA1001",
                "category_engine": "unknown",
                "llm_category": "gas_safety",
                "confidence": 0.95,
                "effective_usd": 100.0,
            },
            {
                "lot_id": "11",
                "sku_code": "EDA1002",
                "category_engine": "unknown",
                "llm_category": "fire_safety",
                "confidence": 0.95,
                "effective_usd": 90.0,
            },
        ],
    )

    monkeypatch.setattr(stage3, "_DEFAULT_SKU_LOOKUP_PATH", sku_path)
    monkeypatch.setattr(stage3, "_DEFAULT_PN_PATTERNS_PATH", pn_path)
    monkeypatch.setattr(stage3, "_DEFAULT_TAXONOMY_VERSION_PATH", version_path)
    monkeypatch.setattr(stage3, "_DEFAULT_TAXONOMY_LOCK_PATH", lock_path)
    monkeypatch.setattr(stage3, "reload_taxonomy", lambda: None)

    summary = stage3.run_stage3_automation(
        input_path=None,
        output_dir=output_dir,
        audits_dir=audits_dir,
        save_baseline=False,
        run_pipeline=False,
        recompute_after_update=False,
        overwrite_existing=False,
        min_confidence=0.85,
        min_votes=1,
        min_prefix_len=4,
        max_prefix_len=7,
        min_prefix_support=2,
        max_new_patterns=10,
        max_new_sku_per_run=1,
        max_new_patterns_per_run=100,
        force_update=True,
        author="test_stage4",
    )

    assert summary["status"] == "guard_triggered"
    assert summary["updates"]["applied"] is False
    assert summary["guardrails"]["dictionary_growth_guard_triggered"] is True
    assert json.loads(sku_path.read_text(encoding="utf-8")) == {}


def test_taxonomy_lock_prevents_updates(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    audits_dir = tmp_path / "audits"
    output_dir = tmp_path / "output"
    data_dir.mkdir(parents=True, exist_ok=True)
    audits_dir.mkdir(parents=True, exist_ok=True)

    sku_path = data_dir / "sku_lookup.json"
    pn_path = data_dir / "pn_patterns.json"
    version_path = data_dir / "taxonomy_version.json"
    lock_path = data_dir / "taxonomy_lock.json"
    sku_path.write_text("{}", encoding="utf-8")
    pn_path.write_text("[]", encoding="utf-8")
    version_path.write_text(
        json.dumps({"version": "v4.0-s1.0", "created_at": "2026-02-24", "sku_lookup_count": 0, "pn_patterns_count": 0}),
        encoding="utf-8",
    )
    lock_path.write_text(json.dumps({"locked": True}), encoding="utf-8")

    _write_unknown_intelligence(
        audits_dir / "unknown_intelligence.csv",
        [
            {
                "ranking": "top_usd",
                "rank": "1",
                "pn": "EDA1001",
                "total_effective_usd": "100.0",
                "lot_count": "1",
                "line_count": "1",
            },
        ],
    )
    _write_llm_results(
        audits_dir / "llm_audit_results.json",
        [
            {
                "lot_id": "10",
                "sku_code": "EDA1001",
                "category_engine": "unknown",
                "llm_category": "gas_safety",
                "confidence": 0.99,
                "effective_usd": 100.0,
            },
        ],
    )

    monkeypatch.setattr(stage3, "_DEFAULT_SKU_LOOKUP_PATH", sku_path)
    monkeypatch.setattr(stage3, "_DEFAULT_PN_PATTERNS_PATH", pn_path)
    monkeypatch.setattr(stage3, "_DEFAULT_TAXONOMY_VERSION_PATH", version_path)
    monkeypatch.setattr(stage3, "_DEFAULT_TAXONOMY_LOCK_PATH", lock_path)
    monkeypatch.setattr(stage3, "reload_taxonomy", lambda: None)

    summary = stage3.run_stage3_automation(
        input_path=None,
        output_dir=output_dir,
        audits_dir=audits_dir,
        save_baseline=False,
        run_pipeline=False,
        recompute_after_update=False,
        overwrite_existing=False,
        min_confidence=0.85,
        min_votes=1,
        min_prefix_len=4,
        max_prefix_len=7,
        min_prefix_support=2,
        max_new_patterns=10,
        max_new_sku_per_run=100,
        max_new_patterns_per_run=100,
        force_update=True,
        author="test_stage4",
    )

    assert summary["status"] == "locked"
    assert summary["updates"]["applied"] is False
    assert summary["guardrails"]["taxonomy_lock_active"] is True
    assert json.loads(sku_path.read_text(encoding="utf-8")) == {}

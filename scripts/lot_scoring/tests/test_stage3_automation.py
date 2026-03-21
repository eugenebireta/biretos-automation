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


def test_collect_sku_candidates_deterministic_and_filtered():
    llm_rows = [
        {
            "lot_id": "10",
            "sku_code": "PNA100",
            "category_engine": "unknown",
            "llm_category": "gas_safety",
            "confidence": 0.9,
            "effective_usd": 50.0,
        },
        {
            "lot_id": "11",
            "sku_code": "PNA100",
            "category_engine": "unknown",
            "llm_category": "gas_safety",
            "confidence": 0.9,
            "effective_usd": 50.0,
        },
        {
            "lot_id": "12",
            "sku_code": "PNB200",
            "category_engine": "unknown",
            "llm_category": "industrial_sensors",
            "confidence": 0.95,
            "effective_usd": 100.0,
        },
        {
            "lot_id": "13",
            "sku_code": "PNB200",
            "category_engine": "unknown",
            "llm_category": "fire_safety",
            "confidence": 0.95,
            "effective_usd": 100.0,
        },
        {
            "lot_id": "14",
            "sku_code": "PNC300",
            "category_engine": "gas_safety",
            "llm_category": "fire_safety",
            "confidence": 0.99,
            "effective_usd": 999.0,
        },
    ]

    selected = stage3._collect_sku_candidates(
        llm_rows,
        target_unknown_pn={"PNA100", "PNB200"},
        min_confidence=0.85,
        min_votes=1,
    )

    # PNB200 has equal usd/votes for two categories, tie-break by category asc.
    # Final candidate ordering: usd desc, sku asc.
    assert [item["sku"] for item in selected] == ["PNA100", "PNB200"]
    assert selected[0]["category"] == "gas_safety"
    assert selected[1]["category"] == "fire_safety"


def test_derive_pn_patterns_non_redundant_and_sorted():
    lookup = {
        "EDA1001": "gas_safety",
        "EDA1002": "gas_safety",
        "EDA1003": "gas_safety",
        "EDA2X01": "gas_safety",
        "ABC1001": "fire_safety",
        "ABC1002": "fire_safety",
        "ABC1003": "fire_safety",
    }
    patterns = stage3._derive_pn_patterns(
        lookup,
        min_prefix_len=3,
        max_prefix_len=6,
        min_support=3,
        author="test",
        max_new_patterns=10,
    )

    assert patterns
    assert patterns == sorted(patterns, key=lambda item: (-len(item["prefix"]), item["prefix"], item["category"]))
    # Redundant shorter prefixes should be removed when longer specific prefix exists.
    prefixes = [item["prefix"] for item in patterns]
    assert "EDA" not in prefixes or "EDA100" not in prefixes
    assert all(item["pattern"].startswith("^") for item in patterns)


def test_run_stage3_automation_updates_then_skips_on_same_signature(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    audits_dir = tmp_path / "audits"
    output_dir = tmp_path / "output"
    data_dir.mkdir(parents=True, exist_ok=True)
    audits_dir.mkdir(parents=True, exist_ok=True)

    sku_path = data_dir / "sku_lookup.json"
    pn_path = data_dir / "pn_patterns.json"
    version_path = data_dir / "taxonomy_version.json"
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
                "total_effective_usd": "500.0",
                "lot_count": "2",
                "line_count": "2",
            },
            {
                "ranking": "top_freq",
                "rank": "1",
                "pn": "EDA1001",
                "total_effective_usd": "500.0",
                "lot_count": "2",
                "line_count": "2",
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
                "effective_usd": 300.0,
            },
            {
                "lot_id": "11",
                "sku_code": "EDA1001",
                "category_engine": "unknown",
                "llm_category": "gas_safety",
                "confidence": 0.92,
                "effective_usd": 200.0,
            },
        ],
    )

    monkeypatch.setattr(stage3, "_DEFAULT_SKU_LOOKUP_PATH", sku_path)
    monkeypatch.setattr(stage3, "_DEFAULT_PN_PATTERNS_PATH", pn_path)
    monkeypatch.setattr(stage3, "_DEFAULT_TAXONOMY_VERSION_PATH", version_path)
    monkeypatch.setattr(stage3, "_DEFAULT_TAXONOMY_LOCK_PATH", data_dir / "taxonomy_lock.json")
    monkeypatch.setattr(stage3, "reload_taxonomy", lambda: None)

    summary_1 = stage3.run_stage3_automation(
        input_path=None,
        output_dir=output_dir,
        audits_dir=audits_dir,
        save_baseline=False,
        run_pipeline=False,
        recompute_after_update=False,
        overwrite_existing=False,
        min_confidence=0.85,
        min_votes=2,
        min_prefix_len=4,
        max_prefix_len=7,
        min_prefix_support=2,
        max_new_patterns=10,
        max_new_sku_per_run=100,
        max_new_patterns_per_run=100,
        force_update=False,
        author="test_stage3",
    )

    assert summary_1["status"] == "completed"
    assert summary_1["updates"]["sku_lookup"]["added"] == 1
    assert summary_1["updates"]["lookup_changed"] is True

    lookup_payload = json.loads(sku_path.read_text(encoding="utf-8"))
    assert lookup_payload["EDA1001"] == "gas_safety"

    version_payload = json.loads(version_path.read_text(encoding="utf-8"))
    assert version_payload["version"] == "v4.0-s3.1"
    assert version_payload["sku_lookup_count"] >= 1

    summary_2 = stage3.run_stage3_automation(
        input_path=None,
        output_dir=output_dir,
        audits_dir=audits_dir,
        save_baseline=False,
        run_pipeline=False,
        recompute_after_update=False,
        overwrite_existing=False,
        min_confidence=0.85,
        min_votes=2,
        min_prefix_len=4,
        max_prefix_len=7,
        min_prefix_support=2,
        max_new_patterns=10,
        max_new_sku_per_run=100,
        max_new_patterns_per_run=100,
        force_update=False,
        author="test_stage3",
    )

    assert summary_2["status"] == "skipped"
    assert "signature unchanged" in summary_2["skip_reason"].lower()

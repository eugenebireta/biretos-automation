import csv
import json
import sys
from pathlib import Path

from scripts.lot_scoring import run_hybrid_audit


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_llm_only_uses_existing_audit_csvs_and_skips_recompute(tmp_path, monkeypatch):
    audits_dir = tmp_path / "audits"
    ranking_summary_path = audits_dir / "ranking_summary.csv"
    category_audit_path = audits_dir / "category_audit.csv"
    value_slice_rows_path = audits_dir / "value_slice_rows.csv"

    _write_csv(
        ranking_summary_path,
        fieldnames=[
            "rank",
            "lot_id",
            "score_10",
            "cqr",
            "core_ratio",
            "total_effective_usd",
            "toxic_anchor",
            "top3_capital_map",
        ],
        rows=[
            {
                "rank": "1",
                "lot_id": "10",
                "score_10": "8.91",
                "cqr": "0.920000",
                "core_ratio": "0.770000",
                "total_effective_usd": "100000.00",
                "toxic_anchor": "NO",
                "top3_capital_map": "gas_safety:80.0%; fire_safety:20.0%",
            },
            {
                "rank": "2",
                "lot_id": "11",
                "score_10": "7.50",
                "cqr": "0.810000",
                "core_ratio": "0.740000",
                "total_effective_usd": "80000.00",
                "toxic_anchor": "YES",
                "top3_capital_map": "unknown:60.0%; gas_safety:40.0%",
            },
        ],
    )

    _write_csv(
        category_audit_path,
        fieldnames=[
            "lot_id",
            "fire_safety_pct",
            "gas_safety_pct",
            "construction_supplies_pct",
            "unknown_pct",
            "other_pct",
        ],
        rows=[
            {
                "lot_id": "10",
                "fire_safety_pct": "20.0000",
                "gas_safety_pct": "80.0000",
                "construction_supplies_pct": "0.0000",
                "unknown_pct": "0.0000",
                "other_pct": "0.0000",
            },
            {
                "lot_id": "11",
                "fire_safety_pct": "0.0000",
                "gas_safety_pct": "40.0000",
                "construction_supplies_pct": "0.0000",
                "unknown_pct": "60.0000",
                "other_pct": "0.0000",
            },
        ],
    )

    _write_csv(
        value_slice_rows_path,
        fieldnames=[
            "lot_id",
            "slice_rank",
            "sku_code",
            "qty",
            "effective_usd",
            "category_engine",
            "brand_engine",
            "raw_text",
            "full_row_text",
        ],
        rows=[
            {
                "lot_id": "10",
                "slice_rank": "1",
                "sku_code": "SKU10",
                "qty": "1.000000",
                "effective_usd": "50000.000000",
                "category_engine": "gas_safety",
                "brand_engine": "honeywell",
                "raw_text": "Detector XNX",
                "full_row_text": "Honeywell XNX detector",
            },
            {
                "lot_id": "11",
                "slice_rank": "1",
                "sku_code": "SKU11",
                "qty": "1.000000",
                "effective_usd": "40000.000000",
                "category_engine": "unknown",
                "brand_engine": "unknown",
                "raw_text": "Unknown module",
                "full_row_text": "Unknown industrial module",
            },
        ],
    )

    ranking_mtime = ranking_summary_path.stat().st_mtime_ns
    category_mtime = category_audit_path.stat().st_mtime_ns
    slice_mtime = value_slice_rows_path.stat().st_mtime_ns

    def _fail_recompute(*args, **kwargs):
        raise AssertionError("recompute path must not run in --llm-only mode")

    monkeypatch.setattr(run_hybrid_audit, "run_full_ranking", _fail_recompute)
    monkeypatch.setattr(run_hybrid_audit, "_compute_all_lots", _fail_recompute)
    monkeypatch.setattr("scripts.lot_scoring.llm_auditor._load_env_from_dotenv", lambda: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_hybrid_audit.py",
            "--llm-only",
            "--audits-dir",
            str(audits_dir),
        ],
    )

    run_hybrid_audit.main()

    assert ranking_summary_path.stat().st_mtime_ns == ranking_mtime
    assert category_audit_path.stat().st_mtime_ns == category_mtime
    assert value_slice_rows_path.stat().st_mtime_ns == slice_mtime

    llm_json_path = audits_dir / "llm_audit_results.json"
    delta_report_path = audits_dir / "delta_report.md"
    llm_raw_dir = audits_dir / "llm_raw_responses"

    assert llm_json_path.exists()
    assert delta_report_path.exists()
    assert llm_raw_dir.exists()

    payload = json.loads(llm_json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "skipped"
    assert "OPENAI_API_KEY" in payload["reason"]

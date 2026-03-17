import csv
import json

from scripts.lot_scoring.cdm import LotRecord
from scripts.lot_scoring.run_full_ranking_v341 import (
    _collect_unknown_intelligence,
    _handle_baseline_and_delta,
)


def _read_csv_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_collect_unknown_intelligence_tie_breakers_and_no_mutation(tmp_path):
    processed = [
        {
            "lot": LotRecord(lot_id="10"),
            "all_skus": [
                {"sku_code_normalized": "PNB", "category": "unknown", "effective_line_usd": 120.0},
                {"sku_code_normalized": "PNA", "category": "unknown", "effective_line_usd": 100.0},
                {"sku_code_normalized": "K1", "category": "gas_safety", "effective_line_usd": 50.0},
            ],
        },
        {
            "lot": LotRecord(lot_id="11"),
            "all_skus": [
                {"sku_code_normalized": "PNA", "category": "unknown", "effective_line_usd": 20.0},
                {"sku_code_normalized": "PNC", "category": "unknown", "effective_line_usd": 110.0},
            ],
        },
        {
            "lot": LotRecord(lot_id="12"),
            "all_skus": [
                {"sku_code_normalized": "PNC", "category": "unknown", "effective_line_usd": 10.0},
            ],
        },
    ]

    before = json.dumps([item["all_skus"] for item in processed], sort_keys=True)
    out_path = _collect_unknown_intelligence(processed, tmp_path, top_n=3)
    after = json.dumps([item["all_skus"] for item in processed], sort_keys=True)
    assert before == after

    rows = _read_csv_rows(out_path)
    top_usd = [row for row in rows if row["ranking"] == "top_usd"]
    top_freq = [row for row in rows if row["ranking"] == "top_freq"]

    assert [row["pn"] for row in top_usd] == ["PNA", "PNB", "PNC"]
    assert [row["pn"] for row in top_freq] == ["PNA", "PNC", "PNB"]
    assert top_usd[0]["total_effective_usd"] == "120.000000"
    assert top_freq[0]["lot_count"] == "2"


def test_handle_baseline_and_delta_create_then_compare_and_no_mutation(tmp_path):
    full_rows_v1 = [
        {"lot_id": "10", "rank": 1, "score_10": 8.0, "final_score": 0.8, "unknown_exposure": 0.10, "abs_score_100": 70.0},
        {"lot_id": "11", "rank": 2, "score_10": 7.0, "final_score": 0.7, "unknown_exposure": 0.20, "abs_score_100": 60.0},
    ]
    baseline_path, delta_path = _handle_baseline_and_delta(full_rows_v1, tmp_path, save_baseline=False)
    assert baseline_path.exists()
    assert delta_path is None

    full_rows_v2 = [
        {"lot_id": "10", "rank": 2, "score_10": 7.9, "final_score": 0.79, "unknown_exposure": 0.15, "abs_score_100": 68.5},
        {"lot_id": "11", "rank": 1, "score_10": 7.2, "final_score": 0.72, "unknown_exposure": 0.18, "abs_score_100": 61.25},
    ]
    before = json.dumps(full_rows_v2, sort_keys=True)
    baseline_path_2, delta_path_2 = _handle_baseline_and_delta(full_rows_v2, tmp_path, save_baseline=False)
    after = json.dumps(full_rows_v2, sort_keys=True)

    assert before == after
    assert baseline_path_2 == baseline_path
    assert delta_path_2 is not None and delta_path_2.exists()

    delta_rows = _read_csv_rows(delta_path_2)
    by_lot = {row["lot_id"]: row for row in delta_rows}
    assert by_lot["10"]["delta_rank"] == "1"
    assert by_lot["11"]["delta_rank"] == "-1"
    assert by_lot["10"]["delta_score_10"] == "-0.1"
    assert by_lot["11"]["delta_unknown_exposure"] == "-0.02"
    assert by_lot["10"]["delta_abs_score_100"] == "-1.5"
    assert by_lot["11"]["delta_abs_score_100"] == "1.25"


def test_handle_baseline_and_delta_save_baseline_overwrites(tmp_path):
    full_rows_v1 = [
        {"lot_id": "10", "rank": 1, "score_10": 8.0, "final_score": 0.8, "unknown_exposure": 0.10, "abs_score_100": 70.0},
    ]
    baseline_path, _ = _handle_baseline_and_delta(full_rows_v1, tmp_path, save_baseline=False)

    full_rows_v2 = [
        {"lot_id": "10", "rank": 1, "score_10": 8.5, "final_score": 0.85, "unknown_exposure": 0.05, "abs_score_100": 75.0},
    ]
    baseline_path_2, delta_path_2 = _handle_baseline_and_delta(full_rows_v2, tmp_path, save_baseline=True)
    assert baseline_path_2 == baseline_path
    assert delta_path_2 is None

    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert payload["lots"][0]["score_10"] == 8.5
    assert payload["lots"][0]["unknown_exposure"] == 0.05
    assert payload["lots"][0]["abs_score_100"] == 75.0

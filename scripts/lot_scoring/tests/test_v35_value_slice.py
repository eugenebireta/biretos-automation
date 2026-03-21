from __future__ import annotations

import json
import math

from scripts.lot_scoring.capital_map import compute_capital_map
from scripts.lot_scoring.cdm import LotRecord
from scripts.lot_scoring.pipeline.score import apply_base_score, apply_final_score
from scripts.lot_scoring.run_config import RunConfig
from scripts.lot_scoring.run_lot_analysis import (
    _build_top_core_slice,
    _build_value_based_slice,
    _line_effective_usd,
)


def _make_skus(specs: list[tuple[float, str]]) -> list[dict]:
    return [
        {
            "row_index": i,
            "sku_code_normalized": f"SKU_{i}",
            "category": cat,
            "brand": "brand_x",
            "qty": 1,
            "q_has_qty": True,
            "effective_line_usd": val,
            "is_in_core_slice": True,
        }
        for i, (val, cat) in enumerate(specs, start=1)
    ]


def test_value_slice_reaches_target_when_not_capped():
    skus = _make_skus([
        (500.0, "cat_a"),
        (300.0, "cat_b"),
        (200.0, "cat_c"),
        (150.0, "cat_d"),
        (50.0, "cat_e"),
    ])
    total = sum(_line_effective_usd(s) for s in skus)
    assert total == 1200.0

    result = _build_value_based_slice(skus, total, value_pct=80.0, max_rows=50)
    cumulative = sum(_line_effective_usd(s) for s in result)

    assert len(result) == 3
    assert cumulative >= total * 0.80


def test_value_slice_capped_by_max_rows():
    skus = _make_skus([(10.0, "cat_a")] * 100)
    total = sum(_line_effective_usd(s) for s in skus)
    assert total == 1000.0

    result = _build_value_based_slice(skus, total, value_pct=80.0, max_rows=5)
    cumulative = sum(_line_effective_usd(s) for s in result)

    assert len(result) == 5
    representativeness = cumulative / total
    assert representativeness < 0.80


def test_value_slice_single_dominant_sku():
    specs = [(9000.0, "cat_a")] + [(100.0, "cat_b")] * 9
    skus = _make_skus(specs)
    total = sum(_line_effective_usd(s) for s in skus)

    result = _build_value_based_slice(skus, total, value_pct=80.0, max_rows=50)

    assert len(result) == 1
    assert _line_effective_usd(result[0]) == 9000.0


def test_capital_map_sums_to_one_and_has_other():
    skus = _make_skus([
        (300.0, "cat_a"),
        (250.0, "cat_b"),
        (200.0, "cat_c"),
        (150.0, "cat_d"),
        (100.0, "cat_e"),
        (80.0, "cat_f"),
        (50.0, "cat_g"),
    ])
    total = sum(_line_effective_usd(s) for s in skus)

    result = compute_capital_map(skus, total, top_k=5)

    dist_sum = sum(result.distribution.values())
    assert abs(dist_sum - 1.0) < 1e-9

    assert len(result.top_categories) == 6
    assert result.top_categories[-1][0] == "OTHER"
    assert result.top_categories[-1][1] > 0.0


def test_capital_map_zero_value_fallback():
    result_empty = compute_capital_map([], 1000.0, top_k=5)
    assert result_empty.flags == ["CAPITAL_MAP:ZERO_VALUE"]
    assert result_empty.distribution == {"unknown": 1.0}
    assert result_empty.analyzed_value_usd == 0.0
    assert result_empty.analyzed_share_of_core == 0.0

    zero_skus = _make_skus([(0.0, "cat_a"), (0.0, "cat_b")])
    result_zero = compute_capital_map(zero_skus, 1000.0, top_k=5)
    assert result_zero.flags == ["CAPITAL_MAP:ZERO_VALUE"]
    assert result_zero.distribution == {"unknown": 1.0}

    nonzero_skus = _make_skus([(100.0, "cat_a")])
    result_zero_total = compute_capital_map(nonzero_skus, 0.0, top_k=5)
    assert result_zero_total.flags == ["CAPITAL_MAP:ZERO_VALUE"]


def test_score10_unchanged_by_v35_patch():
    config = RunConfig()
    all_skus = [
        {
            "row_index": 1, "sku_code_normalized": "A1",
            "category": "industrial_sensors", "brand": "brand_a",
            "qty": 10, "q_has_qty": True, "effective_line_usd": 1200.0,
            "is_in_core_slice": True,
        },
        {
            "row_index": 2, "sku_code_normalized": "B1",
            "category": "electrical_components", "brand": "brand_b",
            "qty": 20, "q_has_qty": True, "effective_line_usd": 800.0,
            "is_in_core_slice": True,
        },
        {
            "row_index": 3, "sku_code_normalized": "C1",
            "category": "packaging_materials", "brand": "brand_c",
            "qty": 30, "q_has_qty": True, "effective_line_usd": 50.0,
            "is_in_core_slice": False,
        },
    ]
    core_skus = [sku for sku in all_skus if sku.get("is_in_core_slice")]
    ref_maps = {
        "category_obsolescence": {"industrial_sensors": 0.8, "electrical_components": 0.7, "packaging_materials": 0.2},
        "brand_score": {"brand_a": 0.9, "brand_b": 0.6, "brand_c": 0.4},
        "category_liquidity": {"industrial_sensors": 0.7, "electrical_components": 0.8, "packaging_materials": 0.3},
        "category_volume_proxy": {"industrial_sensors": 0.02, "electrical_components": 0.01, "packaging_materials": 0.05},
    }

    def _snapshot() -> dict:
        lot = LotRecord(lot_id="det_test")
        apply_base_score(
            lot, core_skus=core_skus, all_skus=all_skus,
            category_obsolescence=ref_maps["category_obsolescence"],
            brand_score=ref_maps["brand_score"],
            category_liquidity=ref_maps["category_liquidity"],
            category_volume_proxy=ref_maps["category_volume_proxy"],
            config=config,
        )
        apply_final_score(lot, core_skus=core_skus, all_skus=all_skus, config=config)
        return {"score_10": lot.score_10, "s1": lot.s1, "s2": lot.s2, "s3": lot.s3, "s4": lot.s4}

    snap1 = _snapshot()
    snap2 = _snapshot()
    assert json.dumps(snap1, sort_keys=True) == json.dumps(snap2, sort_keys=True)
    assert snap1["score_10"] > 0.0


def test_legacy_count_slice_backward_compat():
    skus = _make_skus([(100.0, f"cat_{i}") for i in range(10)])

    result, value = _build_top_core_slice(skus, top_pct=20.0, max_rows=50)

    expected_count = max(1, int(math.ceil(10 * 20.0 / 100.0)))
    assert len(result) == expected_count
    assert value == sum(_line_effective_usd(s) for s in result)

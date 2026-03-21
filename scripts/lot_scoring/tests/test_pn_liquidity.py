import copy
import json

from scripts.lot_scoring.cdm import LotRecord
from scripts.lot_scoring.pipeline.pn_liquidity import (
    PnLiquidityConfig,
    _resolve_pn_id,
    compute_lot_avg_pn_liquidity,
    compute_pn_liquidity,
)
from scripts.lot_scoring.pipeline.score import apply_base_score, apply_final_score, rank_lots
from scripts.lot_scoring.run_config import RunConfig


def _lot_item(lot_id: str, all_skus: list[dict], core_skus: list[dict] | None = None) -> dict:
    return {
        "lot": LotRecord(lot_id=lot_id),
        "all_skus": all_skus,
        "core_skus": all_skus if core_skus is None else core_skus,
        "metadata": {},
    }


def _default_category_liquidity() -> dict:
    return {
        "it_hardware": 0.22,
        "industrial_sensors": 0.66,
        "gas_safety": 0.75,
        "unknown": 0.30,
        "toxic_fake": 0.00,
        "_default": 0.30,
    }


def _find_row(rows: list[dict], pn_id: str) -> dict:
    for row in rows:
        if row.get("pn_id") == pn_id:
            return row
    raise AssertionError(f"PN row not found for {pn_id}")


def test_t1_determinism():
    config = PnLiquidityConfig()
    category_liquidity = _default_category_liquidity()
    processed = [
        _lot_item(
            "1",
            all_skus=[
                {"sku_code_normalized": "abc-1", "effective_line_usd": 1200, "category": "IT Hardware"},
                {"sku_code_normalized": "s-2", "effective_line_usd": 800, "category": "industrial_sensors"},
            ],
        ),
        _lot_item(
            "2",
            all_skus=[
                {"sku_code_normalized": "abc-1", "effective_line_usd": 400, "category": "unknown"},
            ],
        ),
    ]
    rows_1, scores_1 = compute_pn_liquidity(processed, category_liquidity, config)
    rows_2, scores_2 = compute_pn_liquidity(processed, category_liquidity, config)
    assert json.dumps(rows_1, sort_keys=True) == json.dumps(rows_2, sort_keys=True)
    assert json.dumps(scores_1, sort_keys=True) == json.dumps(scores_2, sort_keys=True)


def test_t2_range_0_1():
    config = PnLiquidityConfig()
    category_liquidity = _default_category_liquidity()
    processed = [
        _lot_item(
            "1",
            all_skus=[
                {"sku_code_normalized": "PN-1", "effective_line_usd": 1000, "category": "gas_safety"},
                {"sku_code_normalized": "PN-2", "effective_line_usd": 10, "category": "unknown"},
            ],
        ),
        _lot_item(
            "2",
            all_skus=[
                {"sku_code_normalized": "PN-1", "effective_line_usd": 2000, "category": "industrial_sensors"},
                {"sku_code_normalized": "PN-3", "effective_line_usd": 0, "category": "toxic_fake"},
            ],
        ),
    ]
    rows, scores = compute_pn_liquidity(processed, category_liquidity, config)
    lot_metrics = compute_lot_avg_pn_liquidity(processed, scores)
    for row in rows:
        value = float(row.get("pn_liquidity", 0.0))
        assert 0.0 <= value <= 1.0
    for metrics in lot_metrics.values():
        value = float(metrics.get("lot_avg_pn_liquidity", 0.0))
        assert 0.0 <= value <= 1.0


def test_t3_zero_volume():
    config = PnLiquidityConfig()
    category_liquidity = _default_category_liquidity()
    processed = [
        _lot_item(
            "1",
            all_skus=[
                {"sku_code_normalized": "PN-ZERO", "effective_line_usd": 0.0, "category": "unknown"},
            ],
        )
    ]
    rows, _ = compute_pn_liquidity(processed, category_liquidity, config)
    row = _find_row(rows, "PNZERO")
    assert float(row["vol_norm"]) == 0.0
    assert float(row["ticket_norm"]) == 0.0


def test_t4_breadth_ceiling():
    config = PnLiquidityConfig(LOT_CEIL=10)
    category_liquidity = _default_category_liquidity()
    processed = []
    for idx in range(1, 16):
        processed.append(
            _lot_item(
                str(idx),
                all_skus=[
                    {"sku_code_normalized": "PN-WIDE", "effective_line_usd": 100.0, "category": "gas_safety"},
                ],
            )
        )
    rows, _ = compute_pn_liquidity(processed, category_liquidity, config)
    row = _find_row(rows, "PNWIDE")
    assert int(row["lot_count"]) == 15
    assert float(row["breadth_norm"]) == 1.0


def test_t5_toxic_fake_category_liquidity():
    config = PnLiquidityConfig()
    category_liquidity = _default_category_liquidity()
    processed = [
        _lot_item(
            "1",
            all_skus=[
                {"sku_code_normalized": "PN-TOX", "effective_line_usd": 2500.0, "category": "toxic_fake"},
            ],
        )
    ]
    rows, _ = compute_pn_liquidity(processed, category_liquidity, config)
    row = _find_row(rows, "PNTOX")
    assert float(row["cat_liq_norm"]) == 0.0


def test_t6_category_normalization_contract():
    config = PnLiquidityConfig()
    category_liquidity = _default_category_liquidity()
    processed = [
        _lot_item(
            "1",
            all_skus=[
                {"sku_code_normalized": "PN-IT", "effective_line_usd": 150.0, "category": "IT Hardware"},
            ],
        )
    ]
    rows, _ = compute_pn_liquidity(processed, category_liquidity, config)
    row = _find_row(rows, "PNIT")
    assert abs(float(row["cat_liq_norm"]) - 0.22) < 1e-9


def test_t7_same_pn_across_two_lots_aggregates_and_no_double_count():
    config = PnLiquidityConfig()
    category_liquidity = _default_category_liquidity()
    processed = [
        _lot_item(
            "1",
            all_skus=[
                {"sku_code_normalized": "PN-X", "effective_line_usd": 1000.0, "category": "gas_safety"},
                {"sku_code_normalized": "", "effective_line_usd": 777.0, "category": "gas_safety"},
            ],
        ),
        _lot_item(
            "2",
            all_skus=[
                {"sku_code_normalized": "PN-X", "effective_line_usd": 2000.0, "category": "gas_safety"},
            ],
        ),
    ]
    rows, _ = compute_pn_liquidity(processed, category_liquidity, config)
    row = _find_row(rows, "PNX")
    assert float(row["vol_raw_usd"]) == 3000.0
    assert int(row["line_count"]) == 2
    assert int(row["lot_count"]) == 2

    vol_sum = sum(float(item.get("vol_raw_usd", 0.0)) for item in rows)
    expected = 0.0
    for lot_item in processed:
        for sku in lot_item["all_skus"]:
            if _resolve_pn_id(sku):
                expected += max(0.0, float(sku.get("effective_line_usd", 0.0) or 0.0))
    assert abs(vol_sum - expected) < 1e-9


def test_t8_zero_impact_on_rank_score10_final_score():
    run_config = RunConfig()
    category_obsolescence = {"gas_safety": 0.7, "industrial_sensors": 0.6, "unknown": 0.4}
    brand_score = {"A": 0.8, "B": 0.6, "Unknown": 0.5}
    category_liquidity = _default_category_liquidity()
    category_volume_proxy = {"gas_safety": 0.02, "industrial_sensors": 0.05, "unknown": 0.01}

    lot_1 = LotRecord(lot_id="1")
    all_skus_1 = [
        {
            "row_index": 1,
            "sku_code_normalized": "PN-1",
            "category": "gas_safety",
            "brand": "A",
            "qty": 2,
            "q_has_qty": True,
            "effective_line_usd": 1500.0,
            "is_in_core_slice": True,
        }
    ]
    core_skus_1 = [all_skus_1[0]]

    lot_2 = LotRecord(lot_id="2")
    all_skus_2 = [
        {
            "row_index": 1,
            "sku_code_normalized": "PN-2",
            "category": "industrial_sensors",
            "brand": "B",
            "qty": 3,
            "q_has_qty": True,
            "effective_line_usd": 900.0,
            "is_in_core_slice": True,
        }
    ]
    core_skus_2 = [all_skus_2[0]]

    for lot, core_skus, all_skus in [(lot_1, core_skus_1, all_skus_1), (lot_2, core_skus_2, all_skus_2)]:
        apply_base_score(
            lot,
            core_skus=core_skus,
            all_skus=all_skus,
            category_obsolescence=category_obsolescence,
            brand_score=brand_score,
            category_liquidity=category_liquidity,
            category_volume_proxy=category_volume_proxy,
            config=run_config,
        )
        apply_final_score(
            lot,
            core_skus=core_skus,
            all_skus=all_skus,
            config=run_config,
        )
    rank_lots([lot_1, lot_2])

    before = {
        "1": {"rank": lot_1.rank, "score_10": lot_1.score_10, "final_score": lot_1.final_score},
        "2": {"rank": lot_2.rank, "score_10": lot_2.score_10, "final_score": lot_2.final_score},
    }
    processed = [
        {"lot": lot_1, "all_skus": all_skus_1, "core_skus": core_skus_1, "metadata": {}},
        {"lot": lot_2, "all_skus": all_skus_2, "core_skus": core_skus_2, "metadata": {}},
    ]
    rows, scores = compute_pn_liquidity(processed, category_liquidity, PnLiquidityConfig())
    _ = compute_lot_avg_pn_liquidity(processed, scores)
    assert len(rows) > 0

    after = {
        "1": {"rank": lot_1.rank, "score_10": lot_1.score_10, "final_score": lot_1.final_score},
        "2": {"rank": lot_2.rank, "score_10": lot_2.score_10, "final_score": lot_2.final_score},
    }
    assert before == after


def test_t9_no_mutation_of_reference_dicts():
    config = PnLiquidityConfig()
    category_liquidity = _default_category_liquidity()
    category_liquidity_before = copy.deepcopy(category_liquidity)
    processed = [
        _lot_item(
            "1",
            all_skus=[
                {"sku_code_normalized": "PN-IMM", "effective_line_usd": 100.0, "category": "unknown"},
            ],
        )
    ]
    _rows, _scores = compute_pn_liquidity(processed, category_liquidity, config)
    assert category_liquidity == category_liquidity_before


def test_t10_pn_override_from_json(tmp_path):
    override_path = tmp_path / "pn_liquidity.json"
    override_path.write_text(
        json.dumps(
            {
                "_meta": {"version": "1.0"},
                "PN-OVR": 0.95,
            }
        ),
        encoding="utf-8",
    )
    config = PnLiquidityConfig(OVERRIDE_FILE=str(override_path))
    category_liquidity = _default_category_liquidity()
    processed = [
        _lot_item(
            "1",
            all_skus=[
                {"sku_code_normalized": "PN-OVR", "effective_line_usd": 100.0, "category": "unknown"},
            ],
        )
    ]
    rows, scores = compute_pn_liquidity(processed, category_liquidity, config)
    row = _find_row(rows, "PNOVR")
    assert float(row["pn_liquidity"]) == 0.95
    assert "PN_LIQUIDITY_OVERRIDE" in row["flags"]
    assert float(scores["PNOVR"]) == 0.95


def test_ranked_content_hash_deterministic():
    import tempfile
    from pathlib import Path

    import pandas as pd

    from scripts.lot_scoring.run_full_ranking_v341 import _write_content_hash

    df = pd.DataFrame(
        [
            {"lot_id": "2", "rank": 2, "score_10": 7.123456789, "final_score": 0.654321},
            {"lot_id": "1", "rank": 1, "score_10": 8.987654321, "final_score": 0.876543},
        ]
    )
    with tempfile.TemporaryDirectory() as tmp:
        _, sha1 = _write_content_hash(df, Path(tmp), "test", sort_by=["lot_id"])
        h1 = Path(sha1).read_text(encoding="utf-8").strip()
    with tempfile.TemporaryDirectory() as tmp:
        _, sha2 = _write_content_hash(df, Path(tmp), "test", sort_by=["lot_id"])
        h2 = Path(sha2).read_text(encoding="utf-8").strip()
    assert h1 == h2
    assert len(h1) == 64

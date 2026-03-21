import json

from scripts.lot_scoring.cdm import LotRecord
from scripts.lot_scoring.pipeline.score import apply_base_score, apply_final_score
from scripts.lot_scoring.run_config import RunConfig


def _build_lot_snapshot() -> dict:
    config = RunConfig()
    all_skus = [
        {
            "row_index": 1,
            "sku_code_normalized": "A1",
            "category": "industrial_sensors",
            "brand": "brand_a",
            "qty": 10,
            "q_has_qty": True,
            "effective_line_usd": 1200.0,
            "is_in_core_slice": True,
        },
        {
            "row_index": 2,
            "sku_code_normalized": "B1",
            "category": "electrical_components",
            "brand": "brand_b",
            "qty": 20,
            "q_has_qty": True,
            "effective_line_usd": 800.0,
            "is_in_core_slice": True,
        },
        {
            "row_index": 3,
            "sku_code_normalized": "C1",
            "category": "packaging_materials",
            "brand": "brand_c",
            "qty": 30,
            "q_has_qty": True,
            "effective_line_usd": 50.0,
            "is_in_core_slice": False,
        },
    ]
    core_skus = [sku for sku in all_skus if sku.get("is_in_core_slice")]
    category_obsolescence = {
        "industrial_sensors": 0.8,
        "electrical_components": 0.7,
        "packaging_materials": 0.2,
    }
    brand_score = {"brand_a": 0.9, "brand_b": 0.6, "brand_c": 0.4}
    category_liquidity = {
        "industrial_sensors": 0.7,
        "electrical_components": 0.8,
        "packaging_materials": 0.3,
    }
    category_volume_proxy = {
        "industrial_sensors": 0.02,
        "electrical_components": 0.01,
        "packaging_materials": 0.05,
    }
    tail_handling_cost = {
        "industrial_sensors": 7.0,
        "electrical_components": 5.0,
        "packaging_materials": 10.0,
        "_default": 10.0,
    }
    lot = LotRecord(lot_id="lot_det_1")
    apply_base_score(
        lot,
        core_skus=core_skus,
        all_skus=all_skus,
        category_obsolescence=category_obsolescence,
        brand_score=brand_score,
        category_liquidity=category_liquidity,
        category_volume_proxy=category_volume_proxy,
        config=config,
    )
    apply_final_score(
        lot,
        core_skus=core_skus,
        all_skus=all_skus,
        config=config,
        tail_handling_cost=tail_handling_cost,
    )
    return {
        "s1": lot.s1,
        "s2": lot.s2,
        "s3": lot.s3,
        "s4": lot.s4,
        "base_score": lot.base_score,
        "hhi_index": lot.hhi_index,
        "tail_liability_usd": lot.tail_liability_usd,
        "tail_distinct_sku_count": lot.tail_distinct_sku_count,
        "penny_line_ratio": lot.penny_line_ratio,
        "core_distinct_sku_count": lot.core_distinct_sku_count,
        "m_hustle": lot.m_hustle,
        "m_concentration": lot.m_concentration,
        "m_tail": lot.m_tail,
        "m_liquidity_floor": lot.m_liquidity_floor,
        "m_obsolescence_floor": lot.m_obsolescence_floor,
        "final_score": lot.final_score,
        "score_10": lot.score_10,
    }


def test_determinism_score_snapshot():
    snap1 = _build_lot_snapshot()
    snap2 = _build_lot_snapshot()
    blob1 = json.dumps(snap1, sort_keys=True)
    blob2 = json.dumps(snap2, sort_keys=True)
    assert blob1 == blob2

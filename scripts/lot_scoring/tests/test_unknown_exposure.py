from scripts.lot_scoring.pipeline.score import compute_unknown_exposure
from scripts.lot_scoring.tests.test_determinism_score import _build_lot_snapshot


def test_unknown_exposure_zero_when_all_classified():
    all_skus = [
        {"sku_code_normalized": "A1", "category": "industrial_sensors", "q_has_qty": True, "effective_line_usd": 600.0},
        {"sku_code_normalized": "B1", "category": "electrical_components", "q_has_qty": True, "effective_line_usd": 400.0},
    ]
    ratio, unknown_usd = compute_unknown_exposure(all_skus, 1000.0)
    assert ratio == 0.0
    assert unknown_usd == 0.0


def test_unknown_exposure_partial():
    all_skus = [
        {"sku_code_normalized": "U1", "category": "unknown", "q_has_qty": True, "effective_line_usd": 300.0},
        {"sku_code_normalized": "K1", "category": "industrial_sensors", "q_has_qty": True, "effective_line_usd": 500.0},
        {"sku_code_normalized": "K2", "category": "electrical_components", "q_has_qty": True, "effective_line_usd": 200.0},
    ]
    ratio, unknown_usd = compute_unknown_exposure(all_skus, 1000.0)
    assert abs(ratio - 0.30) < 1e-12
    assert unknown_usd == 300.0


def test_unknown_exposure_zero_denominator():
    all_skus = [
        {"sku_code_normalized": "U1", "category": "unknown", "q_has_qty": True, "effective_line_usd": 300.0},
    ]
    ratio, unknown_usd = compute_unknown_exposure(all_skus, 0.0)
    assert ratio == 0.0
    assert unknown_usd == 0.0


def test_unknown_exposure_does_not_change_scoring():
    snapshot = _build_lot_snapshot()
    assert snapshot["final_score"] == 0.454401
    assert snapshot["score_10"] == 5.11

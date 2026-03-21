import json
from copy import deepcopy

from scripts.lot_scoring.cdm import LotRecord
from scripts.lot_scoring.pipeline.brand_classifier import classify_lot_skus
from scripts.lot_scoring.pipeline.brand_metrics import compute_brand_flags, compute_brand_intelligence_summary, compute_cps
from scripts.lot_scoring.pipeline.explain_v4 import compute_v4_scalars
from scripts.lot_scoring.pipeline.intelligence_loader import load_all_brand_profiles, load_brand_profile
from scripts.lot_scoring.pipeline.score import apply_base_score, apply_final_score, rank_lots
from scripts.lot_scoring.run_config import RunConfig
from scripts.lot_scoring.simulation.scoring_kernel import V4Config


def _profile_payload() -> dict:
    return {
        "schema_version": "brand_intelligence_v1",
        "brand": "honeywell",
        "metadata": {"author": "test"},
        "tuning_params": {
            "alpha_freshness_impact": 0.65,
            "cps_floor": 0.35,
            "reject_abs_usd_ceil": 50000.0,
            "legacy_combinator_mode": "max",
        },
        "verticals": {
            "hard_industrial": {
                "tier": "core",
                "purity_weight": 1.0,
                "obsolescence_score": 0.25,
                "freshness_score": 0.80,
                "reject": False,
            },
            "system_electronics": {
                "tier": "secondary",
                "purity_weight": 0.6,
                "obsolescence_score": 0.50,
                "freshness_score": 0.55,
                "reject": False,
            },
            "toxic_waste": {
                "tier": "reject",
                "purity_weight": 0.0,
                "obsolescence_score": 1.0,
                "freshness_score": 0.0,
                "reject": True,
            },
            "unknown_honeywell": {
                "tier": "unknown",
                "purity_weight": 0.2,
                "obsolescence_score": 0.50,
                "reject": False,
                "freshness_score_by_value": {
                    "high_threshold_usd": 500.0,
                    "high": 0.40,
                    "low": 0.20,
                },
            },
        },
        "category_mapping": {
            "keywords": {
                "safety relay": "hard_industrial",
                "controller module": "system_electronics",
            },
            "fallback_vertical": "unknown_honeywell",
        },
        "legacy_patterns": [
            {"pattern": "^ML1.*", "pattern_type": "regex", "penalty": 0.40, "reason": "legacy"},
            {"pattern": "ML1", "pattern_type": "substring", "penalty": 0.25, "reason": "legacy"},
        ],
        "classification_precedence": [
            "legacy_patterns",
            "category_mapping.keywords",
            "fallback_vertical",
        ],
    }


def _write_profile(tmp_path):
    profile_path = tmp_path / "honeywell.json"
    profile_path.write_text(json.dumps(_profile_payload(), ensure_ascii=False), encoding="utf-8")
    return profile_path


def _maps() -> tuple[dict, dict, dict, dict]:
    category_obsolescence = {
        "industrial_sensors": 0.76,
        "gas_safety": 0.86,
        "system_electronics": 0.50,
        "unknown": 0.40,
        "_default": 0.40,
    }
    brand_score = {"honeywell": 0.92, "unknown": 0.45, "_default": 0.50}
    category_liquidity = {"industrial_sensors": 0.70, "gas_safety": 0.75, "system_electronics": 0.55, "_default": 0.50}
    category_volume_proxy = {"industrial_sensors": 0.02, "gas_safety": 0.02, "system_electronics": 0.03, "_default": 0.03}
    return category_obsolescence, brand_score, category_liquidity, category_volume_proxy


def _lot_skus(prefix: str, high: float, low: float) -> list[dict]:
    return [
        {
            "row_index": 1,
            "sku_code_normalized": f"{prefix}-ML1",
            "category": "industrial_sensors",
            "brand": "honeywell",
            "qty": 1.0,
            "q_has_qty": True,
            "effective_line_usd": high,
            "is_in_core_slice": True,
            "description": "safety relay",
        },
        {
            "row_index": 2,
            "sku_code_normalized": f"{prefix}-TAIL",
            "category": "system_electronics",
            "brand": "honeywell",
            "qty": 1.0,
            "q_has_qty": True,
            "effective_line_usd": low,
            "is_in_core_slice": False,
            "description": "controller module",
        },
    ]


def _score_lot(lot_id: str, all_skus: list[dict], maps: tuple[dict, dict, dict, dict]) -> LotRecord:
    category_obsolescence, brand_score, category_liquidity, category_volume_proxy = maps
    run_config = RunConfig()
    lot = LotRecord(lot_id=lot_id)
    core_skus = [sku for sku in all_skus if bool(sku.get("is_in_core_slice"))]
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
    apply_final_score(lot, core_skus=core_skus, all_skus=all_skus, config=run_config)
    return lot


def test_fas_unchanged_with_brand_layer(tmp_path) -> None:
    _write_profile(tmp_path)
    profile = load_brand_profile("honeywell", base_dir=tmp_path)
    assert profile is not None

    maps = _maps()
    base_skus = _lot_skus("L1", 1000.0, 120.0)
    enriched_skus = deepcopy(base_skus)
    classify_lot_skus(enriched_skus, {"honeywell": profile})

    lot_base = _score_lot("L1-base", deepcopy(base_skus), maps)
    lot_enriched = _score_lot("L1-enriched", deepcopy(enriched_skus), maps)
    metadata = {"core_count": 1, "tail_count": 1}
    run_config = RunConfig()
    v4_config = V4Config()

    baseline = compute_v4_scalars(
        lot=lot_base,
        metadata=metadata,
        core_skus=[sku for sku in base_skus if bool(sku.get("is_in_core_slice"))],
        category_obsolescence=maps[0],
        run_config=run_config,
        v4_config=v4_config,
    )
    with_brand = compute_v4_scalars(
        lot=lot_enriched,
        metadata=metadata,
        core_skus=[sku for sku in enriched_skus if bool(sku.get("is_in_core_slice"))],
        category_obsolescence=maps[0],
        run_config=run_config,
        v4_config=v4_config,
    )
    assert json.dumps(baseline, sort_keys=True) == json.dumps(with_brand, sort_keys=True)


def test_ranking_unchanged_with_brand_layer(tmp_path) -> None:
    _write_profile(tmp_path)
    profile = load_brand_profile("honeywell", base_dir=tmp_path)
    assert profile is not None

    maps = _maps()
    lot_a_base = _score_lot("A", _lot_skus("A", 1200.0, 100.0), maps)
    lot_b_base = _score_lot("B", _lot_skus("B", 800.0, 140.0), maps)
    rank_lots([lot_a_base, lot_b_base])
    baseline_order = [lot.lot_id for lot in sorted([lot_a_base, lot_b_base], key=lambda item: item.rank)]

    lot_a_enriched_skus = _lot_skus("A", 1200.0, 100.0)
    lot_b_enriched_skus = _lot_skus("B", 800.0, 140.0)
    classify_lot_skus(lot_a_enriched_skus, {"honeywell": profile})
    classify_lot_skus(lot_b_enriched_skus, {"honeywell": profile})
    lot_a_enriched = _score_lot("A", lot_a_enriched_skus, maps)
    lot_b_enriched = _score_lot("B", lot_b_enriched_skus, maps)
    rank_lots([lot_a_enriched, lot_b_enriched])
    enriched_order = [lot.lot_id for lot in sorted([lot_a_enriched, lot_b_enriched], key=lambda item: item.rank)]

    assert baseline_order == enriched_order
    assert lot_a_base.score_10 == lot_a_enriched.score_10
    assert lot_b_base.score_10 == lot_b_enriched.score_10


def test_determinism_preserved_with_brand_layer(tmp_path) -> None:
    _write_profile(tmp_path)
    profile = load_brand_profile("honeywell", base_dir=tmp_path)
    assert profile is not None

    all_skus_1 = _lot_skus("D", 900000.0, 100000.0)
    all_skus_2 = deepcopy(all_skus_1)
    classify_lot_skus(all_skus_1, {"honeywell": profile})
    classify_lot_skus(all_skus_2, {"honeywell": profile})

    cps_1 = compute_cps(all_skus_1, profile)
    cps_2 = compute_cps(all_skus_2, profile)
    flags_1 = compute_brand_flags(cps_1, profile)
    flags_2 = compute_brand_flags(cps_2, profile)
    summary_1 = compute_brand_intelligence_summary(all_skus_1, profile, cps_1, flags_1)
    summary_2 = compute_brand_intelligence_summary(all_skus_2, profile, cps_2, flags_2)

    assert json.dumps(summary_1, sort_keys=True) == json.dumps(summary_2, sort_keys=True)


def test_behavior_with_empty_brand_folder_noop(tmp_path) -> None:
    profiles = load_all_brand_profiles(base_dir=tmp_path)
    assert profiles == {}

    skus = _lot_skus("E", 1000.0, 100.0)
    before = json.dumps(skus, sort_keys=True)
    classify_lot_skus(skus, profiles)
    after = json.dumps(skus, sort_keys=True)
    assert before == after

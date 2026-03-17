import json

import pytest

from scripts.lot_scoring.pipeline.brand_classifier import classify_lot_skus, classify_sku, detect_brand
from scripts.lot_scoring.pipeline.brand_metrics import compute_brand_flags, compute_brand_intelligence_summary, compute_cps
from scripts.lot_scoring.pipeline.intelligence_loader import (
    load_all_brand_profiles,
    load_brand_profile,
    validate_brand_profile,
)


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
            {
                "pattern": "^ML1.*",
                "pattern_type": "regex",
                "penalty": 0.40,
                "reason": "legacy generation",
            },
            {
                "pattern": "ML1",
                "pattern_type": "substring",
                "penalty": 0.25,
                "reason": "legacy substring",
            },
        ],
        "classification_precedence": [
            "legacy_patterns",
            "category_mapping.keywords",
            "fallback_vertical",
        ],
    }


def _write_profile(tmp_path, payload: dict | None = None):
    profile_path = tmp_path / "honeywell.json"
    profile_path.write_text(json.dumps(payload or _profile_payload(), ensure_ascii=False), encoding="utf-8")
    return profile_path


def test_validate_brand_profile_ok() -> None:
    assert validate_brand_profile(_profile_payload()) == []


def test_load_brand_profile_missing_returns_none(tmp_path) -> None:
    assert load_brand_profile("honeywell", base_dir=tmp_path) is None


def test_load_all_brand_profiles_empty_dir(tmp_path) -> None:
    assert load_all_brand_profiles(base_dir=tmp_path) == {}


def test_detect_brand_and_combinator_max(tmp_path) -> None:
    _write_profile(tmp_path)
    profile = load_brand_profile("honeywell", base_dir=tmp_path)
    assert profile is not None
    profiles = {"honeywell": profile}
    sku = {
        "brand": "honeywell",
        "sku_code_normalized": "ML1-ABC",
        "description": "safety relay module",
        "effective_line_usd": 1000.0,
        "q_has_qty": True,
    }
    assert detect_brand(sku, profiles) == "honeywell"
    result = classify_sku(sku, profile)
    assert result["brand_vertical"] == "hard_industrial"
    assert result["brand_legacy_penalty"] == pytest.approx(0.40, abs=1e-9)


def test_brand_obs_with_and_without_legacy(tmp_path) -> None:
    _write_profile(tmp_path)
    profile = load_brand_profile("honeywell", base_dir=tmp_path)
    assert profile is not None

    sku_no_legacy = {
        "brand": "honeywell",
        "sku_code_normalized": "NEW123",
        "description": "safety relay",
        "effective_line_usd": 1000.0,
        "q_has_qty": True,
    }
    sku_with_legacy = {
        "brand": "honeywell",
        "sku_code_normalized": "ML1-123",
        "description": "safety relay",
        "effective_line_usd": 1000.0,
        "q_has_qty": True,
    }
    result_no_legacy = classify_sku(sku_no_legacy, profile)
    result_with_legacy = classify_sku(sku_with_legacy, profile)
    assert result_no_legacy["brand_obs"] == pytest.approx(0.12, abs=1e-6)
    assert result_with_legacy["brand_obs"] == pytest.approx(0.172, abs=1e-6)


def test_unknown_honeywell_dynamic_freshness(tmp_path) -> None:
    _write_profile(tmp_path)
    profile = load_brand_profile("honeywell", base_dir=tmp_path)
    assert profile is not None

    expensive_unknown = {
        "brand": "honeywell",
        "sku_code_normalized": "X1",
        "description": "unmapped product",
        "effective_line_usd": 2000.0,
        "q_has_qty": True,
    }
    cheap_unknown = {
        "brand": "honeywell",
        "sku_code_normalized": "X2",
        "description": "unmapped product",
        "effective_line_usd": 50.0,
        "q_has_qty": True,
    }
    expensive_payload = classify_sku(expensive_unknown, profile)
    cheap_payload = classify_sku(cheap_unknown, profile)

    assert expensive_payload["brand_vertical"] == "unknown_honeywell"
    assert cheap_payload["brand_vertical"] == "unknown_honeywell"
    assert expensive_payload["brand_freshness_score"] == pytest.approx(0.40, abs=1e-9)
    assert cheap_payload["brand_freshness_score"] == pytest.approx(0.20, abs=1e-9)
    assert expensive_payload["brand_obs"] == pytest.approx(0.37, abs=1e-6)
    assert cheap_payload["brand_obs"] == pytest.approx(0.435, abs=1e-6)


def test_cps_normal_zero_negative_and_dilution(tmp_path) -> None:
    _write_profile(tmp_path)
    profile = load_brand_profile("honeywell", base_dir=tmp_path)
    assert profile is not None

    normal = [
        {"brand_detected": "honeywell", "brand_vertical": "hard_industrial", "effective_line_usd": 100.0, "q_has_qty": True},
        {"brand_detected": "honeywell", "brand_vertical": "system_electronics", "effective_line_usd": 50.0, "q_has_qty": True},
        {"brand_detected": "honeywell", "brand_vertical": "toxic_waste", "effective_line_usd": 20.0, "q_has_qty": True},
    ]
    normal_result = compute_cps(normal, profile)
    assert normal_result.cps == pytest.approx(110.0 / 170.0, abs=1e-6)

    zero_result = compute_cps([], profile)
    assert zero_result.cps == 0.0
    assert "BRAND_NO_PRICING" in compute_brand_flags(zero_result, profile)

    negative = [
        {"brand_detected": "honeywell", "brand_vertical": "toxic_waste", "effective_line_usd": 100.0, "q_has_qty": True},
    ]
    negative_result = compute_cps(negative, profile)
    assert negative_result.cps == -1.0

    dilution = [
        {"brand_detected": "honeywell", "brand_vertical": "hard_industrial", "effective_line_usd": 900000.0, "q_has_qty": True},
        {"brand_detected": "honeywell", "brand_vertical": "toxic_waste", "effective_line_usd": 100000.0, "q_has_qty": True},
    ]
    dilution_result = compute_cps(dilution, profile)
    dilution_flags = compute_brand_flags(dilution_result, profile)
    assert dilution_result.cps == pytest.approx(0.8, abs=1e-9)
    assert "HIGH_REJECT_ABSOLUTE" in dilution_flags


def test_compute_brand_intelligence_summary_contract(tmp_path) -> None:
    _write_profile(tmp_path)
    profile = load_brand_profile("honeywell", base_dir=tmp_path)
    assert profile is not None

    skus = [
        {"brand_detected": "honeywell", "brand_vertical": "hard_industrial", "effective_line_usd": 1000.0, "brand_obs": 0.12},
        {"brand_detected": "honeywell", "brand_vertical": "toxic_waste", "effective_line_usd": 100.0, "brand_obs": 1.0},
    ]
    cps_result = compute_cps(skus, profile)
    flags = compute_brand_flags(cps_result, profile)
    summary = compute_brand_intelligence_summary(skus, profile, cps_result, flags)

    assert summary["brand"] == "honeywell"
    assert "cps" in summary
    assert "usd_reject" in summary
    assert "flags" in summary
    assert "verticals_breakdown" in summary
    assert summary["verticals_breakdown"]["hard_industrial"]["usd"] == pytest.approx(1000.0, abs=1e-9)
    assert summary["verticals_breakdown"]["toxic_waste"]["usd"] == pytest.approx(100.0, abs=1e-9)


def test_classify_lot_skus_enriches_only_known_brand(tmp_path) -> None:
    _write_profile(tmp_path)
    profiles = load_all_brand_profiles(base_dir=tmp_path)
    assert "honeywell" in profiles

    all_skus = [
        {"brand": "honeywell", "sku_code_normalized": "NEW1", "description": "safety relay", "effective_line_usd": 10.0},
        {"brand": "siemens", "sku_code_normalized": "NEW2", "description": "safety relay", "effective_line_usd": 20.0},
    ]
    classify_lot_skus(all_skus, profiles)

    assert "brand_vertical" in all_skus[0]
    assert "brand_vertical" not in all_skus[1]

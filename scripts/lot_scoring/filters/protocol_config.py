from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProtocolConfig:
    """Static protocol constants for Compute Engine v3."""

    schema_version: str = "compute_engine_v3_protocol_2_1_4"

    # Filter 0 thresholds
    f0_legit_count_min: int = 5
    f0_non_positive_review_min: float = 0.05
    f0_non_positive_stop_min: float = 0.20
    f0_outlier_review_min: float = 0.70
    f0_outlier_stop_min: float = 0.90
    f0_duplicate_divergence_ratio: float = 3.0
    f0_price_missing_review_min: float = 0.10
    f0_price_missing_stop_min: float = 0.40

    # Filter 1 thresholds
    f1_ab_min: float = 0.60
    f1_e_max: float = 0.20
    f1_largest_max: float = 0.45
    f1_match_conf_min: float = 0.70
    f1_used_share_stress_min: float = 0.50
    f1_used_discount: float = 0.60

    # Filter 2 thresholds
    f2_core70_ratio: float = 0.70
    f2_largest_max: float = 0.50
    f2_mass_anchor_qty_min: float = 1000.0
    f2_mass_anchor_review_min: float = 0.10
    f2_mass_anchor_stop_min: float = 0.25

    # Filter 3 ticket threshold
    f3_ticket_threshold_rub: float = 100_000.0

    # Filter 4 defaults
    filter4_top_n_default: int = 5

    # Canonical buckets
    bucket_a: tuple[str, ...] = (
        "gas_safety",
        "fire_safety",
        "industrial_sensors",
        "valves_actuators",
    )
    bucket_b: tuple[str, ...] = ("hvac_components",)
    bucket_e: tuple[str, ...] = (
        "it_hardware",
        "packaging_materials",
        "construction_supplies",
        "toxic_fake",
        "unknown",
    )

    # Human-readable outputs
    filter4_fatal_items: tuple[str, ...] = (
        "vendor_lock_or_firmware_lock",
        "legal_non_resalable",
        "critical_revision_incompatibility_or_project_lock",
    )
    filter4_market_rule: tuple[str, ...] = (
        "dead_market_top3_count>=2 => STOP",
        "dead_market_top3_count==1 => REVIEW",
        "else => PASS",
    )
    filter4_physical_rule: tuple[str, ...] = (
        "high_risk_share>20% => REVIEW",
        "(high_risk_share+medium_risk_share)>30% => REVIEW/SKIP",
    )

    # JSON keys with direct CalculatedLotCost equivalents in RUB
    line_value_rub_keys: tuple[str, ...] = (
        "CalculatedLotCost",
        "calculatedlotcost",
        "line_value_rub",
        "linevalue_rub",
        "line_value",
        "lot_value_rub",
        "total_rub",
        "price_rub_total",
    )
    unit_price_rub_keys: tuple[str, ...] = (
        "unit_price_rub",
        "unitprice_rub",
        "price_rub",
        "calculated_unit_price_rub",
    )
    state_keys: tuple[str, ...] = ("state", "condition_state", "item_state")
    brand_keys: tuple[str, ...] = ("brand", "brand_norm")
    category_keys: tuple[str, ...] = ("category", "category_norm")
    price_found_keys: tuple[str, ...] = ("PriceFound", "price_found", "pricefound")

    # Markers
    unknown_label: str = "unknown"
    used_markers: tuple[str, ...] = (
        "used",
        "б/у",
        "бу",
        "refurb",
        "refurbished",
        "second hand",
        "secondhand",
        "demo",
        "демо",
    )
    new_markers: tuple[str, ...] = ("new", "нов", "unused", "неисп")

    top_slice_ratios: tuple[float, ...] = (0.20, 0.40, 0.80)
    metadata_sha_ref_files: tuple[str, ...] = (
        "scripts/lot_scoring/data/brand_score.json",
        "scripts/lot_scoring/data/category_obsolescence.json",
        "scripts/lot_scoring/data/category_liquidity.json",
        "scripts/lot_scoring/data/category_volume_proxy.json",
        "scripts/lot_scoring/data/taxonomy_version.json",
    )

    summary_columns: tuple[str, ...] = (
        "lot_id",
        "f0_status",
        "f1_status",
        "f2_status",
        "score_100",
        "class",
        "total_value_rub",
        "adjusted_value_rub",
        "share_a",
        "share_b",
        "share_e",
        "share_used",
        "largest_sku_share",
        "core70_value_rub",
        "entry_price_rub",
        "sm",
        "core_coverage",
        "ticket_pct",
        "core_sku_count",
        "brand_count_core",
        "unknown_value_share",
        "unknown_exposure",
        "hhi",
        "mass_anchor_status",
        "filter4_candidate",
    )

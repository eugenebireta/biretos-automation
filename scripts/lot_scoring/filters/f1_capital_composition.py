from __future__ import annotations

from typing import Any

from scripts.lot_scoring.filters.protocol_config import ProtocolConfig
from scripts.lot_scoring.filters.protocol_metrics import aggregate_by_sku, largest_share, shares, used_stress_adjust
from scripts.lot_scoring.pipeline.helpers import to_float


def evaluate_f1(
    *,
    lines: list[dict[str, Any]],
    total_value_rub: float,
    match_confidence_weighted: float | None,
    config: ProtocolConfig,
) -> dict[str, Any]:
    used_info = used_stress_adjust(lines, config)
    share_used = to_float(used_info.get("share_used"), 0.0)
    used_stress_applied = bool(used_info.get("used_stress_applied"))
    adjusted_total = max(0.0, to_float(used_info.get("adjusted_total_value_rub"), 0.0))

    base_shares = shares(lines, config, total_value_rub, value_key="line_value_rub")
    adjusted_shares = shares(lines, config, adjusted_total, value_key="adjusted_value_rub")

    aggregated = aggregate_by_sku(lines, value_key="line_value_rub")
    largest_base = largest_share(aggregated, total_value_rub, value_key="sku_value_rub")
    largest_adjusted = largest_share(aggregated, adjusted_total, value_key="sku_adjusted_value_rub")

    effective_shares = adjusted_shares if used_stress_applied else base_shares
    effective_largest = largest_adjusted if used_stress_applied else largest_base
    share_ab = to_float(effective_shares.get("share_a"), 0.0) + to_float(effective_shares.get("share_b"), 0.0)
    share_e = to_float(effective_shares.get("share_e"), 0.0)

    fail_reasons: list[str] = []
    if share_ab + 1e-9 < config.f1_ab_min:
        fail_reasons.append("AB_LT_60")
    if share_e - 1e-9 > config.f1_e_max:
        fail_reasons.append("E_GT_20")
    if effective_largest - 1e-9 > config.f1_largest_max:
        fail_reasons.append("LARGEST_GT_45")

    confidence_check_applied = match_confidence_weighted is not None
    if confidence_check_applied and match_confidence_weighted + 1e-9 < config.f1_match_conf_min:
        fail_reasons.append("MATCH_CONF_LT_70")

    status = "PASS" if not fail_reasons else "STOP"
    return {
        "status": status,
        "fail_reasons": fail_reasons,
        "share_a": to_float(effective_shares.get("share_a"), 0.0),
        "share_b": to_float(effective_shares.get("share_b"), 0.0),
        "share_e": share_e,
        "largest_sku_share": effective_largest,
        "share_used": share_used,
        "used_stress_applied": used_stress_applied,
        "adjusted_value_rub": adjusted_total if used_stress_applied else total_value_rub,
        "base_share_a": to_float(base_shares.get("share_a"), 0.0),
        "base_share_b": to_float(base_shares.get("share_b"), 0.0),
        "base_share_e": to_float(base_shares.get("share_e"), 0.0),
        "base_largest_sku_share": largest_base,
        "match_confidence_weighted": match_confidence_weighted,
        "match_confidence_applied": confidence_check_applied,
    }

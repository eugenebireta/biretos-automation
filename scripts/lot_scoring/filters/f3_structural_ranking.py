from __future__ import annotations

from typing import Any

from scripts.lot_scoring.filters.protocol_metrics import core_coverage_ratio, sm_ratio


def _class_from_score(score_100: int) -> str:
    if score_100 >= 90:
        return "Elite"
    if score_100 >= 80:
        return "Strong"
    if score_100 >= 70:
        return "Good"
    if score_100 >= 60:
        return "Acceptable"
    return "Weak"


def _block_i(share_a: float, share_b: float, share_e: float) -> tuple[int, dict[str, int]]:
    if share_a >= 0.60:
        a_points = 20
    elif share_a >= 0.50:
        a_points = 16
    elif share_a >= 0.40:
        a_points = 12
    elif share_a >= 0.30:
        a_points = 8
    else:
        a_points = 4

    ab = share_a + share_b
    if ab >= 0.80:
        ab_points = 15
    elif ab >= 0.70:
        ab_points = 12
    elif ab >= 0.60:
        ab_points = 9
    elif ab >= 0.50:
        ab_points = 6
    else:
        ab_points = 0

    if share_e > 0.20:
        e_penalty = -5
    elif share_e >= 0.10:
        e_penalty = -3
    else:
        e_penalty = 0

    total = max(0, min(40, a_points + ab_points + e_penalty))
    return total, {"a_points": a_points, "ab_points": ab_points, "e_penalty": e_penalty}


def _block_ii(total_value_rub: float, entry_price_rub: float | None, largest_share: float, confidence: float | None) -> tuple[int, dict[str, int]]:
    sm = sm_ratio(total_value_rub, entry_price_rub)
    if entry_price_rub is None:
        sm_points = 0
    elif sm >= 4.0:
        sm_points = 15
    elif sm >= 3.0:
        sm_points = 10
    elif sm >= 2.0:
        sm_points = 5
    else:
        sm_points = 0

    if largest_share < 0.30:
        concentration_points = 10
    elif largest_share < 0.40:
        concentration_points = 6
    elif largest_share <= 0.50:
        concentration_points = 3
    else:
        concentration_points = 0

    if confidence is None:
        confidence_points = 2
    elif confidence >= 0.85:
        confidence_points = 3
    elif confidence >= 0.70:
        confidence_points = 2
    else:
        confidence_points = 0

    total = max(0, min(28, sm_points + concentration_points + confidence_points))
    return total, {
        "sm_points": sm_points,
        "concentration_points": concentration_points,
        "confidence_points": confidence_points,
    }


def _block_iii(
    core70_value_rub: float,
    entry_price_rub: float | None,
    share_used: float | None,
    used_signal_available: bool,
    ticket_pct: float,
) -> tuple[int, dict[str, int]]:
    coverage = core_coverage_ratio(core70_value_rub, entry_price_rub)
    if entry_price_rub is None:
        core_coverage_points = 0
    elif coverage >= 1.5:
        core_coverage_points = 15
    elif coverage >= 1.0:
        core_coverage_points = 10
    elif coverage >= 0.70:
        core_coverage_points = 5
    else:
        core_coverage_points = 0

    if not used_signal_available or share_used is None:
        used_points = 6
    elif share_used <= 0.30:
        used_points = 10
    elif share_used <= 0.50:
        used_points = 6
    else:
        used_points = 3

    if ticket_pct >= 0.40:
        ticket_points = 3
    elif ticket_pct >= 0.20:
        ticket_points = 2
    else:
        ticket_points = 1

    total = max(0, min(28, core_coverage_points + used_points + ticket_points))
    return total, {
        "core_coverage_points": core_coverage_points,
        "used_points": used_points,
        "ticket_points": ticket_points,
    }


def _block_iv(core_sku_count: int, brand_count_core: int) -> tuple[int, dict[str, int]]:
    if core_sku_count <= 25:
        sku_points = 2
    elif core_sku_count <= 60:
        sku_points = 1
    else:
        sku_points = 0

    if 1 <= brand_count_core <= 2:
        brand_points = 2
    elif 3 <= brand_count_core <= 4:
        brand_points = 1
    else:
        brand_points = 0

    total = max(0, min(4, sku_points + brand_points))
    return total, {"core_sku_points": sku_points, "brand_points": brand_points}


def evaluate_f3(
    *,
    f1_status: str,
    f2_status: str,
    share_a: float,
    share_b: float,
    share_e: float,
    total_value_rub: float,
    entry_price_rub: float | None,
    largest_sku_share: float,
    match_confidence_weighted: float | None,
    core70_value_rub: float,
    share_used: float | None,
    used_signal_available: bool,
    ticket_pct: float,
    core_sku_count: int,
    brand_count_core: int,
) -> dict[str, Any]:
    if f1_status != "PASS" or f2_status != "PASS":
        return {
            "score_100": 0,
            "class": "Weak",
            "block_i": 0,
            "block_ii": 0,
            "block_iii": 0,
            "block_iv": 0,
            "details": {
                "skip_reason": "F3_REQUIRES_F1_PASS_AND_F2_PASS",
            },
        }

    block_i, block_i_details = _block_i(share_a, share_b, share_e)
    block_ii, block_ii_details = _block_ii(total_value_rub, entry_price_rub, largest_sku_share, match_confidence_weighted)
    block_iii, block_iii_details = _block_iii(
        core70_value_rub,
        entry_price_rub,
        share_used,
        used_signal_available,
        ticket_pct,
    )
    block_iv, block_iv_details = _block_iv(core_sku_count, brand_count_core)

    score_100 = int(max(0, min(100, block_i + block_ii + block_iii + block_iv)))
    return {
        "score_100": score_100,
        "class": _class_from_score(score_100),
        "block_i": block_i,
        "block_ii": block_ii,
        "block_iii": block_iii,
        "block_iv": block_iv,
        "details": {
            "block_i": block_i_details,
            "block_ii": block_ii_details,
            "block_iii": block_iii_details,
            "block_iv": block_iv_details,
        },
    }

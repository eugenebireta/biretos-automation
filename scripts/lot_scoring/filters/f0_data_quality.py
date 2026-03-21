from __future__ import annotations

from typing import Any

from scripts.lot_scoring.filters.protocol_config import ProtocolConfig
from scripts.lot_scoring.filters.protocol_metrics import duplicate_divergence_flags, largest_share
from scripts.lot_scoring.pipeline.helpers import to_float


def evaluate_f0(
    *,
    lines: list[dict[str, Any]],
    aggregated: list[dict[str, Any]],
    total_value_rub: float,
    config: ProtocolConfig,
) -> dict[str, Any]:
    legit_lines = [line for line in lines if not bool(line.get("is_fake"))]
    legit_count = len(legit_lines)
    stop_reasons: list[str] = []
    review_reasons: list[str] = []

    missing_value_rows = sum(1 for line in legit_lines if line.get("line_value_rub_raw") is None)
    if legit_count == 0 or missing_value_rows == legit_count:
        stop_reasons.append("DATA_INVALID")

    if legit_count < config.f0_legit_count_min:
        stop_reasons.append("LEGIT_COUNT_LT_5")

    non_positive_count = sum(1 for line in legit_lines if bool(line.get("is_non_positive")))
    non_positive_ratio_rows = (non_positive_count / legit_count) if legit_count else 0.0

    abs_total = sum(abs(to_float(line.get("line_value_rub_raw"), 0.0)) for line in legit_lines)
    abs_non_positive = sum(
        abs(to_float(line.get("line_value_rub_raw"), 0.0))
        for line in legit_lines
        if bool(line.get("is_non_positive"))
    )
    non_positive_ratio_abs_value = (abs_non_positive / abs_total) if abs_total > 0 else non_positive_ratio_rows

    if (
        non_positive_ratio_rows > config.f0_non_positive_stop_min
        or non_positive_ratio_abs_value > config.f0_non_positive_stop_min
    ):
        stop_reasons.append("NON_POSITIVE_GT_20")
    elif (
        non_positive_ratio_rows >= config.f0_non_positive_review_min
        or non_positive_ratio_abs_value >= config.f0_non_positive_review_min
    ):
        review_reasons.append("NON_POSITIVE_5_TO_20")

    largest = largest_share(aggregated, total_value_rub, value_key="sku_value_rub")
    if largest > config.f0_outlier_stop_min:
        stop_reasons.append("OUTLIER_GT_90")
    elif largest >= config.f0_outlier_review_min:
        review_reasons.append("OUTLIER_70_TO_90")

    duplicate_flag, duplicate_skus = duplicate_divergence_flags(
        legit_lines,
        divergence_ratio=config.f0_duplicate_divergence_ratio,
    )
    if duplicate_flag:
        review_reasons.append("DUPLICATE_DIVERGENCE_GT_3")

    price_missing_count = sum(1 for line in legit_lines if bool(line.get("is_price_missing")))
    price_missing_ratio = (price_missing_count / legit_count) if legit_count else 0.0
    if price_missing_ratio > config.f0_price_missing_stop_min:
        stop_reasons.append("PRICE_MISSING_GT_40")
    elif price_missing_ratio >= config.f0_price_missing_review_min:
        review_reasons.append("PRICE_MISSING_10_TO_40")

    status = "PASS"
    if stop_reasons:
        status = "STOP"
    elif review_reasons:
        status = "REVIEW"

    return {
        "status": status,
        "stop_reasons": sorted(set(stop_reasons)),
        "review_reasons": sorted(set(review_reasons)),
        "legit_count": legit_count,
        "non_positive_ratio_rows": non_positive_ratio_rows,
        "non_positive_ratio_abs_value": non_positive_ratio_abs_value,
        "price_missing_ratio_rows": price_missing_ratio,
        "largest_sku_share": largest,
        "duplicate_sku_keys": sorted(set(duplicate_skus)),
    }

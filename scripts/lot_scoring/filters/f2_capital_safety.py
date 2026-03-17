from __future__ import annotations

from typing import Any

from scripts.lot_scoring.filters.protocol_config import ProtocolConfig
from scripts.lot_scoring.filters.protocol_metrics import core70, largest_share
from scripts.lot_scoring.pipeline.helpers import to_float, to_str


def evaluate_f2(
    *,
    aggregated: list[dict[str, Any]],
    total_value_rub: float,
    entry_price_rub: float | None,
    config: ProtocolConfig,
) -> dict[str, Any]:
    core70_slice, core70_value = core70(aggregated, total_value_rub, config)
    largest = largest_share(aggregated, total_value_rub, value_key="sku_value_rub")

    stop_reasons: list[str] = []
    review_reasons: list[str] = []

    if entry_price_rub is None:
        review_reasons.append("NEEDS_ENTRYPRICE")
    elif core70_value + 1e-9 < entry_price_rub:
        stop_reasons.append("CORE70_LT_ENTRYPRICE")

    if largest - 1e-9 > config.f2_largest_max:
        stop_reasons.append("LARGEST_GT_50")

    mass_anchor_status = "PASS"
    mass_anchor_hits: list[dict[str, Any]] = []
    for sku in aggregated:
        qty = max(0.0, to_float(sku.get("qty_total"), 0.0))
        if qty + 1e-9 < config.f2_mass_anchor_qty_min:
            continue
        sku_value = max(0.0, to_float(sku.get("sku_value_rub"), 0.0))
        share = (sku_value / total_value_rub) if total_value_rub > 0 else 0.0
        mass_anchor_hits.append(
            {
                "sku": to_str(sku.get("sku")),
                "qty_total": qty,
                "value_share": share,
            }
        )
        if share + 1e-9 >= config.f2_mass_anchor_stop_min:
            mass_anchor_status = "STOP"
            stop_reasons.append("MASS_ANCHOR_STOP")
        elif share + 1e-9 >= config.f2_mass_anchor_review_min and mass_anchor_status != "STOP":
            mass_anchor_status = "REVIEW"
            review_reasons.append("MASS_ANCHOR_REVIEW")

    status = "PASS"
    if stop_reasons:
        status = "STOP"
    elif review_reasons:
        status = "REVIEW"

    return {
        "status": status,
        "stop_reasons": sorted(set(stop_reasons)),
        "review_reasons": sorted(set(review_reasons)),
        "core70_value_rub": core70_value,
        "core70_slice": core70_slice,
        "largest_sku_share": largest,
        "entry_price_rub": entry_price_rub,
        "mass_anchor_status": mass_anchor_status,
        "mass_anchor_hits": mass_anchor_hits,
        "buy_allowed": status == "PASS" and entry_price_rub is not None,
    }

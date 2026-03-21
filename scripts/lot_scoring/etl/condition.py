from __future__ import annotations

from scripts.lot_scoring.etl.etl_config import EtlConfig
from scripts.lot_scoring.pipeline.helpers import clamp, to_float


def apply_condition_floor(skus: list[dict], config: EtlConfig) -> list[dict]:
    adjusted: list[dict] = []
    for original in skus:
        sku = dict(original)
        if bool(sku.get("is_fake")):
            adjusted.append(sku)
            continue

        condition_raw = to_float(sku.get("condition_raw"), 1.0)
        condition_calibrated = clamp(max(condition_raw, config.CONDITION_FLOOR), config.CONDITION_FLOOR, 1.0)
        sku["condition_calibrated"] = condition_calibrated

        base_unit_usd = max(0.0, to_float(sku.get("base_unit_usd"), 0.0))
        raw_qty = max(0.0, to_float(sku.get("raw_qty"), 0.0))
        sku["effective_line_usd"] = base_unit_usd * condition_calibrated * raw_qty
        adjusted.append(sku)
    return adjusted


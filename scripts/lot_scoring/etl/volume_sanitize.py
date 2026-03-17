from __future__ import annotations

from math import ceil, floor

from scripts.lot_scoring.etl.etl_config import EtlConfig
from scripts.lot_scoring.pipeline.helpers import to_float


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * float(len(sorted_values) - 1)
    low_idx = floor(rank)
    high_idx = ceil(rank)
    low_value = sorted_values[low_idx]
    high_value = sorted_values[high_idx]
    if low_idx == high_idx:
        return low_value
    weight = rank - float(low_idx)
    return low_value + (high_value - low_value) * weight


def apply_qty_cap(skus: list[dict], config: EtlConfig) -> tuple[list[dict], float]:
    legit_raw_qty: list[float] = []
    for sku in skus:
        if bool(sku.get("is_fake")):
            continue
        legit_raw_qty.append(max(0.0, to_float(sku.get("raw_qty"), 0.0)))

    p95 = _percentile(legit_raw_qty, config.QTY_CAP_PERCENTILE)
    qty_cap = max(p95 * config.QTY_CAP_MULTIPLIER, config.QTY_CAP_FLOOR)

    sanitized: list[dict] = []
    for original in skus:
        sku = dict(original)
        if bool(sku.get("is_fake")):
            sku["qty"] = 0.0
            sanitized.append(sku)
            continue
        raw_qty = max(0.0, to_float(sku.get("raw_qty"), 0.0))
        sku["qty"] = min(raw_qty, qty_cap)
        sanitized.append(sku)
    return sanitized, qty_cap


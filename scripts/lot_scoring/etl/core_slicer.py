from __future__ import annotations

from statistics import median

from scripts.lot_scoring.etl.etl_config import EtlConfig
from scripts.lot_scoring.pipeline.helpers import to_float, to_str


def _effective_usd(sku: dict) -> float:
    return max(0.0, to_float(sku.get("effective_line_usd"), 0.0))


def _sku_tiebreaker(sku: dict) -> str:
    code = to_str(sku.get("sku_code_normalized"))
    if code:
        return code.upper()
    row_index = sku.get("row_index")
    if row_index is None:
        return ""
    return str(row_index)


def _first_index_reaching_ratio(values: list[float], ratio: float, total: float) -> int:
    if not values:
        return 0
    running = 0.0
    for idx, value in enumerate(values):
        running += value
        if total > 0 and (running / total) >= ratio:
            return idx
    return len(values) - 1


def apply_adaptive_core_slice(skus: list[dict], config: EtlConfig) -> list[dict]:
    staged = [dict(sku) for sku in skus]
    legit_indices = [idx for idx, sku in enumerate(staged) if not bool(sku.get("is_fake"))]

    for sku in staged:
        if bool(sku.get("is_fake")):
            sku["is_in_core_slice"] = False
        elif "is_in_core_slice" not in sku:
            sku["is_in_core_slice"] = False

    if not legit_indices:
        return staged

    legit_sorted = sorted(
        legit_indices,
        key=lambda idx: (-_effective_usd(staged[idx]), _sku_tiebreaker(staged[idx])),
    )
    legit_values = [_effective_usd(staged[idx]) for idx in legit_sorted]
    total_legit_value = sum(legit_values)

    if total_legit_value <= 0.0:
        fallback_end = min(len(legit_sorted) - 1, config.CORE_BUFFER_ITEMS)
        core_set = set(legit_sorted[: fallback_end + 1])
        for idx, sku in enumerate(staged):
            if not bool(sku.get("is_fake")):
                sku["is_in_core_slice"] = idx in core_set
        return staged

    min_boundary = _first_index_reaching_ratio(legit_values, config.CORE_MIN_VALUE_RATIO, total_legit_value)
    max_boundary = _first_index_reaching_ratio(legit_values, config.CORE_MAX_VALUE_RATIO, total_legit_value)
    max_boundary = max(min_boundary, max_boundary)

    boundary = max_boundary
    if len(legit_values) >= config.GAP_MIN_ITEMS and max_boundary < (len(legit_values) - 1):
        gaps = [legit_values[i] - legit_values[i + 1] for i in range(len(legit_values) - 1)]
        positive_gaps = [gap for gap in gaps if gap > 0.0]
        median_gap = median(positive_gaps) if positive_gaps else 0.0
        if median_gap > 0.0:
            gap_cutoff = config.GAP_MULTIPLIER * float(median_gap)
            for idx in range(min_boundary, max_boundary + 1):
                if gaps[idx] > gap_cutoff:
                    boundary = idx
                    break

    boundary = min(boundary + config.CORE_BUFFER_ITEMS, len(legit_values) - 1)
    core_set = set(legit_sorted[: boundary + 1])

    for idx, sku in enumerate(staged):
        if not bool(sku.get("is_fake")):
            sku["is_in_core_slice"] = idx in core_set

    return staged


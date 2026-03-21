from __future__ import annotations

from dataclasses import dataclass, field

from scripts.lot_scoring.etl.etl_config import EtlConfig
from scripts.lot_scoring.pipeline.helpers import to_float, to_str


class ETLInvariantError(ValueError):
    pass


@dataclass
class AssembledLot:
    core_skus: list[dict]
    all_skus: list[dict]
    metadata: dict[str, float | int]
    soft_flags: list[str] = field(default_factory=list)


def _sku_key(sku: dict, idx: int) -> str:
    normalized = to_str(sku.get("sku_code_normalized"))
    if normalized:
        return normalized.upper()
    base = (
        to_str(sku.get("sku_code"))
        or to_str(sku.get("sku"))
        or to_str(sku.get("part_number"))
        or to_str(sku.get("model"))
    )
    if base:
        return base.upper().replace(" ", "").replace("-", "")
    row_index = sku.get("row_index")
    if row_index is None:
        return f"__row_{idx}"
    return f"__row_{row_index}"


def _sorted_skus(skus: list[dict]) -> list[dict]:
    indexed = list(enumerate(skus))
    return [sku for _, sku in sorted(indexed, key=lambda pair: _sku_key(pair[1], pair[0]))]


def _line_eligible_for_total(sku: dict) -> bool:
    q_has_qty = sku.get("q_has_qty")
    has_qty = q_has_qty is not False
    has_line = sku.get("effective_line_usd") is not None
    return has_qty and has_line


def assemble_for_scoring(
    skus: list[dict],
    *,
    qty_cap: float,
    config: EtlConfig,
) -> AssembledLot:
    if qty_cap < config.QTY_CAP_FLOOR:
        raise ETLInvariantError("INV-10 failed: qty_cap is lower than configured floor.")

    soft_flags: list[str] = []
    staged = [dict(sku) for sku in skus]
    legit_count = 0
    toxic_fake_count = 0

    for idx, sku in enumerate(staged):
        raw_qty = max(0.0, to_float(sku.get("raw_qty"), 0.0))
        qty = max(0.0, to_float(sku.get("qty"), 0.0))
        effective = to_float(sku.get("effective_line_usd"), 0.0)
        is_fake = bool(sku.get("is_fake"))
        is_core = bool(sku.get("is_in_core_slice"))
        category = to_str(sku.get("category"), "unknown").lower()

        if qty > qty_cap + 1e-9:
            raise ETLInvariantError(f"INV-3 failed for SKU #{idx}: qty exceeds qty_cap.")
        if raw_qty + 1e-9 < qty:
            raise ETLInvariantError(f"INV-9 failed for SKU #{idx}: raw_qty is smaller than qty.")
        if effective < -1e-9:
            raise ETLInvariantError(f"INV-7 failed for SKU #{idx}: effective_line_usd is negative.")

        if is_fake:
            toxic_fake_count += 1
            if category != "toxic_fake":
                raise ETLInvariantError(f"INV-1 failed for SKU #{idx}: fake category must be toxic_fake.")
            if abs(effective) > 1e-9 or abs(qty) > 1e-9:
                raise ETLInvariantError(f"INV-1 failed for SKU #{idx}: fake financial/logistics fields not zeroed.")
            if sku.get("q_has_qty") is not False:
                raise ETLInvariantError(f"INV-1 failed for SKU #{idx}: fake q_has_qty must be False.")
            if is_core:
                raise ETLInvariantError(f"INV-1 failed for SKU #{idx}: fake SKU leaked into core.")
            continue

        legit_count += 1
        condition_calibrated = to_float(sku.get("condition_calibrated"), config.CONDITION_FLOOR)
        if condition_calibrated < config.CONDITION_FLOOR - 1e-9 or condition_calibrated > 1.0 + 1e-9:
            raise ETLInvariantError(f"INV-2 failed for SKU #{idx}: condition_calibrated outside [floor,1].")

        base_unit_usd = max(0.0, to_float(sku.get("base_unit_usd"), 0.0))
        expected_effective = base_unit_usd * condition_calibrated * raw_qty
        if abs(effective - expected_effective) > 1e-6:
            raise ETLInvariantError(
                f"INV-4 failed for SKU #{idx}: effective_line_usd not aligned with base*condition*raw_qty."
            )

        if raw_qty > 0.0 and effective <= 0.0:
            soft_flags.append("zero_value_active:1")

    all_skus = _sorted_skus(staged)
    core_skus = [sku for sku in all_skus if bool(sku.get("is_in_core_slice"))]
    tail_skus = [sku for sku in all_skus if not bool(sku.get("is_in_core_slice"))]

    all_keys = {_sku_key(sku, idx) for idx, sku in enumerate(all_skus)}
    core_keys = {_sku_key(sku, idx) for idx, sku in enumerate(core_skus)}
    if not core_keys.issubset(all_keys):
        raise ETLInvariantError("INV-5 failed: core_skus must be a subset of all_skus by key.")
    if legit_count > 0 and not core_skus:
        raise ETLInvariantError("INV-5 failed: non-empty legit lot produced empty core_skus.")

    total_effective_usd = 0.0
    core_effective_usd = 0.0
    for sku in all_skus:
        if _line_eligible_for_total(sku):
            total_effective_usd += max(0.0, to_float(sku.get("effective_line_usd"), 0.0))
    for sku in core_skus:
        if _line_eligible_for_total(sku):
            core_effective_usd += max(0.0, to_float(sku.get("effective_line_usd"), 0.0))

    core_ratio = core_effective_usd / total_effective_usd if total_effective_usd > 0 else 0.0
    if total_effective_usd > 0 and core_ratio < config.CORE_MIN_VALUE_RATIO:
        soft_flags.append(f"low_core_ratio:{core_ratio:.3f}")

    metadata: dict[str, float | int] = {
        "qty_cap": qty_cap,
        "total_effective_usd": total_effective_usd,
        "core_effective_usd": core_effective_usd,
        "core_ratio": core_ratio,
        "core_count": len(core_skus),
        "tail_count": len(tail_skus),
        "legit_count": legit_count,
        "toxic_fake_count": toxic_fake_count,
    }
    return AssembledLot(core_skus=core_skus, all_skus=all_skus, metadata=metadata, soft_flags=soft_flags)


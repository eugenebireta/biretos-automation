from __future__ import annotations

import json
import time
from pathlib import Path

from scripts.lot_scoring.cdm import LotRecord
from scripts.lot_scoring.pipeline.helpers import (
    clamp,
    load_json_dict,
    log_scale_01,
    median_or_zero,
    normalize_category_key,
    to_float,
    to_str,
    weighted_average,
)
from scripts.lot_scoring.run_config import RunConfig


def _debug_log(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    # region agent log
    payload = {
        "sessionId": "2eec37",
        "runId": "pre-fix",
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    log_path = Path(__file__).resolve().parents[3] / "debug-2eec37.log"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    # endregion


def _sku_key(sku: dict, idx: int) -> str:
    normalized = to_str(sku.get("sku_code_normalized"))
    if normalized:
        return normalized.upper()
    base = to_str(sku.get("sku_code")) or to_str(sku.get("sku")) or to_str(sku.get("part_number")) or to_str(sku.get("model"))
    if base:
        return base.upper().replace(" ", "").replace("-", "")
    row_index = sku.get("row_index")
    if row_index is None:
        return f"__row_{idx}"
    return f"__row_{row_index}"


def _line_eligible_for_total(sku: dict) -> bool:
    q_has_qty = sku.get("q_has_qty")
    has_qty = q_has_qty is not False
    has_line = sku.get("effective_line_usd") is not None
    return has_qty and has_line


def _line_effective_usd(sku: dict) -> float:
    return max(0.0, to_float(sku.get("effective_line_usd"), 0.0))


def _resolve_core_and_tail(core_skus: list[dict], all_skus: list[dict]) -> tuple[list[dict], list[dict]]:
    all_sorted = _sorted_skus(all_skus)
    has_core_flag = any("is_in_core_slice" in sku for sku in all_sorted)
    if has_core_flag:
        resolved_core = [sku for sku in all_sorted if bool(sku.get("is_in_core_slice"))]
        resolved_tail = [sku for sku in all_sorted if not bool(sku.get("is_in_core_slice"))]
        if resolved_core:
            return resolved_core, resolved_tail
    core_sorted = _sorted_skus(core_skus)
    core_keys: set[str] = set()
    for idx, sku in enumerate(core_sorted):
        core_keys.add(_sku_key(sku, idx))
    resolved_tail = [sku for idx, sku in enumerate(all_sorted) if _sku_key(sku, idx) not in core_keys]
    return core_sorted, resolved_tail


def _distinct_keys(
    skus: list[dict],
    *,
    require_effective_not_none: bool,
) -> list[str]:
    keys: set[str] = set()
    for idx, sku in enumerate(_sorted_skus(skus)):
        if require_effective_not_none and sku.get("effective_line_usd") is None:
            continue
        keys.add(_sku_key(sku, idx))
    return sorted(keys)


def _total_effective_lot_usd(all_skus: list[dict]) -> float:
    total = 0.0
    eligible_count = 0
    non_eligible_count = 0
    none_line_count = 0
    for sku in _sorted_skus(all_skus):
        if sku.get("effective_line_usd") is None:
            none_line_count += 1
        if _line_eligible_for_total(sku):
            total += _line_effective_usd(sku)
            eligible_count += 1
        else:
            non_eligible_count += 1
    _debug_log(
        "H2",
        "pipeline/score.py:_total_effective_lot_usd",
        "Computed denominator inputs",
        {
            "line_count": len(all_skus),
            "eligible_count": eligible_count,
            "non_eligible_count": non_eligible_count,
            "none_line_count": none_line_count,
            "total_effective_lot_usd": total,
        },
    )
    return total


def compute_hhi(all_skus: list[dict], total_effective_lot_usd: float) -> float:
    if total_effective_lot_usd <= 0:
        _debug_log(
            "H2",
            "pipeline/score.py:compute_hhi",
            "HHI early return due to non-positive total",
            {"line_count": len(all_skus), "total_effective_lot_usd": total_effective_lot_usd, "hhi": 1.0},
        )
        return 1.0
    hhi = 0.0
    share_sum = 0.0
    none_line_count = 0
    for sku in _sorted_skus(all_skus):
        if sku.get("effective_line_usd") is None:
            none_line_count += 1
        share = _line_effective_usd(sku) / total_effective_lot_usd
        share_sum += share
        hhi += share * share
    _debug_log(
        "H2",
        "pipeline/score.py:compute_hhi",
        "Computed HHI with share sum",
        {
            "line_count": len(all_skus),
            "none_line_count": none_line_count,
            "total_effective_lot_usd": total_effective_lot_usd,
            "share_sum": share_sum,
            "hhi_raw": hhi,
        },
    )
    return clamp(hhi, 0.0, 1.0)


def compute_unknown_exposure(all_skus: list[dict], total_effective_lot_usd: float) -> tuple[float, float]:
    if total_effective_lot_usd <= 0:
        return 0.0, 0.0
    unknown_usd = 0.0
    for sku in _sorted_skus(all_skus):
        if not _line_eligible_for_total(sku):
            continue
        category = to_str(sku.get("category"), "unknown").lower()
        if category != "unknown":
            continue
        unknown_usd += _line_effective_usd(sku)
    return unknown_usd / total_effective_lot_usd, unknown_usd


def compute_m_hustle(penny_line_ratio: float, core_distinct_sku_count: int, config: RunConfig) -> float:
    frag_denominator = float(config.FRAG_HIGH - config.FRAG_LOW)
    frag_ratio = clamp((float(core_distinct_sku_count) - float(config.FRAG_LOW)) / frag_denominator, 0.0, 1.0)
    hustle_raw = config.HUSTLE_W_PENNY * penny_line_ratio + config.HUSTLE_W_FRAG * frag_ratio
    return clamp(max(config.HUSTLE_FLOOR, 1.0 - hustle_raw), config.HUSTLE_FLOOR, 1.0)


def compute_m_concentration(hhi_index: float, config: RunConfig) -> float:
    penalty = config.CONC_K * max(0.0, hhi_index - config.HHI_SAFE)
    return clamp(max(config.CONC_FLOOR, 1.0 - penalty), config.CONC_FLOOR, 1.0)


def compute_m_tail(tail_liability_usd: float, total_effective_lot_usd: float, config: RunConfig) -> float:
    penalty_ratio = tail_liability_usd / max(total_effective_lot_usd, 1.0)
    return clamp(max(config.TAIL_FLOOR, 1.0 - penalty_ratio), config.TAIL_FLOOR, 1.0)


def compute_kill_switches(s1: float, s3: float, config: RunConfig) -> tuple[float, float]:
    m_liquidity_floor = config.LIQUIDITY_KILL_MULT if s3 < config.LIQUIDITY_KILL_THRESH else 1.0
    m_obsolescence_floor = config.OBSOLESCENCE_KILL_MULT if s1 < config.OBSOLESCENCE_KILL_THRESH else 1.0
    return m_liquidity_floor, m_obsolescence_floor


def _load_tail_handling_map(config: RunConfig) -> dict[str, float]:
    raw = load_json_dict(config.TAIL_HANDLING_COST_FILE)
    prepared: dict[str, float] = {}
    for key in sorted(raw):
        value = raw[key]
        if isinstance(value, dict):
            parsed = to_float(value.get("per_sku_handling_usd"), config.TAIL_UNKNOWN_DEFAULT_USD)
        else:
            parsed = to_float(value, config.TAIL_UNKNOWN_DEFAULT_USD)
        prepared[str(key)] = max(0.0, parsed)
    if "_default" not in prepared:
        prepared["_default"] = max(0.0, config.TAIL_UNKNOWN_DEFAULT_USD)
    return prepared


def _category_tail_cost(category_value: object, tail_cost_map: dict[str, float], config: RunConfig) -> float:
    normalized = normalize_category_key(category_value)
    if normalized in tail_cost_map:
        return tail_cost_map[normalized]
    if "_default" in tail_cost_map:
        return tail_cost_map["_default"]
    return max(0.0, config.TAIL_UNKNOWN_DEFAULT_USD)


def _compute_tail_liability_usd(tail_skus: list[dict], config: RunConfig, tail_cost_map: dict[str, float]) -> tuple[float, int]:
    tail_keys = _distinct_keys(tail_skus, require_effective_not_none=False)
    category_by_key: dict[str, object] = {}
    for idx, sku in enumerate(_sorted_skus(tail_skus)):
        key = _sku_key(sku, idx)
        if key not in category_by_key:
            category_by_key[key] = sku.get("category")
    per_sku_sum = 0.0
    for key in tail_keys:
        per_sku_sum += _category_tail_cost(category_by_key.get(key), tail_cost_map, config)
    tail_distinct_sku_count = len(tail_keys)
    base_handling = config.BASE_HANDLING_PER_SKU * float(tail_distinct_sku_count)
    return per_sku_sum + base_handling, tail_distinct_sku_count


def _compute_penny_line_ratio(core_skus: list[dict], config: RunConfig) -> float:
    core_lines = _sorted_skus(core_skus)
    if not core_lines:
        return 1.0
    penny_lines = 0
    for sku in core_lines:
        if _line_effective_usd(sku) < config.PENNY_THRESH:
            penny_lines += 1
    return penny_lines / float(len(core_lines))


def _combined_multiplier(
    m_hustle: float,
    m_concentration: float,
    m_tail: float,
    m_liquidity_floor: float,
    m_obsolescence_floor: float,
) -> float:
    return m_hustle * m_concentration * m_tail * m_liquidity_floor * m_obsolescence_floor


def _sorted_skus(skus: list[dict]) -> list[dict]:
    indexed = list(enumerate(skus))
    return [sku for _, sku in sorted(indexed, key=lambda pair: _sku_key(pair[1], pair[0]))]


def _distinct_core_line_values(core_skus: list[dict]) -> list[float]:
    aggregated: dict[str, float] = {}
    for idx, sku in enumerate(_sorted_skus(core_skus)):
        key = _sku_key(sku, idx)
        aggregated[key] = aggregated.get(key, 0.0) + to_float(sku.get("effective_line_usd"), 0.0)
    return [to_float(aggregated[key], 0.0) for key in sorted(aggregated)]


def _compute_s1(
    core_skus: list[dict],
    category_obsolescence: dict,
    brand_score: dict,
) -> float:
    values: list[float] = []
    weights: list[float] = []
    for sku in _sorted_skus(core_skus):
        category = to_str(sku.get("category"), "Unknown")
        brand = to_str(sku.get("brand"), "Unknown")
        obs = to_float(category_obsolescence.get(category, 0.40), 0.40)
        bscore = to_float(brand_score.get(brand, 0.50), 0.50)
        s1_sku = 0.70 * obs + 0.30 * bscore
        values.append(clamp(s1_sku, 0.0, 1.0))
        weights.append(max(0.0, to_float(sku.get("effective_line_usd"), 0.0)))
    return weighted_average(values, weights)


def _compute_s2(core_skus: list[dict], config: RunConfig) -> float:
    line_values = _distinct_core_line_values(core_skus)
    median_deal_usd = median_or_zero(line_values)
    if median_deal_usd <= 0:
        return 0.0
    return log_scale_01(median_deal_usd, config.DEAL_FLOOR, config.DEAL_CEIL)


def _compute_s3(
    core_skus: list[dict],
    category_liquidity: dict,
    brand_score: dict,
) -> float:
    values: list[float] = []
    weights: list[float] = []
    for sku in _sorted_skus(core_skus):
        category = to_str(sku.get("category"), "Unknown")
        brand = to_str(sku.get("brand"), "Unknown")
        liq = to_float(category_liquidity.get(category, 0.30), 0.30)
        brand_boost = to_float(brand_score.get(brand, 0.50), 0.50) * 0.2
        s3_sku = clamp(liq + brand_boost, 0.0, 1.0)
        values.append(s3_sku)
        weights.append(max(0.0, to_float(sku.get("effective_line_usd"), 0.0)))
    return weighted_average(values, weights)


def _compute_s4(
    all_skus: list[dict],
    category_volume_proxy: dict,
    config: RunConfig,
) -> float:
    total_effective_lot_usd = 0.0
    total_vol = 0.0
    for sku in _sorted_skus(all_skus):
        qty = max(0.0, to_float(sku.get("qty"), 0.0))
        category = to_str(sku.get("category"), "Unknown")
        volume_proxy = max(0.0, to_float(category_volume_proxy.get(category, 0.01), 0.01))
        total_effective_lot_usd += max(0.0, to_float(sku.get("effective_line_usd"), 0.0))
        total_vol += qty * volume_proxy
    value_density = total_effective_lot_usd / max(total_vol, 0.01)
    return log_scale_01(value_density, config.VD_FLOOR, config.VD_CEIL)


def apply_base_score(
    lot: LotRecord,
    *,
    core_skus: list[dict],
    all_skus: list[dict],
    category_obsolescence: dict,
    brand_score: dict,
    category_liquidity: dict,
    category_volume_proxy: dict,
    config: RunConfig,
) -> LotRecord:
    s1 = _compute_s1(core_skus, category_obsolescence, brand_score)
    s2 = _compute_s2(core_skus, config)
    s3 = _compute_s3(core_skus, category_liquidity, brand_score)
    s4 = _compute_s4(all_skus, category_volume_proxy, config)
    lot.s1 = s1
    lot.s2 = s2
    lot.s3 = s3
    lot.s4 = s4
    lot.base_score = 0.35 * s1 + 0.30 * s2 + 0.20 * s3 + 0.15 * s4
    return lot


def apply_final_score(
    lot: LotRecord,
    *,
    core_skus: list[dict],
    all_skus: list[dict],
    config: RunConfig,
    tail_handling_cost: dict[str, float] | None = None,
) -> LotRecord:
    resolved_core, resolved_tail = _resolve_core_and_tail(core_skus, all_skus)
    total_effective_lot_usd = _total_effective_lot_usd(all_skus)
    lot.unknown_exposure, lot.unknown_exposure_usd = compute_unknown_exposure(
        all_skus, total_effective_lot_usd,
    )
    lot.core_distinct_sku_count = len(_distinct_keys(resolved_core, require_effective_not_none=True))
    lot.penny_line_ratio = _compute_penny_line_ratio(resolved_core, config)
    lot.hhi_index = compute_hhi(all_skus, total_effective_lot_usd)
    tail_cost_map = tail_handling_cost if tail_handling_cost is not None else _load_tail_handling_map(config)
    lot.tail_liability_usd, lot.tail_distinct_sku_count = _compute_tail_liability_usd(
        resolved_tail,
        config,
        tail_cost_map,
    )
    lot.m_hustle = compute_m_hustle(lot.penny_line_ratio, lot.core_distinct_sku_count, config)
    lot.m_concentration = compute_m_concentration(lot.hhi_index, config)
    lot.m_tail = compute_m_tail(lot.tail_liability_usd, total_effective_lot_usd, config)
    lot.m_liquidity_floor, lot.m_obsolescence_floor = compute_kill_switches(lot.s1, lot.s3, config)
    multiplier = _combined_multiplier(
        lot.m_hustle,
        lot.m_concentration,
        lot.m_tail,
        lot.m_liquidity_floor,
        lot.m_obsolescence_floor,
    )
    lot.final_score = round(lot.base_score * multiplier, config.SCORE_PRECISION)
    lot.score_10 = round(10 * (lot.final_score ** config.SCORE_GAMMA), 2)
    return lot


def rank_lots(lots: list[LotRecord]) -> list[LotRecord]:
    ranked = sorted(lots, key=lambda lot: lot.final_score, reverse=True)
    for idx, lot in enumerate(ranked, start=1):
        lot.rank = idx
    return ranked

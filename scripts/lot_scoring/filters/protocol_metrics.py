from __future__ import annotations

from typing import Any

from scripts.lot_scoring.filters.protocol_config import ProtocolConfig
from scripts.lot_scoring.pipeline.helpers import normalize_category_key, to_float, to_str


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return parsed


def _is_truthy_no(value: object) -> bool:
    text = to_str(value).strip().lower()
    return text in {"0", "false", "no", "n", "нет"}


def _normalize_sku_key(sku: dict[str, Any], idx: int) -> str:
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
        return f"__ROW_{idx}"
    return f"__ROW_{row_index}"


def _extract_first_number(value: object) -> float | None:
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if parsed == parsed else None
    text = to_str(value).strip()
    if not text:
        return None
    cleaned = (
        text.replace("\u00a0", "")
        .replace(" ", "")
        .replace(",", ".")
        .replace("₽", "")
        .replace("rub", "")
        .replace("RUB", "")
    )
    return _safe_float(cleaned)


def line_value_rub(sku: dict[str, Any], usd_rate: float, config: ProtocolConfig) -> float | None:
    """Canonical line value in RUB with CalculatedLotCost priority."""
    for key in config.line_value_rub_keys:
        if key not in sku:
            continue
        parsed = _extract_first_number(sku.get(key))
        if parsed is not None:
            return parsed
    effective_line_usd = _safe_float(sku.get("effective_line_usd"))
    if effective_line_usd is None:
        return None
    return effective_line_usd * usd_rate


def _line_unit_price_rub(sku: dict[str, Any], line_value: float | None, usd_rate: float, config: ProtocolConfig) -> float | None:
    for key in config.unit_price_rub_keys:
        if key not in sku:
            continue
        parsed = _extract_first_number(sku.get(key))
        if parsed is not None:
            return parsed
    base_unit_usd = _safe_float(sku.get("base_unit_usd"))
    if base_unit_usd is not None:
        return base_unit_usd * usd_rate
    qty = max(0.0, to_float(sku.get("raw_qty"), 0.0))
    if line_value is not None and qty > 0.0:
        return line_value / qty
    return None


def _extract_category(sku: dict[str, Any], config: ProtocolConfig) -> str:
    for key in config.category_keys:
        if key in sku:
            normalized = normalize_category_key(sku.get(key))
            return normalized or config.unknown_label
    return config.unknown_label


def _extract_brand(sku: dict[str, Any], config: ProtocolConfig) -> str:
    for key in config.brand_keys:
        if key in sku:
            brand = to_str(sku.get(key), config.unknown_label).strip().lower()
            return brand or config.unknown_label
    return config.unknown_label


def _extract_state_text(sku: dict[str, Any], config: ProtocolConfig) -> str:
    for key in config.state_keys:
        if key in sku:
            text = to_str(sku.get(key)).strip().lower()
            if text:
                return text
    return ""


def _has_used_signal(sku: dict[str, Any], state_text: str) -> bool:
    if state_text:
        return True
    return sku.get("condition_raw") is not None


def _detect_used(sku: dict[str, Any], state_text: str, config: ProtocolConfig) -> bool:
    lowered = state_text.lower()
    if lowered:
        if any(marker in lowered for marker in config.used_markers):
            return True
        if any(marker in lowered for marker in config.new_markers):
            return False
    condition_raw = _safe_float(sku.get("condition_raw"))
    if condition_raw is None:
        return False
    return condition_raw < 1.0 - 1e-9


def _is_price_missing(sku: dict[str, Any], line_value_raw: float | None, config: ProtocolConfig) -> bool:
    for key in config.price_found_keys:
        if key in sku and _is_truthy_no(sku.get(key)):
            return True
    base_unit = _safe_float(sku.get("base_unit_usd"))
    raw_qty = max(0.0, to_float(sku.get("raw_qty"), 0.0))
    if raw_qty <= 0.0:
        return False
    if base_unit is not None and base_unit <= 0.0:
        return True
    if line_value_raw is not None and line_value_raw <= 0.0:
        return True
    return False


def prepare_protocol_lines(all_skus: list[dict[str, Any]], usd_rate: float, config: ProtocolConfig) -> list[dict[str, Any]]:
    indexed = list(enumerate(all_skus))
    indexed.sort(key=lambda pair: (_normalize_sku_key(pair[1], pair[0]), pair[0]))
    prepared: list[dict[str, Any]] = []
    for idx, sku in indexed:
        sku_key = _normalize_sku_key(sku, idx)
        line_value_raw = line_value_rub(sku, usd_rate, config)
        line_value_pos = max(0.0, line_value_raw or 0.0)
        state_text = _extract_state_text(sku, config)
        is_used = _detect_used(sku, state_text, config)
        prepared.append(
            {
                "line_idx": idx,
                "row_index": sku.get("row_index"),
                "sku_key": sku_key,
                "raw_text": to_str(sku.get("raw_text")),
                "full_row_text": to_str(sku.get("full_row_text")),
                "brand": _extract_brand(sku, config),
                "category": _extract_category(sku, config),
                "qty": max(0.0, to_float(sku.get("raw_qty"), 0.0)),
                "line_value_rub_raw": line_value_raw,
                "line_value_rub": line_value_pos,
                "unit_price_rub": _line_unit_price_rub(sku, line_value_raw, usd_rate, config),
                "is_non_positive": line_value_raw is None or line_value_raw <= 0.0,
                "is_price_missing": _is_price_missing(sku, line_value_raw, config),
                "is_used": is_used,
                "used_signal_available": _has_used_signal(sku, state_text),
                "is_fake": bool(sku.get("is_fake")),
            }
        )
    return prepared


def aggregate_by_sku(lines: list[dict[str, Any]], value_key: str = "line_value_rub") -> list[dict[str, Any]]:
    by_sku: dict[str, dict[str, Any]] = {}
    for line in lines:
        sku_key = to_str(line.get("sku_key"))
        if not sku_key:
            continue
        record = by_sku.setdefault(
            sku_key,
            {
                "sku": sku_key,
                "sku_value_rub": 0.0,
                "sku_adjusted_value_rub": 0.0,
                "qty_total": 0.0,
                "line_count": 0,
                "raw_text": to_str(line.get("raw_text")),
                "category_value": {},
                "brand_value": {},
            },
        )
        value = max(0.0, to_float(line.get(value_key), 0.0))
        adjusted = max(0.0, to_float(line.get("adjusted_value_rub"), value))
        record["sku_value_rub"] += value
        record["sku_adjusted_value_rub"] += adjusted
        record["qty_total"] += max(0.0, to_float(line.get("qty"), 0.0))
        record["line_count"] += 1
        if not record["raw_text"]:
            record["raw_text"] = to_str(line.get("raw_text"))
        category = to_str(line.get("category"), "unknown")
        brand = to_str(line.get("brand"), "unknown")
        category_value = record["category_value"]
        category_value[category] = category_value.get(category, 0.0) + value
        brand_value = record["brand_value"]
        brand_value[brand] = brand_value.get(brand, 0.0) + value
    aggregated: list[dict[str, Any]] = []
    for sku_key in sorted(by_sku):
        record = by_sku[sku_key]
        category = _dominant_key(record["category_value"])
        brand = _dominant_key(record["brand_value"])
        aggregated.append(
            {
                "sku": sku_key,
                "raw_text": record["raw_text"],
                "qty_total": record["qty_total"],
                "sku_value_rub": record["sku_value_rub"],
                "sku_adjusted_value_rub": record["sku_adjusted_value_rub"],
                "line_count": record["line_count"],
                "category": category,
                "brand": brand,
            }
        )
    aggregated.sort(key=lambda sku: (-to_float(sku.get("sku_value_rub"), 0.0), to_str(sku.get("sku"))))
    return aggregated


def _dominant_key(value_map: dict[str, float]) -> str:
    if not value_map:
        return "unknown"
    best_key = "unknown"
    best_value = float("-inf")
    for key in sorted(value_map):
        val = to_float(value_map[key], 0.0)
        if val > best_value:
            best_value = val
            best_key = key
    return best_key


def total_value(lines: list[dict[str, Any]], value_key: str = "line_value_rub") -> float:
    return sum(max(0.0, to_float(line.get(value_key), 0.0)) for line in lines)


def shares(lines: list[dict[str, Any]], config: ProtocolConfig, total: float, value_key: str = "line_value_rub") -> dict[str, float]:
    if total <= 0.0:
        return {"share_a": 0.0, "share_b": 0.0, "share_e": 0.0}
    bucket_a = set(config.bucket_a)
    bucket_b = set(config.bucket_b)
    bucket_e = set(config.bucket_e)
    value_a = 0.0
    value_b = 0.0
    value_e = 0.0
    for line in lines:
        value = max(0.0, to_float(line.get(value_key), 0.0))
        category = normalize_category_key(line.get("category"))
        if category in bucket_a:
            value_a += value
        elif category in bucket_b:
            value_b += value
        elif category in bucket_e:
            value_e += value
        else:
            value_e += value
    return {
        "share_a": value_a / total,
        "share_b": value_b / total,
        "share_e": value_e / total,
    }


def unknown_value_share(lines: list[dict[str, Any]], total: float, value_key: str = "line_value_rub") -> float:
    if total <= 0.0:
        return 0.0
    unknown_value = 0.0
    for line in lines:
        category = normalize_category_key(line.get("category"))
        if category == "unknown":
            unknown_value += max(0.0, to_float(line.get(value_key), 0.0))
    return unknown_value / total


def used_stress_adjust(lines: list[dict[str, Any]], config: ProtocolConfig) -> dict[str, Any]:
    total = total_value(lines, value_key="line_value_rub")
    if total <= 0.0:
        for line in lines:
            line["adjusted_value_rub"] = max(0.0, to_float(line.get("line_value_rub"), 0.0))
        return {
            "used_signal_available": False,
            "share_used": 0.0,
            "used_stress_applied": False,
            "adjusted_total_value_rub": 0.0,
        }

    used_signal_available = any(bool(line.get("used_signal_available")) for line in lines)
    used_value = 0.0
    adjusted_total = 0.0
    for line in lines:
        value = max(0.0, to_float(line.get("line_value_rub"), 0.0))
        if bool(line.get("is_used")):
            used_value += value
    share_used = used_value / total
    used_stress_applied = used_signal_available and share_used > config.f1_used_share_stress_min
    for line in lines:
        value = max(0.0, to_float(line.get("line_value_rub"), 0.0))
        adjusted = value
        if used_stress_applied and bool(line.get("is_used")):
            adjusted = value * config.f1_used_discount
        line["adjusted_value_rub"] = adjusted
        adjusted_total += adjusted
    return {
        "used_signal_available": used_signal_available,
        "share_used": share_used,
        "used_stress_applied": used_stress_applied,
        "adjusted_total_value_rub": adjusted_total,
    }


def largest_share(aggregated: list[dict[str, Any]], total: float, value_key: str = "sku_value_rub") -> float:
    if total <= 0.0 or not aggregated:
        return 0.0
    max_value = max(max(0.0, to_float(sku.get(value_key), 0.0)) for sku in aggregated)
    return max_value / total


def _slice_by_ratio(
    aggregated: list[dict[str, Any]],
    total: float,
    target_ratio: float,
    value_key: str = "sku_value_rub",
) -> tuple[list[dict[str, Any]], float]:
    if total <= 0.0 or target_ratio <= 0.0:
        return [], 0.0
    sorted_rows = sorted(
        aggregated,
        key=lambda sku: (-max(0.0, to_float(sku.get(value_key), 0.0)), to_str(sku.get("sku"))),
    )
    selected: list[dict[str, Any]] = []
    running = 0.0
    threshold = total * target_ratio
    for row in sorted_rows:
        value = max(0.0, to_float(row.get(value_key), 0.0))
        if value <= 0.0:
            continue
        selected.append(row)
        running += value
        if running + 1e-9 >= threshold:
            break
    return selected, running


def core70(aggregated: list[dict[str, Any]], total: float, config: ProtocolConfig) -> tuple[list[dict[str, Any]], float]:
    return _slice_by_ratio(aggregated, total, config.f2_core70_ratio, value_key="sku_value_rub")


def top_value_slice(aggregated: list[dict[str, Any]], total: float, ratio: float) -> tuple[list[dict[str, Any]], float]:
    return _slice_by_ratio(aggregated, total, ratio, value_key="sku_value_rub")


def top_slices(aggregated: list[dict[str, Any]], total: float, config: ProtocolConfig) -> dict[str, list[dict[str, Any]]]:
    payload: dict[str, list[dict[str, Any]]] = {}
    for ratio in config.top_slice_ratios:
        key = f"top{int(ratio * 100)}_value_slice"
        rows, _ = top_value_slice(aggregated, total, ratio)
        payload[key] = rows
    return payload


def ticket_pct(aggregated: list[dict[str, Any]], threshold_rub: float) -> float:
    if not aggregated:
        return 0.0
    total_count = len(aggregated)
    above = 0
    for sku in aggregated:
        if max(0.0, to_float(sku.get("sku_value_rub"), 0.0)) >= threshold_rub:
            above += 1
    return above / float(total_count) if total_count else 0.0


def core_sku_count(core70_slice: list[dict[str, Any]]) -> int:
    seen = {to_str(row.get("sku")) for row in core70_slice if to_str(row.get("sku"))}
    return len(seen)


def brand_count_core(core70_slice: list[dict[str, Any]], config: ProtocolConfig) -> int:
    brands: set[str] = set()
    for row in core70_slice:
        brand = to_str(row.get("brand"), config.unknown_label).strip().lower()
        brands.add(brand or config.unknown_label)
    return len(brands)


def sm_ratio(total_value_rub: float, entry_price_rub: float | None) -> float:
    if entry_price_rub is None or entry_price_rub <= 0.0:
        return 0.0
    if total_value_rub <= 0.0:
        return 0.0
    return total_value_rub / entry_price_rub


def core_coverage_ratio(core70_value_rub: float, entry_price_rub: float | None) -> float:
    if entry_price_rub is None or entry_price_rub <= 0.0:
        return 0.0
    if core70_value_rub <= 0.0:
        return 0.0
    return core70_value_rub / entry_price_rub


def lot_sort_key(lot_id: str) -> tuple[int, str]:
    text = to_str(lot_id)
    return (int(text), text) if text.isdigit() else (10**9, text)


def duplicate_divergence_flags(
    lines: list[dict[str, Any]],
    divergence_ratio: float,
) -> tuple[bool, list[str]]:
    by_sku: dict[str, dict[str, list[float]]] = {}
    for line in lines:
        sku_key = to_str(line.get("sku_key"))
        record = by_sku.setdefault(sku_key, {"unit": [], "line": []})
        unit = _safe_float(line.get("unit_price_rub"))
        line_value = _safe_float(line.get("line_value_rub_raw"))
        if unit is not None and unit > 0.0:
            record["unit"].append(unit)
        if line_value is not None and line_value > 0.0:
            record["line"].append(line_value)
    flagged: list[str] = []
    for sku_key in sorted(by_sku):
        record = by_sku[sku_key]
        if _max_min_ratio(record["unit"]) > divergence_ratio or _max_min_ratio(record["line"]) > divergence_ratio:
            flagged.append(sku_key)
    return bool(flagged), flagged


def _max_min_ratio(values: list[float]) -> float:
    if len(values) < 2:
        return 1.0
    vmax = max(values)
    vmin = min(values)
    if vmin <= 0.0:
        return float("inf")
    return vmax / vmin


def build_review_lines(
    lines: list[dict[str, Any]],
    duplicate_sku_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    duplicate_sku_keys = duplicate_sku_keys or set()
    review_payload: list[dict[str, Any]] = []
    for line in sorted(lines, key=lambda row: (to_str(row.get("sku_key")), int(to_float(row.get("line_idx"), 0.0)))):
        reasons: list[str] = []
        if normalize_category_key(line.get("category")) == "unknown":
            reasons.append("unknown_category")
        brand = to_str(line.get("brand"), "unknown").strip().lower()
        if not brand or brand == "unknown":
            reasons.append("unknown_brand")
        if bool(line.get("is_non_positive")):
            reasons.append("non_positive_value")
        if bool(line.get("is_price_missing")):
            reasons.append("price_missing")
        if max(0.0, to_float(line.get("qty"), 0.0)) >= 1000.0:
            reasons.append("qty_ge_1000")
        if to_str(line.get("sku_key")) in duplicate_sku_keys:
            reasons.append("duplicate_price_divergence")
        if not reasons:
            continue
        review_payload.append(
            {
                "sku": to_str(line.get("sku_key")),
                "raw_text": to_str(line.get("raw_text")),
                "qty": max(0.0, to_float(line.get("qty"), 0.0)),
                "line_value_rub": max(0.0, to_float(line.get("line_value_rub"), 0.0)),
                "reasons": reasons,
            }
        )
    return review_payload

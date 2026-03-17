from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from scripts.lot_scoring.pipeline.helpers import (
    clamp,
    load_json_dict,
    log_scale_01,
    normalize_category_key,
    to_float,
    to_str,
    weighted_average,
)


@dataclass(frozen=True)
class PnLiquidityConfig:
    VOL_FLOOR: float = 500.0
    VOL_CEIL: float = 300000.0
    LOT_CEIL: int = 10
    TICKET_FLOOR: float = 50.0
    TICKET_CEIL: float = 5000.0
    CAT_UNKNOWN_HEAVY_RATIO: float = 0.80

    W_VOL: float = 0.35
    W_BRD: float = 0.30
    W_TKT: float = 0.15
    W_CAT: float = 0.20

    SCORE_PRECISION: int = 6
    OVERRIDE_FILE: str = "data/pn_liquidity.json"

    def __post_init__(self) -> None:
        if not (0 < self.VOL_FLOOR < self.VOL_CEIL):
            raise ValueError("VOL_FLOOR/VOL_CEIL must satisfy 0 < VOL_FLOOR < VOL_CEIL.")
        if self.LOT_CEIL < 1:
            raise ValueError("LOT_CEIL must be >= 1.")
        if not (0 < self.TICKET_FLOOR < self.TICKET_CEIL):
            raise ValueError("TICKET_FLOOR/TICKET_CEIL must satisfy 0 < TICKET_FLOOR < TICKET_CEIL.")
        if not (0 <= self.CAT_UNKNOWN_HEAVY_RATIO <= 1):
            raise ValueError("CAT_UNKNOWN_HEAVY_RATIO must be in [0, 1].")
        if self.SCORE_PRECISION < 0:
            raise ValueError("SCORE_PRECISION must be >= 0.")
        total_w = self.W_VOL + self.W_BRD + self.W_TKT + self.W_CAT
        if abs(total_w - 1.0) > 1e-12:
            raise ValueError("PN liquidity weights must sum to 1.0.")


def _resolve_pn_id(sku: dict[str, Any]) -> str:
    raw = (
        sku.get("sku_code_normalized")
        or sku.get("sku_code")
        or sku.get("sku")
        or sku.get("part_number")
        or sku.get("model")
    )
    return _normalize_pn_key(raw)


def _normalize_pn_key(raw: object) -> str:
    text = to_str(raw).upper()
    text = text.replace(" ", "").replace("\u00a0", "")
    return re.sub(r"[^A-Z0-9]", "", text)


def _line_usd(sku: dict[str, Any]) -> float:
    return max(0.0, to_float(sku.get("effective_line_usd"), 0.0))


def _round(value: float, precision: int) -> float:
    return round(float(value), precision)


def compute_pn_liquidity(
    processed: list[dict[str, Any]],
    category_liquidity: dict[str, Any],
    config: PnLiquidityConfig,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    override_raw: dict[str, Any] = {}
    try:
        override_raw = load_json_dict(config.OVERRIDE_FILE)
    except FileNotFoundError:
        override_raw = {}
    override_scores: dict[str, float] = {}
    for raw_key, raw_value in override_raw.items():
        key = _normalize_pn_key(raw_key)
        if not key:
            continue
        parsed = to_float(raw_value, -1.0)
        if 0.0 <= parsed <= 1.0:
            override_scores[key] = parsed

    aggregated: dict[str, dict[str, Any]] = {}
    for item in sorted(processed, key=lambda row: to_str(getattr(row.get("lot"), "lot_id", ""))):
        lot = item.get("lot")
        lot_id = to_str(getattr(lot, "lot_id", ""))
        all_skus = item.get("all_skus")
        if not isinstance(all_skus, list):
            continue
        for sku in all_skus:
            if not isinstance(sku, dict):
                continue
            pn_id = _resolve_pn_id(sku)
            if not pn_id:
                continue
            line_usd = _line_usd(sku)
            cat_key = normalize_category_key(sku.get("category"))
            cat_liq = to_float(category_liquidity.get(cat_key, category_liquidity.get("_default", 0.30)), 0.30)
            cat_liq = clamp(cat_liq, 0.0, 1.0)
            if pn_id not in aggregated:
                aggregated[pn_id] = {
                    "pn_id": pn_id,
                    "vol_raw_usd": 0.0,
                    "line_count": 0,
                    "lot_ids": set(),
                    "cat_values": [],
                    "cat_weights": [],
                    "unknown_lines": 0,
                }
            entry = aggregated[pn_id]
            entry["vol_raw_usd"] = to_float(entry.get("vol_raw_usd"), 0.0) + line_usd
            entry["line_count"] = int(entry.get("line_count", 0)) + 1
            lot_ids = entry.get("lot_ids")
            if isinstance(lot_ids, set):
                lot_ids.add(lot_id)
            cat_values = entry.get("cat_values")
            if isinstance(cat_values, list):
                cat_values.append(cat_liq)
            cat_weights = entry.get("cat_weights")
            if isinstance(cat_weights, list):
                cat_weights.append(line_usd)
            if cat_key == "unknown":
                entry["unknown_lines"] = int(entry.get("unknown_lines", 0)) + 1

    pn_rows: list[dict[str, Any]] = []
    pn_scores: dict[str, float] = {}
    for pn_id in sorted(aggregated.keys()):
        entry = aggregated[pn_id]
        vol_raw_usd = max(0.0, to_float(entry.get("vol_raw_usd"), 0.0))
        line_count = max(0, int(entry.get("line_count", 0)))
        lot_ids = entry.get("lot_ids")
        lot_count = len(lot_ids) if isinstance(lot_ids, set) else 0
        avg_line_usd = vol_raw_usd / float(line_count) if line_count > 0 else 0.0
        vol_norm = log_scale_01(vol_raw_usd, config.VOL_FLOOR, config.VOL_CEIL)
        breadth_norm = clamp(float(lot_count) / float(config.LOT_CEIL), 0.0, 1.0)
        ticket_norm = log_scale_01(avg_line_usd, config.TICKET_FLOOR, config.TICKET_CEIL)
        cat_values = entry.get("cat_values")
        cat_weights = entry.get("cat_weights")
        if isinstance(cat_values, list) and isinstance(cat_weights, list):
            cat_liq_norm = weighted_average([to_float(v, 0.0) for v in cat_values], [max(0.0, to_float(w, 0.0)) for w in cat_weights])
        else:
            cat_liq_norm = 0.0
        pn_liquidity = clamp(
            (config.W_VOL * vol_norm)
            + (config.W_BRD * breadth_norm)
            + (config.W_TKT * ticket_norm)
            + (config.W_CAT * cat_liq_norm),
            0.0,
            1.0,
        )
        unknown_lines = max(0, int(entry.get("unknown_lines", 0)))
        unknown_ratio = (unknown_lines / float(line_count)) if line_count > 0 else 0.0
        flags: list[str] = []
        if unknown_ratio >= config.CAT_UNKNOWN_HEAVY_RATIO:
            flags.append("CAT_UNKNOWN_HEAVY")
        if pn_id in override_scores:
            pn_liquidity = clamp(override_scores[pn_id], 0.0, 1.0)
            flags.append("PN_LIQUIDITY_OVERRIDE")

        row = {
            "pn_id": pn_id,
            "vol_raw_usd": _round(vol_raw_usd, config.SCORE_PRECISION),
            "vol_norm": _round(vol_norm, config.SCORE_PRECISION),
            "lot_count": lot_count,
            "breadth_norm": _round(breadth_norm, config.SCORE_PRECISION),
            "line_count": line_count,
            "avg_line_usd": _round(avg_line_usd, config.SCORE_PRECISION),
            "ticket_norm": _round(ticket_norm, config.SCORE_PRECISION),
            "cat_liq_norm": _round(cat_liq_norm, config.SCORE_PRECISION),
            "pn_liquidity": _round(pn_liquidity, config.SCORE_PRECISION),
            "flags": flags,
        }
        pn_rows.append(row)
        pn_scores[pn_id] = to_float(row["pn_liquidity"], 0.0)

    pn_rows = sorted(
        pn_rows,
        key=lambda row: (-to_float(row.get("pn_liquidity"), 0.0), to_str(row.get("pn_id"))),
    )
    return pn_rows, pn_scores


def compute_lot_avg_pn_liquidity(
    processed: list[dict[str, Any]],
    pn_scores: dict[str, float],
) -> dict[str, dict[str, Any]]:
    lot_rows: dict[str, dict[str, Any]] = {}
    for item in sorted(processed, key=lambda row: to_str(getattr(row.get("lot"), "lot_id", ""))):
        lot = item.get("lot")
        lot_id = to_str(getattr(lot, "lot_id", ""))
        all_skus = item.get("all_skus")
        core_skus = item.get("core_skus")
        flags: list[str] = []
        all_empty = not isinstance(all_skus, list) or len(all_skus) == 0
        core_empty = not isinstance(core_skus, list) or len(core_skus) == 0
        if all_empty:
            flags.append("EMPTY_ALL_SKUS")
        if core_empty:
            flags.append("EMPTY_CORE_SKUS")
            core_skus = []

        values: list[float] = []
        weights: list[float] = []
        for sku in core_skus:
            if not isinstance(sku, dict):
                continue
            pn_id = _resolve_pn_id(sku)
            if not pn_id:
                continue
            weight = _line_usd(sku)
            values.append(to_float(pn_scores.get(pn_id), 0.0))
            weights.append(weight)

        lot_avg = weighted_average(values, weights)
        lot_rows[lot_id] = {
            "lot_avg_pn_liquidity": round(lot_avg, 6),
            "flags": flags,
        }
    return lot_rows

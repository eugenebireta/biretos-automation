from __future__ import annotations

import json
from functools import lru_cache
from math import log10
from pathlib import Path
from statistics import median


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def to_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        parsed = float(value)
        if parsed != parsed:
            return default
        return parsed
    except (TypeError, ValueError):
        return default


def to_str(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def log_scale_01(value: float, floor: float, ceil: float) -> float:
    if value <= 0:
        return 0.0
    scaled = log10(value / floor) / log10(ceil / floor)
    return clamp(scaled, 0.0, 1.0)


def weighted_average(values: list[float], weights: list[float]) -> float:
    total_w = sum(weights)
    if total_w <= 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / total_w


def median_or_zero(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(median(values))


def normalize_category_key(value: object) -> str:
    text = to_str(value, "unknown").lower()
    return text.replace("-", "_").replace(" ", "_")


@lru_cache(maxsize=8)
def load_json_dict(relative_or_absolute_path: str) -> dict:
    candidate = Path(relative_or_absolute_path)
    if not candidate.is_absolute():
        lot_scoring_root = Path(__file__).resolve().parents[1]
        candidate = lot_scoring_root / candidate
    with candidate.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {candidate}")
    return payload

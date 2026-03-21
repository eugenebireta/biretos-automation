from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.lot_scoring.pipeline.helpers import clamp, to_float, to_str
from scripts.lot_scoring.pipeline.intelligence_loader import BrandProfile


@dataclass(frozen=True)
class CpsResult:
    brand: str
    cps: float
    total_usd: float
    usd_reject: float
    weighted_non_reject_usd: float
    usd_by_vertical: dict[str, float]
    line_count: int


def _eligible_line(sku: dict[str, Any]) -> bool:
    q_has_qty = sku.get("q_has_qty")
    has_qty = q_has_qty is not False
    has_line = sku.get("effective_line_usd") is not None
    return has_qty and has_line


def compute_cps(all_skus: list[dict[str, Any]], profile: BrandProfile) -> CpsResult:
    total_usd = 0.0
    usd_reject = 0.0
    weighted_non_reject_usd = 0.0
    line_count = 0
    usd_by_vertical: dict[str, float] = {}

    fallback_vertical = profile.verticals.get(profile.fallback_vertical)

    for sku in all_skus:
        if not isinstance(sku, dict):
            continue
        if to_str(sku.get("brand_detected")).lower() != profile.brand:
            continue
        if not _eligible_line(sku):
            continue

        vertical_name = to_str(sku.get("brand_vertical"))
        if not vertical_name:
            continue
        vertical = profile.verticals.get(vertical_name, fallback_vertical)
        if vertical is None:
            continue

        usd = max(0.0, to_float(sku.get("effective_line_usd"), 0.0))
        total_usd += usd
        line_count += 1
        usd_by_vertical[vertical_name] = usd_by_vertical.get(vertical_name, 0.0) + usd

        if vertical.reject:
            usd_reject += usd
        else:
            weighted_non_reject_usd += usd * vertical.purity_weight

    denom = max(total_usd, 1.0)
    if total_usd <= 0.0:
        cps_raw = 0.0
    else:
        cps_raw = (weighted_non_reject_usd - usd_reject) / denom
    cps = clamp(cps_raw, -1.0, 1.0)
    ordered_verticals = {key: round(usd_by_vertical[key], 6) for key in sorted(usd_by_vertical.keys())}

    return CpsResult(
        brand=profile.brand,
        cps=round(cps, 6),
        total_usd=round(total_usd, 6),
        usd_reject=round(usd_reject, 6),
        weighted_non_reject_usd=round(weighted_non_reject_usd, 6),
        usd_by_vertical=ordered_verticals,
        line_count=line_count,
    )


def compute_brand_flags(cps_result: CpsResult, profile: BrandProfile) -> list[str]:
    cps_floor = clamp(to_float(profile.tuning_params.get("cps_floor"), 0.35), 0.0, 1.0)
    reject_abs_usd_ceil = max(0.0, to_float(profile.tuning_params.get("reject_abs_usd_ceil"), 50000.0))

    flags: list[str] = []
    if cps_result.total_usd <= 0.0:
        flags.append("BRAND_NO_PRICING")
    if cps_result.cps < cps_floor:
        flags.append("LOW_CAPITAL_PURITY")
    if cps_result.usd_reject > reject_abs_usd_ceil:
        flags.append("HIGH_REJECT_ABSOLUTE")
    return sorted(set(flags))


def compute_brand_intelligence_summary(
    all_skus: list[dict[str, Any]],
    profile: BrandProfile,
    cps_result: CpsResult,
    flags: list[str],
) -> dict[str, Any]:
    total_usd = max(0.0, cps_result.total_usd)
    denom = max(total_usd, 1.0)

    weighted_obs_sum = 0.0
    for sku in all_skus:
        if not isinstance(sku, dict):
            continue
        if to_str(sku.get("brand_detected")).lower() != profile.brand:
            continue
        if not _eligible_line(sku):
            continue
        usd = max(0.0, to_float(sku.get("effective_line_usd"), 0.0))
        obs = clamp(to_float(sku.get("brand_obs"), 0.0), 0.0, 1.0)
        weighted_obs_sum += usd * obs
    brand_obs_weighted = 0.0 if total_usd <= 0.0 else weighted_obs_sum / denom

    verticals_breakdown: dict[str, dict[str, float]] = {}
    for vertical in sorted(cps_result.usd_by_vertical.keys()):
        usd = max(0.0, to_float(cps_result.usd_by_vertical.get(vertical), 0.0))
        verticals_breakdown[vertical] = {
            "usd": round(usd, 6),
            "pct": round(usd / denom if total_usd > 0.0 else 0.0, 6),
        }

    return {
        "brand": profile.brand,
        "cps": round(cps_result.cps, 6),
        "total_usd": round(total_usd, 6),
        "usd_reject": round(cps_result.usd_reject, 6),
        "line_count": int(cps_result.line_count),
        "flags": sorted(set(flags)),
        "brand_obs_weighted": round(brand_obs_weighted, 6),
        "verticals_breakdown": verticals_breakdown,
    }
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from scripts.lot_scoring.pipeline.helpers import clamp, to_float, to_str
from scripts.lot_scoring.pipeline.intelligence_loader import BrandProfile


@dataclass(frozen=True)
class CpsResult:
    brand: str
    cps: float
    total_effective_usd: float
    weighted_purity_usd: float
    reject_usd: float
    usd_by_vertical: dict[str, float]


def _line_eligible_for_total(sku: dict) -> bool:
    q_has_qty = sku.get("q_has_qty")
    has_qty = q_has_qty is not False
    has_line = sku.get("effective_line_usd") is not None
    return has_qty and has_line


def _line_effective_usd(sku: dict) -> float:
    return max(0.0, to_float(sku.get("effective_line_usd"), 0.0))


def compute_cps(all_skus: list[dict], profile: BrandProfile) -> CpsResult:
    usd_by_vertical: dict[str, float] = {}
    total_effective_usd = 0.0
    weighted_purity_usd = 0.0
    reject_usd = 0.0

    for sku in all_skus:
        if to_str(sku.get("brand_detected")).lower() != profile.brand:
            continue
        if not _line_eligible_for_total(sku):
            continue
        line_usd = _line_effective_usd(sku)
        total_effective_usd += line_usd
        vertical_name = to_str(sku.get("brand_vertical"), profile.fallback_vertical)
        if vertical_name not in profile.verticals:
            vertical_name = profile.fallback_vertical
        usd_by_vertical[vertical_name] = usd_by_vertical.get(vertical_name, 0.0) + line_usd

    for vertical_name in sorted(usd_by_vertical.keys()):
        usd = usd_by_vertical[vertical_name]
        vertical = profile.verticals.get(vertical_name, profile.verticals[profile.fallback_vertical])
        if vertical.reject:
            reject_usd += usd
        else:
            weighted_purity_usd += usd * vertical.purity_weight

    denominator = max(total_effective_usd, 1.0)
    cps_raw = (weighted_purity_usd - reject_usd) / denominator
    cps_clamped = clamp(cps_raw, -1.0, 1.0)
    return CpsResult(
        brand=profile.brand,
        cps=round(cps_clamped, 6),
        total_effective_usd=round(total_effective_usd, 6),
        weighted_purity_usd=round(weighted_purity_usd, 6),
        reject_usd=round(reject_usd, 6),
        usd_by_vertical={key: round(usd_by_vertical[key], 6) for key in sorted(usd_by_vertical.keys())},
    )


def compute_brand_flags(cps_result: CpsResult, profile: BrandProfile) -> list[str]:
    flags: list[str] = []
    if cps_result.total_effective_usd <= 0.0:
        flags.append("BRAND_NO_PRICING")
    if cps_result.cps < profile.cps_floor:
        flags.append("LOW_CAPITAL_PURITY")
    if cps_result.reject_usd > profile.reject_abs_usd_ceil:
        flags.append("HIGH_REJECT_ABSOLUTE")
    return flags


def compute_brand_intelligence_summary(cps_result: CpsResult, flags: list[str]) -> dict[str, Any]:
    denominator = max(cps_result.total_effective_usd, 1.0)
    verticals_breakdown: dict[str, dict[str, float]] = {}
    for vertical_name in sorted(cps_result.usd_by_vertical.keys()):
        usd = cps_result.usd_by_vertical[vertical_name]
        verticals_breakdown[vertical_name] = {
            "usd": round(usd, 6),
            "pct": round(clamp(usd / denominator, 0.0, 1.0), 6),
        }

    payload: dict[str, Any] = {
        "brand": cps_result.brand,
        "cps": round(cps_result.cps, 6),
        "usd_reject": round(cps_result.reject_usd, 6),
        "total_effective_usd": round(cps_result.total_effective_usd, 6),
        "weighted_purity_usd": round(cps_result.weighted_purity_usd, 6),
        "flags": list(flags),
        "verticals_breakdown": verticals_breakdown,
    }
    payload["summary_json"] = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    payload["verticals_json"] = json.dumps(verticals_breakdown, ensure_ascii=False, sort_keys=True)
    return payload

"""


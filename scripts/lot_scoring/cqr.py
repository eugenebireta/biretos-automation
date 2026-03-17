from __future__ import annotations

from dataclasses import dataclass

from scripts.lot_scoring.pipeline.helpers import clamp, to_float, to_str

_CQR_WEIGHTS: dict[str, float] = {
    "REGULATED_PROJECT": 1.0,
    "COMPATIBILITY_LOCK": 0.85,
    "COMMODITY": 0.50,
    "CONSUMABLE": 0.30,
    "OBSOLESCENCE_RISK": 0.10,
    "UNKNOWN": 0.50,
}

_TOXIC_BRAND_PATTERNS: tuple[str, ...] = (
    "counterfeit",
    "fake",
    "no name",
    "noname",
    "generic",
)


@dataclass(frozen=True)
class CQRResult:
    cqr_score: float
    cqr_confidence: str
    representativeness_ratio: float
    toxic_anchor_flag: bool
    demand_type_distribution: dict[str, float]
    flags: list[str]


def classify_demand_type(category: str, brand: str) -> str:
    category_key = to_str(category).strip().lower()
    brand_key = to_str(brand).strip().lower()

    if any(pattern in brand_key for pattern in _TOXIC_BRAND_PATTERNS):
        return "OBSOLESCENCE_RISK"

    if category_key in {"gas_safety", "fire_safety"}:
        return "REGULATED_PROJECT"
    if category_key in {"industrial_sensors", "valves_actuators"}:
        return "COMPATIBILITY_LOCK"
    if category_key in {"hvac_components", "construction_supplies"}:
        return "COMMODITY"
    if category_key in {"packaging_materials"}:
        return "CONSUMABLE"
    if category_key in {"it_hardware", "toxic_fake"}:
        return "OBSOLESCENCE_RISK"
    return "UNKNOWN"


def _confidence_from_representativeness(representativeness_ratio: float) -> str:
    if representativeness_ratio >= 0.50:
        return "HIGH"
    if representativeness_ratio >= 0.30:
        return "MEDIUM"
    if representativeness_ratio >= 0.15:
        return "LOW"
    return "UNRELIABLE"


def compute_cqr(
    top_core_skus: list[dict],
    total_core_value_usd: float,
    lot_flags: list[str],
    toxic_anchor_threshold: float = 0.20,
) -> CQRResult:
    del lot_flags  # Reserved for future deterministic flag conditioning.

    values: list[tuple[float, str]] = []
    for sku in top_core_skus:
        line_value = max(0.0, to_float(sku.get("effective_line_usd"), 0.0))
        if line_value <= 0.0:
            continue
        demand_type = classify_demand_type(to_str(sku.get("category")), to_str(sku.get("brand")))
        values.append((line_value, demand_type))

    top_core_value = sum(value for value, _ in values)
    positive_total_core_value = max(0.0, to_float(total_core_value_usd, 0.0))
    representativeness_ratio = (
        top_core_value / positive_total_core_value if positive_total_core_value > 0.0 else 0.0
    )

    value_by_type = {key: 0.0 for key in _CQR_WEIGHTS}
    for value, demand_type in values:
        value_by_type[demand_type] += value

    if top_core_value > 0.0:
        demand_type_distribution = {
            key: value_by_type[key] / top_core_value for key in _CQR_WEIGHTS
        }
        cqr_score = sum(
            _CQR_WEIGHTS[key] * demand_type_distribution[key] for key in _CQR_WEIGHTS
        )
    else:
        demand_type_distribution = {key: 0.0 for key in _CQR_WEIGHTS}
        cqr_score = _CQR_WEIGHTS["UNKNOWN"]

    toxic_anchor_flag = False
    if top_core_value > 0.0:
        max_value, max_type = max(values, key=lambda pair: pair[0], default=(0.0, "UNKNOWN"))
        max_share = max_value / top_core_value
        if max_share > toxic_anchor_threshold and max_type in {"OBSOLESCENCE_RISK", "COMMODITY"}:
            toxic_anchor_flag = True

    cqr_confidence = _confidence_from_representativeness(representativeness_ratio)
    flags: list[str] = []
    if cqr_confidence == "UNRELIABLE":
        flags.append("UNRELIABLE_CORE")
    if toxic_anchor_flag:
        flags.append("TOXIC_ANCHOR")

    return CQRResult(
        cqr_score=clamp(cqr_score, 0.0, 1.0),
        cqr_confidence=cqr_confidence,
        representativeness_ratio=clamp(representativeness_ratio, 0.0, 1.0),
        toxic_anchor_flag=toxic_anchor_flag,
        demand_type_distribution=demand_type_distribution,
        flags=flags,
    )

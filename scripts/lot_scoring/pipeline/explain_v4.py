from __future__ import annotations

import json
from math import log
from typing import Any

from scripts.lot_scoring.governance_config import GovernanceConfig
from scripts.lot_scoring.pipeline.helpers import clamp, to_float, to_str
from scripts.lot_scoring.run_config import RunConfig
from scripts.lot_scoring.simulation.scoring_kernel import V4Config, compute_fas_from_scalars

ROUND_DIGITS = 6
EPSILON = 1e-9


def _r6(value: float) -> float:
    return round(float(value), ROUND_DIGITS)


def compute_obs_weighted(core_skus: list[dict], category_obsolescence: dict) -> float:
    default_obs = to_float(category_obsolescence.get("_default", 0.40), 0.40)
    values: list[float] = []
    weights: list[float] = []
    for sku in core_skus:
        category = to_str(sku.get("category"), "unknown")
        obs = to_float(category_obsolescence.get(category, default_obs), default_obs)
        values.append(clamp(obs, 0.0, 1.0))
        weights.append(max(0.0, to_float(sku.get("effective_line_usd"), 0.0)))
    total_weight = sum(weights)
    if total_weight <= 0.0:
        return _r6(clamp(default_obs, 0.0, 1.0))
    weighted = sum(value * weight for value, weight in zip(values, weights)) / total_weight
    return _r6(clamp(weighted, 0.0, 1.0))


def compute_v4_scalars(
    *,
    lot: Any,
    metadata: dict[str, float | int],
    core_skus: list[dict],
    category_obsolescence: dict,
    run_config: RunConfig,
    v4_config: V4Config,
) -> dict[str, Any]:
    core_count = max(0, int(metadata.get("core_count", 0)))
    tail_count = max(0, int(metadata.get("tail_count", 0)))
    total_count = max(1, core_count + tail_count)
    tail_ratio = clamp(tail_count / total_count, 0.0, 1.0)
    obs_weighted = compute_obs_weighted(core_skus, category_obsolescence)
    return compute_fas_from_scalars(
        s1=to_float(getattr(lot, "s1", 0.0), 0.0),
        s2=to_float(getattr(lot, "s2", 0.0), 0.0),
        s3=to_float(getattr(lot, "s3", 0.0), 0.0),
        s4=to_float(getattr(lot, "s4", 0.0), 0.0),
        hhi_index=to_float(getattr(lot, "hhi_index", 1.0), 1.0),
        obs_weighted=obs_weighted,
        unknown_exposure=to_float(getattr(lot, "unknown_exposure", 0.0), 0.0),
        penny_ratio=to_float(getattr(lot, "penny_line_ratio", 1.0), 1.0),
        core_distinct_sku_count=int(max(1, int(getattr(lot, "core_distinct_sku_count", 1)))),
        tail_ratio=tail_ratio,
        run_config=run_config,
        v4_config=v4_config,
    )


def compute_loss_attribution(v4_scalars: dict[str, Any]) -> dict[str, Any]:
    ordered_multipliers = (
        ("M_Lifecycle", to_float(v4_scalars.get("m_lifecycle"), 1.0)),
        ("M_Unknown", to_float(v4_scalars.get("m_unknown"), 1.0)),
        ("m_concentration", to_float(v4_scalars.get("m_concentration"), 1.0)),
        ("m_hustle", to_float(v4_scalars.get("m_hustle"), 1.0)),
        ("m_tail", to_float(v4_scalars.get("m_tail"), 1.0)),
        ("KS_liquidity", to_float(v4_scalars.get("ks_liquidity"), 1.0)),
        ("KS_obsolescence", to_float(v4_scalars.get("ks_obsolescence"), 1.0)),
    )
    components: list[dict[str, float | str]] = []
    total_loss = 0.0
    for name, multiplier in ordered_multipliers:
        safe_multiplier = max(EPSILON, min(1.0, multiplier))
        loss_value = -log(safe_multiplier)
        total_loss += loss_value
        components.append(
            {
                "name": name,
                "multiplier": _r6(safe_multiplier),
                "loss": _r6(loss_value),
            }
        )

    denom = max(total_loss, EPSILON)
    for component in components:
        component["pct"] = _r6(to_float(component["loss"], 0.0) / denom)

    payload = {
        "total_loss": _r6(total_loss),
        "components": components,
    }
    payload["loss_attribution_json"] = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return payload


def compute_top_loss_reasons(loss_attribution: dict[str, Any], top_n: int = 3) -> str:
    components = list(loss_attribution.get("components", []))
    sorted_components = sorted(
        components,
        key=lambda item: (
            -to_float(item.get("loss"), 0.0),
            to_str(item.get("name")),
        ),
    )
    reasons: list[str] = []
    for component in sorted_components[: max(1, top_n)]:
        name = to_str(component.get("name"), "unknown")
        pct_value = to_float(component.get("pct"), 0.0) * 100.0
        reasons.append(f"{name}:{pct_value:.0f}%")
    return ", ".join(reasons)


def compute_investor_summary(v4_scalars: dict[str, Any], top_loss_reasons: str, zone: str | None = None) -> str:
    aq = to_float(v4_scalars.get("aq"), 0.0)
    fas = to_float(v4_scalars.get("fas"), 0.0)
    zone_label = to_str(zone or "N/A")
    reasons = to_str(top_loss_reasons, "n/a")
    return f"AQ={aq:.1f}, FAS={fas:.1f}, Zone={zone_label}. Top drags: {reasons}"


def compute_data_trust(all_skus: list[dict]) -> tuple[str, float]:
    total = len(all_skus)
    if total <= 0:
        return "LOW", 0.0
    recognized = 0
    for sku in all_skus:
        category = to_str(sku.get("category"), "unknown").lower()
        if category != "unknown":
            recognized += 1
    ratio = recognized / float(total)
    rounded = _r6(clamp(ratio, 0.0, 1.0))
    if rounded >= 0.80:
        return "HIGH", rounded
    if rounded >= 0.50:
        return "MED", rounded
    return "LOW", rounded


def compute_tier(score_10: float) -> str:
    score = to_float(score_10, 0.0)
    if score >= 7.0:
        return "STRONG"
    if score >= 5.0:
        return "CANDIDATE"
    if score >= 3.0:
        return "RISKY"
    return "WEAK"


def compute_zone(
    fas_v4: float,
    gov_config: GovernanceConfig,
    *,
    hhi_index: float = 0.0,
    unknown_exposure: float = 0.0,
) -> str:
    fas = to_float(fas_v4, 0.0)
    if fas >= gov_config.ZONE_PASS_THRESH:
        hhi = to_float(hhi_index, 0.0)
        unknown = to_float(unknown_exposure, 0.0)
        if hhi >= gov_config.HHI_ALERT_THRESH or unknown >= gov_config.UNKNOWN_ALERT_THRESH:
            return "REVIEW"
        return "PASS"
    if fas >= gov_config.ZONE_REVIEW_THRESH:
        return "REVIEW"
    return "WEAK"

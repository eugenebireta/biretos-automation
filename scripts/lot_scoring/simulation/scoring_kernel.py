from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.lot_scoring.pipeline.helpers import clamp
from scripts.lot_scoring.pipeline.score import (
    compute_kill_switches,
    compute_m_concentration,
    compute_m_hustle,
)
from scripts.lot_scoring.run_config import RunConfig

ROUND_DIGITS = 6


@dataclass(frozen=True)
class V4Config:
    LIFECYCLE_SAFE: float = 0.50
    LIFECYCLE_K: float = 1.40
    LIFECYCLE_FLOOR: float = 0.30
    UNKNOWN_SAFE: float = 0.10
    UNKNOWN_K: float = 2.00
    UNKNOWN_FLOOR: float = 0.30
    AQ_W1: float = 0.35
    AQ_W2: float = 0.30
    AQ_W3: float = 0.20
    AQ_W4: float = 0.15


def _r6(value: float) -> float:
    return round(float(value), ROUND_DIGITS)


def _c01(value: float) -> float:
    return clamp(float(value), 0.0, 1.0)


def compute_aq(
    *,
    s1: float,
    s2: float,
    s3: float,
    s4: float,
    v4_config: V4Config,
) -> float:
    s1_clamped = _c01(s1)
    s2_clamped = _c01(s2)
    s3_clamped = _c01(s3)
    s4_clamped = _c01(s4)
    aq_01 = (
        v4_config.AQ_W1 * s1_clamped
        + v4_config.AQ_W2 * s2_clamped
        + v4_config.AQ_W3 * s3_clamped
        + v4_config.AQ_W4 * s4_clamped
    )
    return _r6(_c01(aq_01) * 100.0)


def compute_m_lifecycle(*, obs_weighted: float, v4_config: V4Config) -> float:
    obs_value = _c01(obs_weighted)
    penalty = v4_config.LIFECYCLE_K * max(0.0, v4_config.LIFECYCLE_SAFE - obs_value)
    return _r6(clamp(1.0 - penalty, v4_config.LIFECYCLE_FLOOR, 1.0))


def compute_m_unknown(*, unknown_exposure: float, v4_config: V4Config) -> float:
    unknown_value = _c01(unknown_exposure)
    penalty = v4_config.UNKNOWN_K * max(0.0, unknown_value - v4_config.UNKNOWN_SAFE)
    return _r6(clamp(1.0 - penalty, v4_config.UNKNOWN_FLOOR, 1.0))


def compute_m_tail_from_ratio(*, tail_ratio: float, run_config: RunConfig) -> float:
    ratio = _c01(tail_ratio)
    return _r6(clamp(max(run_config.TAIL_FLOOR, 1.0 - ratio), run_config.TAIL_FLOOR, 1.0))


def compute_fas_from_scalars(
    *,
    s1: float,
    s2: float,
    s3: float,
    s4: float,
    hhi_index: float,
    obs_weighted: float,
    unknown_exposure: float,
    penny_ratio: float,
    core_distinct_sku_count: int,
    tail_ratio: float,
    run_config: RunConfig,
    v4_config: V4Config,
) -> dict[str, Any]:
    s1_value = _c01(s1)
    s2_value = _c01(s2)
    s3_value = _c01(s3)
    s4_value = _c01(s4)
    hhi_value = _c01(hhi_index)
    obs_value = _c01(obs_weighted)
    unknown_value = _c01(unknown_exposure)
    penny_value = _c01(penny_ratio)
    tail_value = _c01(tail_ratio)
    frag_count = max(1, int(core_distinct_sku_count))

    aq = compute_aq(
        s1=s1_value,
        s2=s2_value,
        s3=s3_value,
        s4=s4_value,
        v4_config=v4_config,
    )
    m_concentration = _r6(compute_m_concentration(hhi_value, run_config))
    m_lifecycle = compute_m_lifecycle(obs_weighted=obs_value, v4_config=v4_config)
    m_unknown = compute_m_unknown(unknown_exposure=unknown_value, v4_config=v4_config)
    m_hustle = _r6(compute_m_hustle(penny_value, frag_count, run_config))
    m_tail = compute_m_tail_from_ratio(tail_ratio=tail_value, run_config=run_config)
    ks_liquidity, ks_obsolescence = compute_kill_switches(s1_value, s3_value, run_config)
    ks_liquidity = _r6(ks_liquidity)
    ks_obsolescence = _r6(ks_obsolescence)

    combined_risk = _r6(
        m_concentration
        * m_lifecycle
        * m_unknown
        * m_hustle
        * m_tail
        * ks_liquidity
        * ks_obsolescence
    )
    fas = _r6(clamp(aq * combined_risk, 0.0, 100.0))

    return {
        "s1": _r6(s1_value),
        "s2": _r6(s2_value),
        "s3": _r6(s3_value),
        "s4": _r6(s4_value),
        "hhi_index": _r6(hhi_value),
        "obs_weighted": _r6(obs_value),
        "unknown_exposure": _r6(unknown_value),
        "penny_ratio": _r6(penny_value),
        "core_distinct_sku_count": frag_count,
        "tail_ratio": _r6(tail_value),
        "aq": aq,
        "m_concentration": m_concentration,
        "m_lifecycle": m_lifecycle,
        "m_unknown": m_unknown,
        "m_hustle": m_hustle,
        "m_tail": m_tail,
        "ks_liquidity": ks_liquidity,
        "ks_obsolescence": ks_obsolescence,
        "combined_risk": combined_risk,
        "fas": fas,
    }

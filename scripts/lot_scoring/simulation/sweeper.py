from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from scripts.lot_scoring.run_config import RunConfig
from scripts.lot_scoring.simulation.scoring_kernel import V4Config, compute_fas_from_scalars

PROFILES: dict[str, dict[str, float | int]] = {
    "good": {
        "s1": 0.85,
        "s2": 0.75,
        "s3": 0.80,
        "s4": 0.70,
        "hhi_index": 0.10,
        "obs_weighted": 0.80,
        "unknown_exposure": 0.05,
        "penny_ratio": 0.10,
        "core_distinct_sku_count": 25,
        "tail_ratio": 0.05,
    },
    "medium": {
        "s1": 0.55,
        "s2": 0.45,
        "s3": 0.50,
        "s4": 0.40,
        "hhi_index": 0.25,
        "obs_weighted": 0.50,
        "unknown_exposure": 0.20,
        "penny_ratio": 0.35,
        "core_distinct_sku_count": 35,
        "tail_ratio": 0.15,
    },
    "bad": {
        "s1": 0.25,
        "s2": 0.20,
        "s3": 0.15,
        "s4": 0.15,
        "hhi_index": 0.55,
        "obs_weighted": 0.20,
        "unknown_exposure": 0.45,
        "penny_ratio": 0.70,
        "core_distinct_sku_count": 55,
        "tail_ratio": 0.40,
    },
}

SWEEP_FACTORS: tuple[str, ...] = (
    "s1",
    "s2",
    "s3",
    "s4",
    "hhi_index",
    "obs_weighted",
    "unknown_exposure",
    "penny_ratio",
    "core_distinct_sku_count",
    "tail_ratio",
)


def _linspace_100(start: float, end: float) -> list[float]:
    if start == end:
        return [round(start, 6)] * 100
    step = (end - start) / 99.0
    return [round(start + step * idx, 6) for idx in range(100)]


def _factor_values(name: str) -> list[float | int]:
    if name == "core_distinct_sku_count":
        return list(range(1, 101))
    return _linspace_100(0.0, 1.0)


def _score_profile(
    *,
    profile: dict[str, float | int],
    factor_name: str,
    factor_value: float | int,
    run_config: RunConfig,
    v4_config: V4Config,
) -> float:
    values = dict(profile)
    values[factor_name] = factor_value
    scored = compute_fas_from_scalars(
        s1=float(values["s1"]),
        s2=float(values["s2"]),
        s3=float(values["s3"]),
        s4=float(values["s4"]),
        hhi_index=float(values["hhi_index"]),
        obs_weighted=float(values["obs_weighted"]),
        unknown_exposure=float(values["unknown_exposure"]),
        penny_ratio=float(values["penny_ratio"]),
        core_distinct_sku_count=int(values["core_distinct_sku_count"]),
        tail_ratio=float(values["tail_ratio"]),
        run_config=run_config,
        v4_config=v4_config,
    )
    return float(scored["fas"])


def run_sweep(
    *,
    out_dir: Path,
    seed: int,
    run_config: RunConfig,
    v4_config: V4Config,
) -> dict[str, list[dict[str, Any]]]:
    _ = seed
    curves_dir = out_dir / "curves"
    curves_dir.mkdir(parents=True, exist_ok=True)

    for factor_name in SWEEP_FACTORS:
        path = curves_dir / f"sweep_{factor_name}.csv"
        rows: list[dict[str, str]] = []
        for factor_value in _factor_values(factor_name):
            rows.append(
                {
                    "factor_value": str(factor_value),
                    "fas_good": f"{_score_profile(profile=PROFILES['good'], factor_name=factor_name, factor_value=factor_value, run_config=run_config, v4_config=v4_config):.6f}",
                    "fas_medium": f"{_score_profile(profile=PROFILES['medium'], factor_name=factor_name, factor_value=factor_value, run_config=run_config, v4_config=v4_config):.6f}",
                    "fas_bad": f"{_score_profile(profile=PROFILES['bad'], factor_name=factor_name, factor_value=factor_value, run_config=run_config, v4_config=v4_config):.6f}",
                }
            )

        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["factor_value", "fas_good", "fas_medium", "fas_bad"],
            )
            writer.writeheader()
            writer.writerows(rows)

    concentration_floor_threshold = round(
        run_config.HHI_SAFE + ((1.0 - run_config.CONC_FLOOR) / max(run_config.CONC_K, 1e-9)),
        6,
    )
    lifecycle_floor_threshold = round(
        v4_config.LIFECYCLE_SAFE - ((1.0 - v4_config.LIFECYCLE_FLOOR) / max(v4_config.LIFECYCLE_K, 1e-9)),
        6,
    )
    unknown_floor_threshold = round(
        v4_config.UNKNOWN_SAFE + ((1.0 - v4_config.UNKNOWN_FLOOR) / max(v4_config.UNKNOWN_K, 1e-9)),
        6,
    )
    tail_floor_threshold = round(1.0 - run_config.TAIL_FLOOR, 6)

    return {
        "hhi_index": [
            {"threshold": round(run_config.HHI_SAFE, 6), "effect": "m_concentration_penalty_start"},
            {"threshold": concentration_floor_threshold, "effect": "m_concentration_floor"},
        ],
        "obs_weighted": [
            {"threshold": round(v4_config.LIFECYCLE_SAFE, 6), "effect": "m_lifecycle_penalty_start"},
            {"threshold": lifecycle_floor_threshold, "effect": "m_lifecycle_floor"},
        ],
        "unknown_exposure": [
            {"threshold": round(v4_config.UNKNOWN_SAFE, 6), "effect": "m_unknown_penalty_start"},
            {"threshold": unknown_floor_threshold, "effect": "m_unknown_floor"},
        ],
        "core_distinct_sku_count": [
            {"threshold": int(run_config.FRAG_LOW), "effect": "m_hustle_frag_penalty_start"},
            {"threshold": int(run_config.FRAG_HIGH), "effect": "m_hustle_frag_penalty_saturated"},
        ],
        "tail_ratio": [
            {"threshold": tail_floor_threshold, "effect": "m_tail_floor"},
        ],
        "s3": [
            {"threshold": round(run_config.LIQUIDITY_KILL_THRESH, 6), "effect": "ks_liquidity_switch"},
        ],
        "s1": [
            {"threshold": round(run_config.OBSOLESCENCE_KILL_THRESH, 6), "effect": "ks_obsolescence_switch"},
        ],
    }

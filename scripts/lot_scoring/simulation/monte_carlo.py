from __future__ import annotations

import csv
import random
from math import ceil, floor, prod, sqrt
from pathlib import Path
from typing import Any

from scripts.lot_scoring.pipeline.helpers import clamp
from scripts.lot_scoring.run_config import RunConfig
from scripts.lot_scoring.simulation.scoring_kernel import V4Config, compute_fas_from_scalars

INPUT_FIELDS: tuple[str, ...] = (
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

CSV_FIELDS: tuple[str, ...] = (
    "sample_index",
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
    "aq",
    "m_concentration",
    "m_lifecycle",
    "m_unknown",
    "m_hustle",
    "m_tail",
    "ks_liquidity",
    "ks_obsolescence",
    "combined_risk",
    "fas",
)


def _r6(value: float) -> float:
    return round(float(value), 6)


def _c01(value: float) -> float:
    return clamp(float(value), 0.0, 1.0)


def generate_samples(samples: int, rng: random.Random) -> list[dict[str, float | int]]:
    generated: list[dict[str, float | int]] = []
    for _ in range(max(0, int(samples))):
        frag_raw = int(round(rng.lognormvariate(3.0, 0.5)))
        frag_count = max(1, min(100, frag_raw))

        generated.append(
            {
                "s1": _r6(_c01(rng.betavariate(5.0, 2.0))),
                "s2": _r6(_c01(rng.betavariate(2.0, 3.0))),
                "s3": _r6(_c01(rng.betavariate(4.0, 2.0))),
                "s4": _r6(_c01(rng.betavariate(2.0, 2.0))),
                "hhi_index": _r6(_c01(rng.betavariate(2.0, 5.0))),
                "obs_weighted": _r6(_c01(rng.betavariate(5.0, 2.0))),
                "unknown_exposure": _r6(_c01(rng.betavariate(1.5, 6.0))),
                "penny_ratio": _r6(_c01(rng.betavariate(2.0, 5.0))),
                "core_distinct_sku_count": frag_count,
                "tail_ratio": _r6(_c01(rng.betavariate(2.0, 8.0))),
            }
        )
    return generated


def _rank_values(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks: list[float] = [0.0] * len(values)
    idx = 0
    while idx < len(indexed):
        end = idx + 1
        while end < len(indexed) and indexed[end][1] == indexed[idx][1]:
            end += 1
        avg_rank = ((idx + 1) + end) / 2.0
        for pos in range(idx, end):
            original_index = indexed[pos][0]
            ranks[original_index] = avg_rank
        idx = end
    return ranks


def _pearson(x: list[float], y: list[float]) -> float:
    if len(x) != len(y) or not x:
        return 0.0
    n = float(len(x))
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = 0.0
    var_x = 0.0
    var_y = 0.0
    for left, right in zip(x, y):
        dx = left - mean_x
        dy = right - mean_y
        cov += dx * dy
        var_x += dx * dx
        var_y += dy * dy
    if var_x <= 0.0 or var_y <= 0.0:
        return 0.0
    return cov / sqrt(var_x * var_y)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = max(0.0, min(1.0, q)) * float(len(sorted_values) - 1)
    low_idx = floor(rank)
    high_idx = ceil(rank)
    low_value = sorted_values[low_idx]
    high_value = sorted_values[high_idx]
    if low_idx == high_idx:
        return float(low_value)
    weight = rank - float(low_idx)
    return float(low_value + ((high_value - low_value) * weight))


def _fraction(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return _r6((float(count) / float(total)) * 100.0)


def analyze_spearman(rows: list[dict[str, Any]], fas_values: list[float]) -> dict[str, float]:
    result: dict[str, float] = {}
    if not rows or len(rows) != len(fas_values):
        return {field: 0.0 for field in INPUT_FIELDS}

    fas_ranks = _rank_values(fas_values)
    for field in INPUT_FIELDS:
        values = [float(row[field]) for row in rows]
        value_ranks = _rank_values(values)
        result[field] = _r6(_pearson(value_ranks, fas_ranks))
    return result


def analyze_permutation_importance(
    *,
    rows: list[dict[str, Any]],
    fas_values: list[float],
    seed: int,
    run_config: RunConfig,
    v4_config: V4Config,
) -> dict[str, float]:
    result: dict[str, float] = {}
    if not rows or len(rows) != len(fas_values):
        return {field: 0.0 for field in INPUT_FIELDS}

    size = len(rows)
    for idx, field in enumerate(INPUT_FIELDS):
        shuffled = [rows[row_idx][field] for row_idx in range(size)]
        rng = random.Random(seed + idx + 1)
        rng.shuffle(shuffled)

        total_abs_delta = 0.0
        for row_idx, row in enumerate(rows):
            probe = dict(row)
            probe[field] = shuffled[row_idx]
            permuted = compute_fas_from_scalars(
                s1=float(probe["s1"]),
                s2=float(probe["s2"]),
                s3=float(probe["s3"]),
                s4=float(probe["s4"]),
                hhi_index=float(probe["hhi_index"]),
                obs_weighted=float(probe["obs_weighted"]),
                unknown_exposure=float(probe["unknown_exposure"]),
                penny_ratio=float(probe["penny_ratio"]),
                core_distinct_sku_count=int(probe["core_distinct_sku_count"]),
                tail_ratio=float(probe["tail_ratio"]),
                run_config=run_config,
                v4_config=v4_config,
            )
            total_abs_delta += abs(float(permuted["fas"]) - fas_values[row_idx])

        result[field] = _r6(total_abs_delta / float(size))
    return result


def _compute_stacking_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    aq_cut_rows = [row for row in rows if float(row["aq"]) > 70.0]

    product_killed = 0
    geomean_killed = 0
    minpenalty_killed = 0
    stress_rows: list[dict[str, Any]] = []

    for row in aq_cut_rows:
        multipliers = [
            float(row["m_concentration"]),
            float(row["m_lifecycle"]),
            float(row["m_unknown"]),
            float(row["m_hustle"]),
            float(row["m_tail"]),
            float(row["ks_liquidity"]),
            float(row["ks_obsolescence"]),
        ]
        aq = float(row["aq"])
        product_risk = float(prod(multipliers))
        geomean_risk = product_risk ** (1.0 / float(len(multipliers)))
        minpenalty_risk = float(min(multipliers))

        fas_product = aq * product_risk
        fas_geomean = aq * geomean_risk
        fas_minpenalty = aq * minpenalty_risk

        if fas_product < 30.0:
            product_killed += 1
        if fas_geomean < 30.0:
            geomean_killed += 1
        if fas_minpenalty < 30.0:
            minpenalty_killed += 1

        stress_rows.append(
            {
                "sample_index": int(row["sample_index"]),
                "aq": _r6(aq),
                "product_risk": _r6(product_risk),
                "fas_product": _r6(fas_product),
            }
        )

    worst_cases = sorted(
        stress_rows,
        key=lambda item: (item["fas_product"], -item["aq"], item["sample_index"]),
    )[:10]

    fixed_all_m = 0.85
    fixed_count = 7
    fixed_product = fixed_all_m ** fixed_count
    fixed_geomean = fixed_product ** (1.0 / float(fixed_count))
    fixed_min = fixed_all_m

    total_cut = len(aq_cut_rows)
    return {
        "fixed_example": {
            "aq": 80.0,
            "all_m": fixed_all_m,
            "m_count": fixed_count,
            "product_fas": _r6(80.0 * fixed_product),
            "geomean_fas": _r6(80.0 * fixed_geomean),
            "minpenalty_fas": _r6(80.0 * fixed_min),
        },
        "population": {
            "aq_above_70_count": total_cut,
            "killed_by_product_pct": _fraction(product_killed, total_cut),
            "killed_by_geomean_pct": _fraction(geomean_killed, total_cut),
            "killed_by_minpenalty_pct": _fraction(minpenalty_killed, total_cut),
        },
        "worst_stacking_cases": worst_cases,
    }


def _write_sample_csv(out_dir: Path, scored_rows: list[dict[str, Any]]) -> None:
    sample_rows = sorted(scored_rows, key=lambda row: int(row["sample_index"]))[:10000]
    path = out_dir / "montecarlo_stats.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_FIELDS))
        writer.writeheader()
        for row in sample_rows:
            writer.writerow({field: row[field] for field in CSV_FIELDS})


def run_monte_carlo(
    *,
    out_dir: Path,
    seed: int,
    samples: int,
    run_config: RunConfig,
    v4_config: V4Config,
) -> dict[str, Any]:
    rng = random.Random(seed)
    samples_rows = generate_samples(max(0, int(samples)), rng)

    scored_rows: list[dict[str, Any]] = []
    fas_values: list[float] = []
    for idx, row in enumerate(samples_rows):
        scored = compute_fas_from_scalars(
            s1=float(row["s1"]),
            s2=float(row["s2"]),
            s3=float(row["s3"]),
            s4=float(row["s4"]),
            hhi_index=float(row["hhi_index"]),
            obs_weighted=float(row["obs_weighted"]),
            unknown_exposure=float(row["unknown_exposure"]),
            penny_ratio=float(row["penny_ratio"]),
            core_distinct_sku_count=int(row["core_distinct_sku_count"]),
            tail_ratio=float(row["tail_ratio"]),
            run_config=run_config,
            v4_config=v4_config,
        )
        scored_row = {"sample_index": idx, **scored}
        scored_rows.append(scored_row)
        fas_values.append(float(scored_row["fas"]))

    _write_sample_csv(out_dir, scored_rows)

    spearman = analyze_spearman(scored_rows, fas_values)
    permutation = analyze_permutation_importance(
        rows=scored_rows,
        fas_values=fas_values,
        seed=seed,
        run_config=run_config,
        v4_config=v4_config,
    )

    quantiles = {
        "p5": _r6(_quantile(fas_values, 0.05)),
        "p10": _r6(_quantile(fas_values, 0.10)),
        "p25": _r6(_quantile(fas_values, 0.25)),
        "p50": _r6(_quantile(fas_values, 0.50)),
        "p75": _r6(_quantile(fas_values, 0.75)),
        "p90": _r6(_quantile(fas_values, 0.90)),
        "p95": _r6(_quantile(fas_values, 0.95)),
    }

    count_above_70 = sum(1 for value in fas_values if value > 70.0)
    count_above_50 = sum(1 for value in fas_values if value > 50.0)
    count_below_30 = sum(1 for value in fas_values if value < 30.0)
    count_ks_liq = sum(1 for row in scored_rows if float(row["ks_liquidity"]) < 1.0)
    count_ks_obs = sum(1 for row in scored_rows if float(row["ks_obsolescence"]) < 1.0)

    stacking = _compute_stacking_stats(scored_rows)

    return {
        "spearman_correlations": spearman,
        "permutation_importance": permutation,
        "fas_quantiles": quantiles,
        "fas_thresholds": {
            "above_70_pct": _fraction(count_above_70, len(fas_values)),
            "above_50_pct": _fraction(count_above_50, len(fas_values)),
            "below_30_pct": _fraction(count_below_30, len(fas_values)),
        },
        "kill_switch_rates": {
            "ks_liquidity_fired_pct": _fraction(count_ks_liq, len(scored_rows)),
            "ks_obsolescence_fired_pct": _fraction(count_ks_obs, len(scored_rows)),
        },
        "stacking_stress": stacking,
    }

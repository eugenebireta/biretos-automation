from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from scripts.lot_scoring.run_config import RunConfig
from scripts.lot_scoring.simulation.monte_carlo import run_monte_carlo
from scripts.lot_scoring.simulation.scoring_kernel import V4Config
from scripts.lot_scoring.simulation.sweeper import run_sweep


def _build_recommendation(summary: dict[str, Any]) -> str:
    permutation = summary.get("permutation_importance", {})
    spearman = summary.get("spearman_correlations", {})
    kill_switch = summary.get("kill_switch_rates", {})
    stacking = summary.get("stacking_stress", {})

    top_factors = sorted(
        ((str(name), float(value)) for name, value in permutation.items()),
        key=lambda pair: (-pair[1], pair[0]),
    )[:10]

    lines: list[str] = []
    lines.append("# Sensitivity Recommendation")
    lines.append("")
    lines.append("## 1) Top Factors")
    if not top_factors:
        lines.append("- No factor data was produced.")
    else:
        for name, value in top_factors:
            rho = float(spearman.get(name, 0.0))
            lines.append(f"- `{name}`: permutation={value:.6f}, spearman={rho:.6f}")

    lines.append("")
    lines.append("## 2) Stacking Stress")
    population = stacking.get("population", {})
    fixed = stacking.get("fixed_example", {})
    lines.append(
        f"- AQ>70 population: {int(population.get('aq_above_70_count', 0))}"
    )
    lines.append(
        "- Killed rates (FAS<30): "
        f"product={float(population.get('killed_by_product_pct', 0.0)):.6f}%, "
        f"geomean={float(population.get('killed_by_geomean_pct', 0.0)):.6f}%, "
        f"minpenalty={float(population.get('killed_by_minpenalty_pct', 0.0)):.6f}%"
    )
    lines.append(
        "- Fixed AQ=80, all M=0.85: "
        f"product={float(fixed.get('product_fas', 0.0)):.6f}, "
        f"geomean={float(fixed.get('geomean_fas', 0.0)):.6f}, "
        f"minpenalty={float(fixed.get('minpenalty_fas', 0.0)):.6f}"
    )

    lines.append("")
    lines.append("## 3) Kill-Switch Rates")
    lines.append(
        f"- Liquidity kill-switch fired: {float(kill_switch.get('ks_liquidity_fired_pct', 0.0)):.6f}%"
    )
    lines.append(
        f"- Obsolescence kill-switch fired: {float(kill_switch.get('ks_obsolescence_fired_pct', 0.0)):.6f}%"
    )

    lines.append("")
    lines.append("## 4) Tuning Suggestions")
    killed_product = float(population.get("killed_by_product_pct", 0.0))
    ks_liq_rate = float(kill_switch.get("ks_liquidity_fired_pct", 0.0))
    ks_obs_rate = float(kill_switch.get("ks_obsolescence_fired_pct", 0.0))

    if killed_product > 15.0:
        lines.append("- Product stacking is aggressive. Review UNKNOWN/LIFECYCLE slopes and multiplier floors.")
    else:
        lines.append("- Product stacking is within moderate range for AQ>70 samples.")
    if ks_liq_rate > 10.0:
        lines.append("- Liquidity kill-switch fires often. Re-check `LIQUIDITY_KILL_THRESH` and source distributions.")
    if ks_obs_rate > 10.0:
        lines.append("- Obsolescence kill-switch fires often. Re-check `OBSOLESCENCE_KILL_THRESH` and lifecycle assumptions.")
    if ks_liq_rate <= 10.0 and ks_obs_rate <= 10.0:
        lines.append("- Kill-switch rates are stable; keep current thresholds unless business policy changes.")

    return "\n".join(lines) + "\n"


def run_simulation(
    *,
    out_dir: Path,
    seed: int,
    samples: int,
    run_config: RunConfig | None = None,
    v4_config: V4Config | None = None,
) -> dict[str, Any]:
    cfg = run_config or RunConfig()
    v4 = v4_config or V4Config()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "curves").mkdir(parents=True, exist_ok=True)

    sweep_inflection_points = run_sweep(
        out_dir=out_dir,
        seed=seed,
        run_config=cfg,
        v4_config=v4,
    )
    monte = run_monte_carlo(
        out_dir=out_dir,
        seed=seed,
        samples=samples,
        run_config=cfg,
        v4_config=v4,
    )

    permutation = monte.get("permutation_importance", {})
    top_factors = sorted(
        ((str(name), float(value)) for name, value in permutation.items()),
        key=lambda pair: (-pair[1], pair[0]),
    )[:10]

    summary = {
        "seed": int(seed),
        "samples": int(samples),
        "config": {
            "RunConfig": asdict(cfg),
            "V4Config": asdict(v4),
        },
        "spearman_correlations": monte.get("spearman_correlations", {}),
        "permutation_importance": monte.get("permutation_importance", {}),
        "top_10_factors_by_importance": [
            {"factor": name, "importance": round(value, 6)}
            for name, value in top_factors
        ],
        "fas_quantiles": monte.get("fas_quantiles", {}),
        "fas_thresholds": monte.get("fas_thresholds", {}),
        "kill_switch_rates": monte.get("kill_switch_rates", {}),
        "stacking_stress": monte.get("stacking_stress", {}),
        "sweep_inflection_points": sweep_inflection_points,
    }

    summary_path = out_dir / "sensitivity_summary.json"
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)

    recommendation_path = out_dir / "recommendation.md"
    recommendation_path.write_text(_build_recommendation(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run sensitivity simulation for strict independent scoring v4.0.")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic RNG seed.")
    parser.add_argument("--samples", type=int, default=50000, help="Number of Monte Carlo samples.")
    parser.add_argument(
        "--out-dir",
        type=str,
        default="downloads/audits/simulation_v4/",
        help="Output directory for simulation artifacts.",
    )
    args = parser.parse_args()

    run_simulation(
        out_dir=Path(args.out_dir),
        seed=int(args.seed),
        samples=max(0, int(args.samples)),
    )


if __name__ == "__main__":
    main()

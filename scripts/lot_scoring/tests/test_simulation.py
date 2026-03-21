import random

from scripts.lot_scoring.run_config import RunConfig
from scripts.lot_scoring.simulation.monte_carlo import generate_samples
from scripts.lot_scoring.simulation.run_sensitivity import run_simulation
from scripts.lot_scoring.simulation.scoring_kernel import V4Config, compute_fas_from_scalars


def test_simulation_reproducibility(tmp_path):
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"

    run_simulation(out_dir=out_a, seed=12345, samples=2000)
    run_simulation(out_dir=out_b, seed=12345, samples=2000)

    summary_a = (out_a / "sensitivity_summary.json").read_bytes()
    summary_b = (out_b / "sensitivity_summary.json").read_bytes()
    assert summary_a == summary_b


def test_simulation_sanity_bounds():
    run_config = RunConfig()
    v4_config = V4Config()
    rng = random.Random(7)

    samples = generate_samples(1000, rng)
    for sample in samples:
        scored = compute_fas_from_scalars(
            s1=float(sample["s1"]),
            s2=float(sample["s2"]),
            s3=float(sample["s3"]),
            s4=float(sample["s4"]),
            hhi_index=float(sample["hhi_index"]),
            obs_weighted=float(sample["obs_weighted"]),
            unknown_exposure=float(sample["unknown_exposure"]),
            penny_ratio=float(sample["penny_ratio"]),
            core_distinct_sku_count=int(sample["core_distinct_sku_count"]),
            tail_ratio=float(sample["tail_ratio"]),
            run_config=run_config,
            v4_config=v4_config,
        )

        assert 0.0 <= float(scored["fas"]) <= 100.0
        assert run_config.CONC_FLOOR <= float(scored["m_concentration"]) <= 1.0
        assert v4_config.LIFECYCLE_FLOOR <= float(scored["m_lifecycle"]) <= 1.0
        assert v4_config.UNKNOWN_FLOOR <= float(scored["m_unknown"]) <= 1.0
        assert run_config.HUSTLE_FLOOR <= float(scored["m_hustle"]) <= 1.0
        assert run_config.TAIL_FLOOR <= float(scored["m_tail"]) <= 1.0
        assert float(scored["ks_liquidity"]) in {run_config.LIQUIDITY_KILL_MULT, 1.0}
        assert float(scored["ks_obsolescence"]) in {run_config.OBSOLESCENCE_KILL_MULT, 1.0}

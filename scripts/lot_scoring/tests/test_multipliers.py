from scripts.lot_scoring.pipeline.score import (
    compute_kill_switches,
    compute_m_concentration,
    compute_m_hustle,
    compute_m_tail,
)
from scripts.lot_scoring.run_config import RunConfig


def test_hhi_penalty_examples():
    config = RunConfig()
    assert compute_m_concentration(0.25, config) == 1.0
    assert compute_m_concentration(1.0, config) == config.CONC_FLOOR
    assert abs(compute_m_concentration(0.5, config) - 0.625) < 1e-9


def test_hustle_penalty_bounds():
    config = RunConfig()
    low = compute_m_hustle(0.0, 0, config)
    high = compute_m_hustle(1.0, 1000, config)
    assert config.HUSTLE_FLOOR <= low <= 1.0
    assert config.HUSTLE_FLOOR <= high <= 1.0
    assert abs(high - config.HUSTLE_FLOOR) < 1e-12


def test_tail_penalty_monotonic():
    config = RunConfig()
    m_small = compute_m_tail(30.0, 1000.0, config)
    m_large = compute_m_tail(120.0, 1000.0, config)
    assert m_large <= m_small


def test_kill_switches():
    config = RunConfig()
    m_liq, m_obs = compute_kill_switches(0.05, 0.05, config)
    assert m_liq == config.LIQUIDITY_KILL_MULT
    assert m_obs == config.OBSOLESCENCE_KILL_MULT
    m_liq_ok, m_obs_ok = compute_kill_switches(0.8, 0.8, config)
    assert m_liq_ok == 1.0
    assert m_obs_ok == 1.0

from __future__ import annotations

from pathlib import Path
import sys

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from synthetic_bot_driver import (
    SyntheticTelegramDriver,
    load_reference_fixture,
    replay_reference_fixture,
    replay_reference_fixture_n_times,
)


def _fixture_path() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "synthetic_bot_reference.json"


def test_reference_fixture_replays_without_drift():
    result = replay_reference_fixture(_fixture_path())

    assert result["scenario_count"] == 5
    assert result["total_steps"] == 8
    assert result["match_rate"] == 1.0, result["mismatches"]
    assert result["mismatches"] == []


def test_waybill_confirm_scenario_records_snapshot_and_shadow_rows():
    fixture = load_reference_fixture(_fixture_path())
    scenario = next(item for item in fixture["scenarios"] if item["name"] == "nlu_get_waybill_confirm")

    driver = SyntheticTelegramDriver()
    actual_steps = driver.run_scenario(scenario)

    assert actual_steps[-1]["execution"]["status"] == "success"
    assert actual_steps[-1]["execution"]["pdf_size_bytes"] == 9
    assert actual_steps[-1]["side_effects"]["shadow_rows"] == 2
    assert actual_steps[-1]["side_effects"]["snapshot_rows"] == 1
    assert actual_steps[-1]["side_effects"]["employee_action_rows"] == 1


def test_reference_fixture_volume_mode_reaches_stage83_synthetic_threshold():
    result = replay_reference_fixture_n_times(_fixture_path(), repeat=7)

    assert result["repeat"] == 7
    assert result["synthetic_requests"] == 56
    assert result["match_rate"] == 1.0, result["mismatches"]

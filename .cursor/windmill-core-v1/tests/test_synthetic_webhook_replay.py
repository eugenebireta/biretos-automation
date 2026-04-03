from __future__ import annotations

from pathlib import Path
import sys

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from synthetic_webhook_driver import (
    SyntheticWebhookDriver,
    replay_reference_fixture,
    replay_reference_fixture_n_times,
)


def _fixture_path() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "synthetic_webhook_reference.json"


def test_reference_fixture_replays_without_drift():
    result = replay_reference_fixture(_fixture_path())

    assert result["scenario_count"] == 6
    assert result["total_steps"] == 8
    assert result["match_rate"] == 1.0, result["mismatches"]
    assert result["mismatches"] == []


def test_tbank_webhook_rejects_bad_token_without_creating_job():
    driver = SyntheticWebhookDriver()
    result = driver.run_step(
        {
            "input": {
                "endpoint": "tbank_invoice_paid",
                "headers": {"X-Api-Token": "wrong-secret"},
                "json": {
                    "eventType": "INVOICE_PAID",
                    "invoiceId": "INV-401",
                },
            }
        }
    )

    assert result["response"]["status_code"] == 403
    assert result["response"]["body"] == {"ok": False, "message": "Forbidden"}
    assert result["insert"] is None
    assert result["side_effects"]["jobs_total"] == 0


def test_reference_fixture_volume_mode_reaches_stage83_synthetic_threshold():
    result = replay_reference_fixture_n_times(_fixture_path(), repeat=7)

    assert result["repeat"] == 7
    assert result["synthetic_requests"] == 56
    assert result["match_rate"] == 1.0, result["mismatches"]

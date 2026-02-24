from copy import deepcopy
import json
import math

import pytest

from scripts.lot_scoring.cdm import LotRecord
from scripts.lot_scoring.governance_config import GovernanceConfig
from scripts.lot_scoring.pipeline.explain_v4 import (
    compute_loss_attribution,
    compute_v4_scalars,
    compute_zone,
)
from scripts.lot_scoring.pipeline.governance_flags import compute_governance_flags
from scripts.lot_scoring.run_config import RunConfig
from scripts.lot_scoring.run_full_ranking_v341 import _check_refs_drift, _compute_refs_manifest
from scripts.lot_scoring.simulation.scoring_kernel import V4Config


def test_loss_attribution_sums_to_total() -> None:
    payload = compute_loss_attribution(
        {
            "m_lifecycle": 0.80,
            "m_unknown": 0.50,
            "m_concentration": 0.90,
            "m_hustle": 0.70,
            "m_tail": 0.95,
            "ks_liquidity": 1.00,
            "ks_obsolescence": 1.00,
        }
    )

    components = payload["components"]
    sum_loss = sum(float(item["loss"]) for item in components)
    sum_pct = sum(float(item["pct"]) for item in components)

    assert sum_loss == pytest.approx(float(payload["total_loss"]), abs=1e-5)
    assert sum_pct == pytest.approx(1.0, abs=1e-5)


def test_loss_attribution_ln0_protection() -> None:
    payload = compute_loss_attribution(
        {
            "m_lifecycle": 1.00,
            "m_unknown": 0.00,
            "m_concentration": 1.00,
            "m_hustle": 1.00,
            "m_tail": 1.00,
            "ks_liquidity": 1.00,
            "ks_obsolescence": 1.00,
        }
    )
    unknown_component = next(item for item in payload["components"] if item["name"] == "M_Unknown")
    assert math.isfinite(float(unknown_component["loss"]))
    assert float(unknown_component["loss"]) == pytest.approx(round(-math.log(1e-9), 6), abs=1e-9)
    assert math.isfinite(float(payload["total_loss"]))


def test_refs_manifest_has_sha256() -> None:
    manifest = _compute_refs_manifest(usd_rate=78.0, gov_config=GovernanceConfig())
    refs = manifest["refs"]
    for key in (
        "category_obsolescence",
        "brand_score",
        "category_liquidity",
        "category_volume_proxy",
        "taxonomy_version",
    ):
        sha = str(refs[key]["sha256"])
        assert len(sha) == 64
        assert all(ch in "0123456789abcdef" for ch in sha)


def test_batch_independence_same_lot_same_fas() -> None:
    run_config = RunConfig()
    v4_config = V4Config()
    category_obsolescence = {
        "industrial_sensors": 0.76,
        "gas_safety": 0.86,
        "_default": 0.40,
    }
    core_skus = [
        {"category": "industrial_sensors", "effective_line_usd": 300.0},
        {"category": "gas_safety", "effective_line_usd": 700.0},
    ]
    metadata = {"core_count": 2, "tail_count": 1}

    lot_a = LotRecord(lot_id="L-A")
    lot_a.s1 = 0.65
    lot_a.s2 = 0.58
    lot_a.s3 = 0.62
    lot_a.s4 = 0.47
    lot_a.hhi_index = 0.33
    lot_a.unknown_exposure = 0.12
    lot_a.penny_line_ratio = 0.08
    lot_a.core_distinct_sku_count = 5

    lot_b = LotRecord(lot_id="L-B")
    lot_b.s1 = lot_a.s1
    lot_b.s2 = lot_a.s2
    lot_b.s3 = lot_a.s3
    lot_b.s4 = lot_a.s4
    lot_b.hhi_index = lot_a.hhi_index
    lot_b.unknown_exposure = lot_a.unknown_exposure
    lot_b.penny_line_ratio = lot_a.penny_line_ratio
    lot_b.core_distinct_sku_count = lot_a.core_distinct_sku_count

    out_a = compute_v4_scalars(
        lot=lot_a,
        metadata=metadata,
        core_skus=core_skus,
        category_obsolescence=category_obsolescence,
        run_config=run_config,
        v4_config=v4_config,
    )
    out_b = compute_v4_scalars(
        lot=lot_b,
        metadata=metadata,
        core_skus=core_skus,
        category_obsolescence=category_obsolescence,
        run_config=run_config,
        v4_config=v4_config,
    )

    assert json.dumps(out_a, sort_keys=True) == json.dumps(out_b, sort_keys=True)


def test_zone_boundaries() -> None:
    config = GovernanceConfig()
    assert compute_zone(60.0, config) == "PASS"
    assert compute_zone(59.99, config) == "REVIEW"
    assert compute_zone(35.0, config) == "REVIEW"
    assert compute_zone(34.99, config) == "WEAK"
    assert compute_zone(0.0, config) == "WEAK"
    assert compute_zone(100.0, config) == "PASS"


def test_governance_flags_hvl() -> None:
    config = GovernanceConfig()
    lot = LotRecord(lot_id="L-1")
    lot.unknown_exposure = 0.1
    lot.hhi_index = 0.2

    flags_low = compute_governance_flags(
        lot=lot,
        metadata={"total_effective_usd": 499.99, "core_count": 1, "tail_count": 0},
        v4_scalars={"unknown_exposure": 0.1, "hhi_index": 0.2},
        gov_config=config,
    )
    flags_hvl = compute_governance_flags(
        lot=lot,
        metadata={"total_effective_usd": 500.0, "core_count": 1, "tail_count": 0},
        v4_scalars={"unknown_exposure": 0.1, "hhi_index": 0.2},
        gov_config=config,
    )

    assert "HVL" not in flags_low
    assert "HVL" in flags_hvl


def test_governance_config_validation() -> None:
    GovernanceConfig()
    with pytest.raises(ValueError):
        GovernanceConfig(HVL_THRESHOLD_USD=-1.0)
    with pytest.raises(ValueError):
        GovernanceConfig(ZONE_PASS_THRESH=20.0, ZONE_REVIEW_THRESH=50.0)


def test_strict_refs_no_drift(tmp_path) -> None:
    current = _compute_refs_manifest(usd_rate=78.0, gov_config=GovernanceConfig())
    previous = deepcopy(current)
    previous["run_timestamp"] = "1970-01-01T00:00:00Z"
    previous_path = tmp_path / "prev.json"
    previous_path.write_text(json.dumps(previous), encoding="utf-8")

    _check_refs_drift(current, previous_path, strict=True)


def test_strict_refs_sha256_drift_warning(tmp_path, capsys) -> None:
    current = _compute_refs_manifest(usd_rate=78.0, gov_config=GovernanceConfig())
    previous = deepcopy(current)
    previous["refs"]["category_obsolescence"]["sha256"] = "0" * 64
    previous_path = tmp_path / "prev.json"
    previous_path.write_text(json.dumps(previous), encoding="utf-8")

    _check_refs_drift(current, previous_path, strict=False)

    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "category_obsolescence" in err
    assert "SHA256 mismatch" in err


def test_strict_refs_sha256_drift_fail(tmp_path) -> None:
    current = _compute_refs_manifest(usd_rate=78.0, gov_config=GovernanceConfig())
    previous = deepcopy(current)
    previous["refs"]["category_obsolescence"]["sha256"] = "0" * 64
    previous_path = tmp_path / "prev.json"
    previous_path.write_text(json.dumps(previous), encoding="utf-8")

    with pytest.raises(RuntimeError, match="STRICT_REFS_GUARD") as exc_info:
        _check_refs_drift(current, previous_path, strict=True)

    message = str(exc_info.value)
    assert "category_obsolescence" in message
    assert "SHA256 mismatch" in message


def test_strict_refs_usd_rate_drift(tmp_path, capsys) -> None:
    current = _compute_refs_manifest(usd_rate=78.0, gov_config=GovernanceConfig())
    previous = deepcopy(current)
    previous["etl_usd_rate"] = 100.0
    previous_path = tmp_path / "prev.json"
    previous_path.write_text(json.dumps(previous), encoding="utf-8")

    _check_refs_drift(current, previous_path, strict=False)

    err = capsys.readouterr().err
    assert "etl_usd_rate" in err
    assert "changed" in err
    assert "78.0" in err
    assert "100.0" in err


@pytest.mark.parametrize("prev_content", ['{"schema_version":"v4.0"}', '"NOT_JSON"'])
def test_strict_refs_missing_keys_in_previous(tmp_path, capsys, prev_content: str) -> None:
    current = _compute_refs_manifest(usd_rate=78.0, gov_config=GovernanceConfig())
    previous_path = tmp_path / "prev.json"
    previous_path.write_text(prev_content, encoding="utf-8")

    _check_refs_drift(current, previous_path, strict=False)

    err = capsys.readouterr().err
    assert err.count("missing in previous manifest") >= 5

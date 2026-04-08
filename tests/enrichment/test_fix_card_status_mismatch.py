"""Tests for fix_card_status_mismatch.py."""
from __future__ import annotations

import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from fix_card_status_mismatch import find_mismatches, fix_single, run, MismatchFixResult


@pytest.fixture
def evidence_dir(tmp_path):
    """Create temp evidence dir with test fixtures."""
    return tmp_path


def _write_evidence(evidence_dir: Path, pn: str, **overrides) -> Path:
    """Helper to write a test evidence file."""
    data = {
        "pn": pn,
        "card_status": overrides.get("card_status", "AUTO_PUBLISH"),
        "review_reasons": overrides.get("review_reasons", []),
        "policy_decision_v2": {
            "card_status": overrides.get("pd_v2_card_status",
                                         overrides.get("card_status", "AUTO_PUBLISH")),
        },
        "verifier_shadow": {
            "packet": {
                "card_status": overrides.get("verifier_card_status", "DRAFT_ONLY"),
            },
        },
        "refresh_trace": {
            "policy_card_status_mismatch": overrides.get("mismatch", True),
            "policy_card_status_historical": overrides.get("historical", "DRAFT_ONLY"),
        },
    }
    fpath = evidence_dir / f"evidence_{pn}.json"
    fpath.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return fpath


def test_find_mismatches_finds_flagged(evidence_dir):
    _write_evidence(evidence_dir, "SKU1", mismatch=True)
    _write_evidence(evidence_dir, "SKU2", mismatch=False)
    _write_evidence(evidence_dir, "SKU3", mismatch=True)
    result = find_mismatches(evidence_dir)
    pns = [f.stem.replace("evidence_", "") for f in result]
    assert sorted(pns) == ["SKU1", "SKU3"]


def test_find_mismatches_empty_dir(evidence_dir):
    assert find_mismatches(evidence_dir) == []


def test_fix_single_reconciles_card_status(evidence_dir):
    fpath = _write_evidence(evidence_dir, "SKU1",
                            card_status="AUTO_PUBLISH",
                            verifier_card_status="DRAFT_ONLY")
    result = fix_single(fpath, "test_trace_1")
    assert result["action"] == "fixed"
    assert result["old_card_status"] == "AUTO_PUBLISH"
    assert result["new_card_status"] == "DRAFT_ONLY"
    # Verify file was updated
    data = json.loads(fpath.read_text(encoding="utf-8"))
    assert data["card_status"] == "DRAFT_ONLY"
    assert data["policy_decision_v2"]["card_status"] == "DRAFT_ONLY"
    assert data["refresh_trace"]["policy_card_status_mismatch"] is False


def test_fix_single_removes_holdout_reason(evidence_dir):
    fpath = _write_evidence(evidence_dir, "SKU1",
                            card_status="AUTO_PUBLISH",
                            review_reasons=["LEGACY_AUTO_PUBLISH_HOLDOUT"])
    result = fix_single(fpath, "test_trace_2")
    assert result["action"] == "fixed"
    data = json.loads(fpath.read_text(encoding="utf-8"))
    assert "LEGACY_AUTO_PUBLISH_HOLDOUT" not in data["review_reasons"]


def test_fix_single_dry_run_no_write(evidence_dir):
    fpath = _write_evidence(evidence_dir, "SKU1",
                            card_status="AUTO_PUBLISH",
                            verifier_card_status="DRAFT_ONLY")
    result = fix_single(fpath, "test_trace_3", dry_run=True)
    assert result["action"] == "fixed"
    # File should NOT be modified
    data = json.loads(fpath.read_text(encoding="utf-8"))
    assert data["card_status"] == "AUTO_PUBLISH"


def test_fix_single_already_matching(evidence_dir):
    fpath = _write_evidence(evidence_dir, "SKU1",
                            card_status="DRAFT_ONLY",
                            pd_v2_card_status="DRAFT_ONLY",
                            verifier_card_status="DRAFT_ONLY",
                            mismatch=True)
    result = fix_single(fpath, "test_trace_4")
    # Only mismatch flag should be cleared
    assert result["action"] == "fixed"
    data = json.loads(fpath.read_text(encoding="utf-8"))
    assert data["refresh_trace"]["policy_card_status_mismatch"] is False


def test_fix_single_no_verifier_uses_historical(evidence_dir):
    data = {
        "pn": "SKU1",
        "card_status": "AUTO_PUBLISH",
        "review_reasons": [],
        "policy_decision_v2": {"card_status": "AUTO_PUBLISH"},
        "refresh_trace": {
            "policy_card_status_mismatch": True,
            "policy_card_status_historical": "REVIEW_REQUIRED",
        },
    }
    fpath = evidence_dir / "evidence_SKU1.json"
    fpath.write_text(json.dumps(data), encoding="utf-8")
    result = fix_single(fpath, "test_trace_5")
    assert result["action"] == "fixed"
    assert result["new_card_status"] == "REVIEW_REQUIRED"


def test_fix_single_no_ground_truth_skips(evidence_dir):
    data = {
        "pn": "SKU1",
        "card_status": "AUTO_PUBLISH",
        "review_reasons": [],
        "policy_decision_v2": {"card_status": "AUTO_PUBLISH"},
        "refresh_trace": {
            "policy_card_status_mismatch": True,
        },
    }
    fpath = evidence_dir / "evidence_SKU1.json"
    fpath.write_text(json.dumps(data), encoding="utf-8")
    result = fix_single(fpath, "test_trace_6")
    assert result["action"] == "skipped"


def test_run_full_batch(evidence_dir):
    _write_evidence(evidence_dir, "A1", card_status="AUTO_PUBLISH")
    _write_evidence(evidence_dir, "A2", card_status="AUTO_PUBLISH",
                    review_reasons=["LEGACY_AUTO_PUBLISH_HOLDOUT"])
    _write_evidence(evidence_dir, "A3", mismatch=False)  # should be ignored
    result = run("test_batch_1", evidence_dir=evidence_dir)
    assert result.total_scanned == 3
    assert len(result.fixed) == 2
    assert len(result.errors) == 0


def test_run_requires_trace_id(evidence_dir):
    with pytest.raises(ValueError, match="trace_id"):
        run("", evidence_dir=evidence_dir)


def test_fix_preserves_other_review_reasons(evidence_dir):
    fpath = _write_evidence(evidence_dir, "SKU1",
                            card_status="AUTO_PUBLISH",
                            review_reasons=["LEGACY_AUTO_PUBLISH_HOLDOUT",
                                            "category_mismatch"])
    fix_single(fpath, "test_trace_7")
    data = json.loads(fpath.read_text(encoding="utf-8"))
    assert data["review_reasons"] == ["category_mismatch"]


def test_fix_adds_trace_to_refresh_trace(evidence_dir):
    fpath = _write_evidence(evidence_dir, "SKU1", card_status="AUTO_PUBLISH")
    fix_single(fpath, "my_trace_123")
    data = json.loads(fpath.read_text(encoding="utf-8"))
    assert data["refresh_trace"]["policy_card_status_fix_trace_id"] == "my_trace_123"
    assert "policy_card_status_fix_ts" in data["refresh_trace"]

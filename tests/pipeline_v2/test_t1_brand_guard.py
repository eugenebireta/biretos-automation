"""Tests for T1 Sync Guard — Step 1 hotfix.

Regression test: all 19 SKUs that were wrongly corrected by auto-fix
(reverted by brand_validation_log.jsonl) MUST be skipped by the guard.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.pipeline_v2.t1_brand_guard import (
    should_skip_brand_autofix,
    get_t1_trust,
    needs_sync,
)


ROOT = Path(__file__).resolve().parents[2]
EV_DIR = ROOT / "downloads" / "evidence"
VAL_LOG = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "brand_validation_log.jsonl"


def load_reverted_pns() -> list[str]:
    """Return PNs of SKUs that auto-fix got wrong (validator reverted them)."""
    if not VAL_LOG.exists():
        return []
    reverted = []
    for line in VAL_LOG.read_text(encoding="utf-8").strip().split("\n"):
        v = json.loads(line)
        if v["verdict"]["verdict"] == "revert_to_old":
            reverted.append(v["pn"])
    return reverted


def load_evidence(pn: str) -> dict:
    f = EV_DIR / f"evidence_{pn}.json"
    return json.loads(f.read_text(encoding="utf-8"))


@pytest.mark.parametrize("pn", load_reverted_pns())
def test_guard_blocks_wrong_brand_corrections(pn: str):
    """All 19 SKUs where auto-fix picked wrong brand MUST be skipped by guard."""
    ev = load_evidence(pn)
    skip, reason = should_skip_brand_autofix(ev)
    assert skip, f"{pn}: guard should have blocked autofix but did not ({reason})"


def test_t1_trust_none_when_empty():
    assert get_t1_trust({}) == "none"
    assert get_t1_trust({"structured_identity": {}}) == "none"


def test_t1_trust_weak_without_exact_match():
    ev = {"structured_identity": {"confirmed_manufacturer": "Honeywell"}}
    assert get_t1_trust(ev) == "weak"


def test_t1_trust_strong_with_title_match():
    ev = {"structured_identity": {
        "confirmed_manufacturer": "Honeywell",
        "exact_title_pn_match": True,
    }}
    assert get_t1_trust(ev) == "strong"


def test_parent_subbrand_compat_no_sync():
    """brand=Honeywell + T1=Esser is acceptable — both name the same org."""
    ev = {
        "brand": "Honeywell",
        "structured_identity": {
            "confirmed_manufacturer": "Esser",
            "exact_title_pn_match": True,
        },
    }
    assert needs_sync(ev) is None


def test_genuine_mismatch_flagged():
    """brand=Honeywell + T1=Dell is a real divergence."""
    ev = {
        "brand": "Honeywell",
        "structured_identity": {
            "confirmed_manufacturer": "Dell",
            "exact_title_pn_match": True,
        },
    }
    assert needs_sync(ev) == ("Honeywell", "Dell")

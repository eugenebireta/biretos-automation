"""Tests for identity_checker.py

Coverage:
  - IdentityArtifact acceptance rules
  - retrospective_identity_boost logic
  - select_identity_sprint_cohort stratification
  - training data recording
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Path bootstrap
_SCRIPTS = Path(__file__).parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from identity_checker import (
    IdentityArtifact,
    evaluate_acceptance,
    retrospective_identity_boost,
    select_identity_sprint_cohort,
    _STRUCTURED_CONTEXTS,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_checkpoint(**overrides) -> dict:
    """Minimal checkpoint with identity_weak SKU."""
    base = {
        "TEST001": {
            "pn": "TEST001",
            "brand": "Honeywell",
            "card_status": "DRAFT_ONLY",
            "policy_decision_v2": {"identity_level": "weak"},
            "structured_identity": {
                "exact_jsonld_pn_match": False,
                "exact_title_pn_match": False,
                "exact_h1_pn_match": False,
                "exact_product_context_pn_match": False,
                "exact_structured_pn_match": False,
                "structured_pn_match_location": "",
            },
            "trace": {"structured_pn_match_location": "", "pn_match_location": ""},
            "photo": {"verdict": "KEEP"},
            "price": {"price_status": "no_price_found"},
        }
    }
    base["TEST001"].update(overrides)
    return base


def _write_checkpoint(tmp_path: Path, data: dict) -> Path:
    cp = tmp_path / "checkpoint.json"
    cp.write_text(json.dumps(data), encoding="utf-8")
    return cp


# ══════════════════════════════════════════════════════════════════════════════
# IdentityArtifact acceptance rules
# ══════════════════════════════════════════════════════════════════════════════

class TestEvaluateAcceptance:

    def _artifact(self, **kw) -> IdentityArtifact:
        defaults = {
            "pn": "TEST001", "brand": "Honeywell",
            "pn_match_type": "exact", "confidence": "high",
            "source_type": "manufacturer", "source_domain": "honeywell.com",
        }
        defaults.update(kw)
        return IdentityArtifact(**defaults)

    def test_exact_tier1_manufacturer_high_conf_confirmed(self):
        art = self._artifact(
            pn_match_type="exact", confidence="high",
            source_type="manufacturer", source_domain="honeywell.com",
        )
        trusted = ["honeywell.com", "sps.honeywell.com", "rs-online.com"]
        result = evaluate_acceptance(art, trusted)
        assert result.accept_for_pipeline is True
        assert result.identity_status == "confirmed"
        assert result.source_strength == "tier1"

    def test_exact_tier2_distributor_medium_conf_confirmed(self):
        art = self._artifact(
            pn_match_type="exact", confidence="medium",
            source_type="distributor", source_domain="conrad.com",
        )
        # tier1 = first 3, tier2 = rest
        trusted = ["honeywell.com", "sps.honeywell.com", "rs-online.com", "conrad.com"]
        result = evaluate_acceptance(art, trusted)
        assert result.accept_for_pipeline is True
        assert result.identity_status == "confirmed"
        assert result.source_strength == "tier2"

    def test_exact_weak_source_not_confirmed(self):
        """Exact match but unknown domain → probable, NOT confirmed."""
        art = self._artifact(
            pn_match_type="exact", confidence="low",
            source_type="other", source_domain="somemarket.ru",
        )
        trusted = ["honeywell.com", "rs-online.com"]
        result = evaluate_acceptance(art, trusted)
        assert result.accept_for_pipeline is False
        assert result.identity_status == "probable"
        assert result.source_strength == "weak"

    def test_family_match_not_confirmed(self):
        """Family match must never be confirmed."""
        art = self._artifact(pn_match_type="family", confidence="high",
                             source_type="manufacturer", source_domain="honeywell.com")
        trusted = ["honeywell.com"]
        result = evaluate_acceptance(art, trusted)
        assert result.accept_for_pipeline is False
        assert result.identity_status == "probable"
        assert result.reject_reason is not None

    def test_inferred_match_not_found(self):
        art = self._artifact(pn_match_type="inferred", confidence="high",
                             source_type="manufacturer")
        result = evaluate_acceptance(art, [])
        assert result.accept_for_pipeline is False
        assert result.identity_status == "not_found"

    def test_not_found_not_accepted(self):
        art = self._artifact(pn_match_type="not_found", confidence="high")
        result = evaluate_acceptance(art, [])
        assert result.accept_for_pipeline is False

    def test_exact_high_conf_manufacturer_no_trusted_list_accepted(self):
        """Exact + high + manufacturer works even without trusted_domains list."""
        art = self._artifact(
            pn_match_type="exact", confidence="high",
            source_type="manufacturer", source_domain="unknown.com",
        )
        result = evaluate_acceptance(art, trusted_domains=None)
        assert result.accept_for_pipeline is True
        assert result.identity_status == "confirmed"

    def test_source_strength_tier1_from_first_three(self):
        trusted = ["a.com", "b.com", "c.com", "d.com", "e.com"]
        art = self._artifact(source_domain="c.com")
        result = evaluate_acceptance(art, trusted)
        assert result.source_strength == "tier1"

    def test_source_strength_tier2_from_rest(self):
        trusted = ["a.com", "b.com", "c.com", "d.com", "e.com"]
        art = self._artifact(source_domain="d.com")
        result = evaluate_acceptance(art, trusted)
        assert result.source_strength == "tier2"


# ══════════════════════════════════════════════════════════════════════════════
# retrospective_identity_boost
# ══════════════════════════════════════════════════════════════════════════════

class TestRetrospectiveBoost:

    def test_title_match_boosts_to_strong(self, tmp_path):
        cp = _make_checkpoint()
        cp["TEST001"]["structured_identity"]["exact_title_pn_match"] = True
        cp["TEST001"]["structured_identity"]["exact_structured_pn_match"] = True
        cp["TEST001"]["structured_identity"]["structured_pn_match_location"] = "title"

        cp_path = _write_checkpoint(tmp_path, cp)
        stats = retrospective_identity_boost(cp_path, training=False)

        assert stats["boosted_to_strong"] == 1
        result = json.loads(cp_path.read_text())
        assert result["TEST001"]["policy_decision_v2"]["identity_level"] == "strong"

    def test_h1_match_boosts_to_strong(self, tmp_path):
        cp = _make_checkpoint()
        cp["TEST001"]["structured_identity"]["exact_h1_pn_match"] = True
        cp["TEST001"]["structured_identity"]["exact_structured_pn_match"] = True
        cp["TEST001"]["structured_identity"]["structured_pn_match_location"] = "h1"

        cp_path = _write_checkpoint(tmp_path, cp)
        stats = retrospective_identity_boost(cp_path, training=False)

        assert stats["boosted_to_strong"] == 1
        result = json.loads(cp_path.read_text())
        assert result["TEST001"]["policy_decision_v2"]["identity_level"] == "strong"

    def test_jsonld_match_boosts_to_strong(self, tmp_path):
        cp = _make_checkpoint()
        cp["TEST001"]["structured_identity"]["exact_jsonld_pn_match"] = True
        cp["TEST001"]["structured_identity"]["exact_structured_pn_match"] = True
        cp["TEST001"]["structured_identity"]["structured_pn_match_location"] = "jsonld"

        cp_path = _write_checkpoint(tmp_path, cp)
        stats = retrospective_identity_boost(cp_path, training=False)

        assert stats["boosted_to_strong"] == 1

    def test_no_match_stays_weak(self, tmp_path):
        """SKU with no structured match must stay weak."""
        cp = _make_checkpoint()
        cp_path = _write_checkpoint(tmp_path, cp)
        stats = retrospective_identity_boost(cp_path, training=False)

        assert stats["boosted_to_strong"] == 0
        assert stats["boosted_to_medium"] == 0
        assert stats["remained_weak"] == 1

    def test_already_strong_not_touched(self, tmp_path):
        cp = _make_checkpoint()
        cp["TEST001"]["policy_decision_v2"]["identity_level"] = "strong"
        cp_path = _write_checkpoint(tmp_path, cp)
        stats = retrospective_identity_boost(cp_path, training=False)

        assert stats["already_strong"] == 1
        assert stats["boosted_to_strong"] == 0

    def test_trace_fallback_for_structured_location(self, tmp_path):
        """If structured_identity is empty, fall back to trace.structured_pn_match_location."""
        cp = _make_checkpoint()
        # No structured_identity data, but trace has it
        cp["TEST001"]["structured_identity"] = {}
        cp["TEST001"]["trace"]["structured_pn_match_location"] = "title"

        cp_path = _write_checkpoint(tmp_path, cp)
        stats = retrospective_identity_boost(cp_path, training=False)

        assert stats["boosted_to_strong"] == 1

    def test_training_data_written(self, tmp_path):
        cp = _make_checkpoint()
        cp["TEST001"]["structured_identity"]["exact_title_pn_match"] = True
        cp["TEST001"]["structured_identity"]["exact_structured_pn_match"] = True
        cp["TEST001"]["structured_identity"]["structured_pn_match_location"] = "title"
        cp_path = _write_checkpoint(tmp_path, cp)

        # Patch TRAINING_DIR to tmp_path
        import identity_checker
        original = identity_checker.TRAINING_DIR
        identity_checker.TRAINING_DIR = tmp_path
        try:
            retrospective_identity_boost(cp_path, training=True)
        finally:
            identity_checker.TRAINING_DIR = original

        training_file = tmp_path / "identity_boost_examples.jsonl"
        assert training_file.exists()
        record = json.loads(training_file.read_text().strip())
        assert record["output"]["new_level"] == "strong"
        assert record["output"]["old_level"] == "weak"

    def test_boost_signals_recorded(self, tmp_path):
        cp = _make_checkpoint()
        cp["TEST001"]["structured_identity"]["exact_title_pn_match"] = True
        cp["TEST001"]["structured_identity"]["exact_structured_pn_match"] = True
        cp["TEST001"]["structured_identity"]["structured_pn_match_location"] = "title"
        cp_path = _write_checkpoint(tmp_path, cp)

        retrospective_identity_boost(cp_path, training=False)
        result = json.loads(cp_path.read_text())
        signals = result["TEST001"]["policy_decision_v2"]["identity_boost_signals"]
        assert any("structured_pn_match" in s for s in signals)

    def test_multiple_skus_mixed(self, tmp_path):
        """Mix of boosted, weak, already-strong."""
        cp = {
            "STRONG": {
                "pn": "STRONG", "brand": "Honeywell",
                "policy_decision_v2": {"identity_level": "strong"},
                "structured_identity": {},
                "trace": {},
            },
            "WILL_BOOST": {
                "pn": "WILL_BOOST", "brand": "Honeywell",
                "policy_decision_v2": {"identity_level": "weak"},
                "structured_identity": {
                    "exact_structured_pn_match": True,
                    "structured_pn_match_location": "h1",
                },
                "trace": {},
            },
            "STAYS_WEAK": {
                "pn": "STAYS_WEAK", "brand": "Honeywell",
                "policy_decision_v2": {"identity_level": "weak"},
                "structured_identity": {"exact_structured_pn_match": False, "structured_pn_match_location": ""},
                "trace": {},
            },
        }
        cp_path = _write_checkpoint(tmp_path, cp)
        stats = retrospective_identity_boost(cp_path, training=False)

        assert stats["already_strong"] == 1
        assert stats["boosted_to_strong"] == 1
        assert stats["remained_weak"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# select_identity_sprint_cohort
# ══════════════════════════════════════════════════════════════════════════════

class TestSelectSprintCohort:

    def _make_cp(self, n_photo_price=3, n_photo=5, n_price=2, n_numeric=10, n_alpha=15, n_nothing=5):
        """Build a checkpoint with N SKUs in each group."""
        cp = {}
        i = 0

        def add(prefix, has_photo, has_price, is_numeric=False):
            nonlocal i
            pn = f"{prefix}{i:03d}" if not is_numeric else f"{i:06d}"
            cp[pn] = {
                "pn": pn, "brand": "Honeywell",
                "policy_decision_v2": {"identity_level": "weak"},
                "structured_identity": {"exact_structured_pn_match": False, "structured_pn_match_location": ""},
                "trace": {},
                "photo": {"verdict": "KEEP" if has_photo else "REJECT"},
                "price": {"price_status": "public_price" if has_price else "no_price_found"},
            }
            i += 1

        for _ in range(n_photo_price): add("PP", True, True)
        for _ in range(n_photo): add("PH", True, False)
        for _ in range(n_price): add("PR", False, True)
        for _ in range(n_numeric): add("", False, False, is_numeric=True)
        for _ in range(n_alpha): add("AL", False, False)
        for _ in range(n_nothing): add("ZZ", False, False)

        return cp

    def test_cohort_not_larger_than_size(self, tmp_path):
        cp = self._make_cp()
        cp_path = _write_checkpoint(tmp_path, cp)
        out = tmp_path / "cohort.json"

        result = select_identity_sprint_cohort(cp_path, cohort_size=20, output_path=out)
        assert len(result) <= 20

    def test_cohort_file_written(self, tmp_path):
        cp = self._make_cp()
        cp_path = _write_checkpoint(tmp_path, cp)
        out = tmp_path / "cohort.json"

        select_identity_sprint_cohort(cp_path, cohort_size=15, output_path=out)
        assert out.exists()
        data = json.loads(out.read_text())
        assert "selected_pns" in data
        assert data["cohort_size"] == len(data["selected_pns"])

    def test_stratified_includes_photo_price_group(self, tmp_path):
        cp = self._make_cp(n_photo_price=5)
        cp_path = _write_checkpoint(tmp_path, cp)
        out = tmp_path / "cohort.json"

        pns = select_identity_sprint_cohort(cp_path, cohort_size=30, output_path=out)
        data = json.loads(out.read_text())
        # Group stats should show photo_and_price group
        assert data["groups"]["has_photo_and_price"] == 5

    def test_already_strong_excluded(self, tmp_path):
        cp = self._make_cp(n_photo_price=3)
        # Mark some as strong (already boosted)
        for pn in list(cp.keys())[:5]:
            cp[pn]["policy_decision_v2"]["identity_level"] = "strong"
        cp_path = _write_checkpoint(tmp_path, cp)
        out = tmp_path / "cohort.json"

        pns = select_identity_sprint_cohort(cp_path, cohort_size=50, output_path=out)
        result_data = json.loads(out.read_text())
        # total_weak should exclude the 5 strong ones
        assert result_data["total_weak_after_boost"] == len(cp) - 5

    def test_no_duplicates_in_cohort(self, tmp_path):
        cp = self._make_cp()
        cp_path = _write_checkpoint(tmp_path, cp)
        out = tmp_path / "cohort.json"

        pns = select_identity_sprint_cohort(cp_path, cohort_size=30, output_path=out)
        assert len(pns) == len(set(pns))


# ══════════════════════════════════════════════════════════════════════════════
# Integration: boost stats consistency
# ══════════════════════════════════════════════════════════════════════════════

class TestBoostStats:

    def test_stats_sum_to_total_checked(self, tmp_path):
        cp = {
            "A": {"pn": "A", "brand": "H", "policy_decision_v2": {"identity_level": "weak"},
                  "structured_identity": {"exact_structured_pn_match": True, "structured_pn_match_location": "title"}, "trace": {}},
            "B": {"pn": "B", "brand": "H", "policy_decision_v2": {"identity_level": "weak"},
                  "structured_identity": {"exact_structured_pn_match": False, "structured_pn_match_location": ""}, "trace": {}},
            "C": {"pn": "C", "brand": "H", "policy_decision_v2": {"identity_level": "strong"},
                  "structured_identity": {}, "trace": {}},
        }
        cp_path = _write_checkpoint(tmp_path, cp)
        stats = retrospective_identity_boost(cp_path, training=False)

        assert stats["total_checked"] == 3
        assert stats["boosted_to_strong"] + stats["boosted_to_medium"] + stats["remained_weak"] + stats["already_strong"] == 3

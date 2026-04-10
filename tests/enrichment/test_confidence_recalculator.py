"""R1.2 — Confidence Recalculator: deterministic tests.

Covers: signal extraction, label computation, evidence processing,
full pipeline dry-run / apply, idempotency, and distribution tracking.

No live API, no unmocked time/randomness.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from confidence_recalculator import (  # noqa: E402
    LABEL_HIGH,
    LABEL_LOW,
    LABEL_MEDIUM,
    LABEL_VERY_LOW,
    compute_label,
    extract_signals,
    recalculate_confidence,
    run_recalculator,
)


# =============================================================================
# Signal extraction
# =============================================================================

class TestExtractSignals:
    """Extract boolean signals from evidence bundles."""

    def test_all_strong(self):
        evidence = {
            "identity_level": "strong",
            "photo": {"verdict": "ACCEPT"},
            "price": {"price_status": "public_price"},
        }
        signals = extract_signals(evidence)
        assert signals["identity_strong"] is True
        assert signals["photo_ok"] is True
        assert signals["price_available"] is True

    def test_weak_identity(self):
        evidence = {
            "identity_level": "weak",
            "photo": {"verdict": "ACCEPT"},
            "price": {"price_status": "public_price"},
        }
        signals = extract_signals(evidence)
        assert signals["identity_strong"] is False

    def test_reject_photo(self):
        evidence = {
            "identity_level": "strong",
            "photo": {"verdict": "REJECT"},
            "price": {"price_status": "public_price"},
        }
        signals = extract_signals(evidence)
        assert signals["photo_ok"] is False

    def test_keep_photo_counts(self):
        evidence = {
            "identity_level": "strong",
            "photo": {"verdict": "KEEP"},
            "price": {"price_status": "no_price_found"},
        }
        signals = extract_signals(evidence)
        assert signals["photo_ok"] is True
        assert signals["price_available"] is False

    def test_no_price(self):
        evidence = {
            "identity_level": "strong",
            "photo": {"verdict": "ACCEPT"},
            "price": {"price_status": "no_price_found"},
        }
        signals = extract_signals(evidence)
        assert signals["price_available"] is False

    def test_rfq_price_counts(self):
        evidence = {
            "identity_level": "strong",
            "photo": {"verdict": "ACCEPT"},
            "price": {"price_status": "rfq_only"},
        }
        signals = extract_signals(evidence)
        assert signals["price_available"] is True

    def test_hidden_price_counts(self):
        evidence = {
            "identity_level": "strong",
            "photo": {"verdict": "ACCEPT"},
            "price": {"price_status": "hidden_price"},
        }
        signals = extract_signals(evidence)
        assert signals["price_available"] is True

    def test_empty_evidence(self):
        signals = extract_signals({})
        assert signals["identity_strong"] is False
        assert signals["photo_ok"] is False
        assert signals["price_available"] is False

    def test_ambiguous_offer_not_available(self):
        evidence = {
            "identity_level": "strong",
            "photo": {"verdict": "ACCEPT"},
            "price": {"price_status": "ambiguous_offer"},
        }
        signals = extract_signals(evidence)
        assert signals["price_available"] is False


# =============================================================================
# Label computation
# =============================================================================

class TestComputeLabel:
    """Confidence label from boolean signals."""

    def test_high_all_true(self):
        label = compute_label({
            "identity_strong": True, "photo_ok": True, "price_available": True,
        })
        assert label == LABEL_HIGH

    def test_medium_identity_plus_photo(self):
        label = compute_label({
            "identity_strong": True, "photo_ok": True, "price_available": False,
        })
        assert label == LABEL_MEDIUM

    def test_medium_identity_plus_price(self):
        label = compute_label({
            "identity_strong": True, "photo_ok": False, "price_available": True,
        })
        assert label == LABEL_MEDIUM

    def test_low_identity_only(self):
        label = compute_label({
            "identity_strong": True, "photo_ok": False, "price_available": False,
        })
        assert label == LABEL_LOW

    def test_low_photo_only(self):
        label = compute_label({
            "identity_strong": False, "photo_ok": True, "price_available": False,
        })
        assert label == LABEL_LOW

    def test_low_price_only(self):
        label = compute_label({
            "identity_strong": False, "photo_ok": False, "price_available": True,
        })
        assert label == LABEL_LOW

    def test_very_low_none(self):
        label = compute_label({
            "identity_strong": False, "photo_ok": False, "price_available": False,
        })
        assert label == LABEL_VERY_LOW

    def test_low_photo_and_price_without_identity(self):
        """Photo + price but no identity = LOW (not MEDIUM)."""
        label = compute_label({
            "identity_strong": False, "photo_ok": True, "price_available": True,
        })
        assert label == LABEL_LOW


# =============================================================================
# Evidence processing
# =============================================================================

class TestRecalculateConfidence:
    """Single evidence bundle processing."""

    def test_upgrade_very_low_to_medium(self):
        evidence = {
            "confidence": {"overall_label": "VERY_LOW"},
            "identity_level": "strong",
            "photo": {"verdict": "ACCEPT"},
            "price": {"price_status": "no_price_found"},
        }
        updated, new_label, old_label = recalculate_confidence(evidence)
        assert old_label == "VERY_LOW"
        assert new_label == LABEL_MEDIUM
        assert updated["confidence"]["overall_label"] == LABEL_MEDIUM
        assert updated["confidence"]["overall_label_prior"] == "VERY_LOW"
        assert updated["confidence"]["recalculated"] is True

    def test_upgrade_very_low_to_high(self):
        evidence = {
            "confidence": {"overall_label": "VERY_LOW"},
            "identity_level": "strong",
            "photo": {"verdict": "ACCEPT"},
            "price": {"price_status": "public_price"},
        }
        _, new_label, _ = recalculate_confidence(evidence)
        assert new_label == LABEL_HIGH

    def test_no_change_for_correct_label(self):
        evidence = {
            "confidence": {"overall_label": "VERY_LOW"},
            "identity_level": "weak",
            "photo": {"verdict": "REJECT"},
            "price": {"price_status": "no_price_found"},
        }
        _, new_label, old_label = recalculate_confidence(evidence)
        assert new_label == LABEL_VERY_LOW
        assert old_label == "VERY_LOW"

    def test_preserves_existing_confidence_fields(self):
        evidence = {
            "confidence": {"overall_label": "VERY_LOW", "score": 0.15},
            "identity_level": "strong",
            "photo": {"verdict": "ACCEPT"},
            "price": {"price_status": "no_price_found"},
        }
        updated, _, _ = recalculate_confidence(evidence)
        assert updated["confidence"]["score"] == 0.15  # preserved
        assert updated["confidence"]["overall_label"] == LABEL_MEDIUM

    def test_missing_confidence_object(self):
        evidence = {
            "identity_level": "strong",
            "photo": {"verdict": "ACCEPT"},
            "price": {"price_status": "public_price"},
        }
        updated, new_label, old_label = recalculate_confidence(evidence)
        assert old_label == LABEL_VERY_LOW  # default
        assert new_label == LABEL_HIGH
        assert "confidence" in updated


# =============================================================================
# Full pipeline
# =============================================================================

class TestFullPipeline:
    """End-to-end confidence recalculation."""

    def _write_evidence(self, evidence_dir, pn, **kwargs):
        defaults = {
            "confidence": {"overall_label": "VERY_LOW"},
            "identity_level": "weak",
            "photo": {"verdict": "REJECT"},
            "price": {"price_status": "no_price_found"},
        }
        defaults.update(kwargs)
        path = evidence_dir / f"evidence_{pn}.json"
        path.write_text(json.dumps(defaults), encoding="utf-8")

    def test_dry_run_no_modify(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        output_dir = tmp_path / "output"

        self._write_evidence(evidence_dir, "A001",
                             identity_level="strong",
                             photo={"verdict": "ACCEPT"})
        original = (evidence_dir / "evidence_A001.json").read_text(encoding="utf-8")

        report = run_recalculator(evidence_dir, output_dir, apply=False)

        after = (evidence_dir / "evidence_A001.json").read_text(encoding="utf-8")
        assert original == after
        assert report["upgraded"] == 1
        assert report["applied"] is False

    def test_apply_modifies_evidence(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        output_dir = tmp_path / "output"

        self._write_evidence(evidence_dir, "B001",
                             identity_level="strong",
                             photo={"verdict": "ACCEPT"},
                             price={"price_status": "public_price"})

        run_recalculator(evidence_dir, output_dir, apply=True)

        data = json.loads(
            (evidence_dir / "evidence_B001.json").read_text(encoding="utf-8"),
        )
        assert data["confidence"]["overall_label"] == LABEL_HIGH

    def test_distribution_tracking(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        output_dir = tmp_path / "output"

        # HIGH candidate
        self._write_evidence(evidence_dir, "C001",
                             identity_level="strong",
                             photo={"verdict": "ACCEPT"},
                             price={"price_status": "public_price"})
        # MEDIUM candidate
        self._write_evidence(evidence_dir, "C002",
                             identity_level="strong",
                             photo={"verdict": "ACCEPT"})
        # VERY_LOW stays
        self._write_evidence(evidence_dir, "C003")

        report = run_recalculator(evidence_dir, output_dir, apply=False)

        assert report["new_distribution"][LABEL_HIGH] == 1
        assert report["new_distribution"][LABEL_MEDIUM] == 1
        assert report["new_distribution"][LABEL_VERY_LOW] == 1

    def test_idempotent(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        output_dir = tmp_path / "output"

        self._write_evidence(evidence_dir, "D001",
                             identity_level="strong",
                             photo={"verdict": "ACCEPT"})

        run_recalculator(evidence_dir, output_dir, apply=True)
        report2 = run_recalculator(evidence_dir, output_dir, apply=True)

        assert report2["upgraded"] == 0
        assert report2["unchanged"] == 1

    def test_report_written(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        output_dir = tmp_path / "output"

        self._write_evidence(evidence_dir, "E001")

        run_recalculator(evidence_dir, output_dir, apply=False)

        assert (output_dir / "confidence_recalc_report.json").exists()

    def test_transitions_tracked(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        output_dir = tmp_path / "output"

        self._write_evidence(evidence_dir, "F001",
                             identity_level="strong",
                             photo={"verdict": "ACCEPT"})
        self._write_evidence(evidence_dir, "F002",
                             identity_level="strong",
                             photo={"verdict": "ACCEPT"})

        report = run_recalculator(evidence_dir, output_dir, apply=False)

        assert "VERY_LOW->MEDIUM" in report["transitions"]
        assert report["transitions"]["VERY_LOW->MEDIUM"] == 2

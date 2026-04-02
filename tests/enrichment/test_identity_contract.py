"""Tests for Phase A pn_secondary identity invariant."""
import sys
import os

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from identity_contract import build_identity_code_registry


class TestIdentityContract:

    def test_primary_is_identity_proof(self):
        registry = build_identity_code_registry("00020211")
        assert registry["identity_proof_codes"] == ["00020211"]

    def test_secondary_from_raw_input_never_auto_proof(self):
        registry = build_identity_code_registry(
            pn_primary="00020211",
            pn_secondary="SL22-020211-K6",
            secondary_source_role="raw_input",
        )
        assert registry["identity_proof_codes"] == ["00020211"]
        secondary = registry["code_records"][1]
        assert secondary["code_role"] == "typed_supporting_code"
        assert secondary["auto_identity_proof"] is False
        assert secondary["eligible_for_identity_proof"] is False

    def test_secondary_from_allowed_source_still_not_auto_proof(self):
        registry = build_identity_code_registry(
            pn_primary="00020211",
            pn_secondary="00020211-EU",
            secondary_source_role="authorized_distributor",
            secondary_source_ref="https://example.com/p",
        )
        assert registry["identity_proof_codes"] == ["00020211"]
        secondary = registry["code_records"][1]
        assert secondary["eligible_for_identity_proof"] is True
        assert secondary["policy_approved_for_identity"] is False

    def test_secondary_requires_explicit_policy_promotion(self):
        registry = build_identity_code_registry(
            pn_primary="00020211",
            pn_secondary="00020211-EU",
            secondary_source_role="authorized_distributor",
            secondary_source_ref="https://example.com/p",
            policy_allows_secondary_identity=True,
            secondary_identity_policy_rule_id="ICP-01",
        )
        assert registry["identity_proof_codes"] == ["00020211", "00020211-EU"]
        assert registry["secondary_identity_policy_rule_id"] == "ICP-01"
        assert registry["secondary_identity_source_ref"] == "https://example.com/p"
        assert registry["secondary_identity_decision_trace"] == {
            "code": "00020211-EU",
            "code_role": "typed_supporting_code",
            "secondary_source_role": "authorized_distributor",
            "secondary_identity_source_ref": "https://example.com/p",
            "eligible_for_identity_proof": True,
            "policy_allows_secondary_identity": True,
            "policy_approved_for_identity": True,
            "secondary_identity_policy_rule_id": "ICP-01",
        }

    def test_policy_approved_secondary_requires_rule_id(self):
        import pytest

        with pytest.raises(ValueError):
            build_identity_code_registry(
                pn_primary="00020211",
                pn_secondary="00020211-EU",
                secondary_source_role="authorized_distributor",
                secondary_source_ref="https://example.com/p",
                policy_allows_secondary_identity=True,
            )

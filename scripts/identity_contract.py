"""identity_contract.py - Phase A PN identity code-role contract."""
from __future__ import annotations

from dataclasses import asdict, dataclass

_SECONDARY_ELIGIBLE_SOURCE_ROLES = frozenset(
    {"manufacturer_proof", "official_pdf_proof", "authorized_distributor"}
)


@dataclass(frozen=True)
class CodeRecord:
    code: str
    code_role: str
    source_role: str
    source_ref: str
    auto_identity_proof: bool
    eligible_for_identity_proof: bool
    policy_approved_for_identity: bool

    def to_dict(self) -> dict:
        return asdict(self)


def build_identity_code_registry(
    pn_primary: str,
    pn_secondary: str = "",
    secondary_source_role: str = "raw_input",
    secondary_source_ref: str = "raw_input",
    policy_allows_secondary_identity: bool = False,
    secondary_identity_policy_rule_id: str = "",
) -> dict:
    """Build code-role registry with the Phase A pn_secondary invariant.

    Invariant:
    pn_secondary never becomes identity proof automatically. It may only become
    identity-participating if policy explicitly allows it.
    """
    records: list[CodeRecord] = [
        CodeRecord(
            code=pn_primary,
            code_role="pn_primary",
            source_role="identity_anchor",
            source_ref="primary_input",
            auto_identity_proof=True,
            eligible_for_identity_proof=True,
            policy_approved_for_identity=True,
        )
    ]
    identity_proof_codes = [pn_primary]
    secondary_identity_decision_trace: dict = {}
    secondary_identity_policy_rule = ""
    secondary_identity_source = secondary_source_ref if pn_secondary else ""

    if pn_secondary:
        eligible = secondary_source_role in _SECONDARY_ELIGIBLE_SOURCE_ROLES
        approved = bool(policy_allows_secondary_identity and eligible)
        if approved and not secondary_identity_policy_rule_id:
            raise ValueError(
                "secondary_identity_policy_rule_id is required when "
                "policy approves pn_secondary for identity"
            )
        records.append(
            CodeRecord(
                code=pn_secondary,
                code_role="typed_supporting_code",
                source_role=secondary_source_role,
                source_ref=secondary_source_ref,
                auto_identity_proof=False,
                eligible_for_identity_proof=eligible,
                policy_approved_for_identity=approved,
            )
        )
        secondary_identity_policy_rule = (
            secondary_identity_policy_rule_id if approved else ""
        )
        secondary_identity_decision_trace = {
            "code": pn_secondary,
            "code_role": "typed_supporting_code",
            "secondary_source_role": secondary_source_role,
            "secondary_identity_source_ref": secondary_source_ref,
            "eligible_for_identity_proof": eligible,
            "policy_allows_secondary_identity": bool(policy_allows_secondary_identity),
            "policy_approved_for_identity": approved,
            "secondary_identity_policy_rule_id": secondary_identity_policy_rule,
        }
        if approved:
            identity_proof_codes.append(pn_secondary)

    return {
        "pn_primary": pn_primary,
        "pn_secondary": pn_secondary or "",
        "identity_proof_codes": identity_proof_codes,
        "secondary_identity_policy_rule_id": secondary_identity_policy_rule,
        "secondary_identity_source_ref": secondary_identity_source,
        "secondary_identity_decision_trace": secondary_identity_decision_trace,
        "code_records": [record.to_dict() for record in records],
    }

"""candidate_lake.py - Candidate storage for Phase A enrichment contracts."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

_MAX_CANDIDATES_PER_FIELD: dict[str, int] = {
    "image": 10,
    "price": 10,
    "pdf": 5,
    "title": 5,
    "description": 5,
}
_MAX_CANDIDATES_PER_ROLE: dict[str, int] = {
    "manufacturer_proof": 8,
    "official_pdf_proof": 5,
    "authorized_distributor": 8,
    "industrial_distributor": 6,
    "organic_discovery": 4,
}
_MAX_TOTAL_CANDIDATES_PER_SKU = 24

_ROLE_RANK: dict[str, int] = {
    "manufacturer_proof": 5,
    "official_pdf_proof": 4,
    "authorized_distributor": 3,
    "industrial_distributor": 2,
    "organic_discovery": 1,
}


@dataclass
class Candidate:
    """Single candidate artifact with provenance and contract metadata."""

    candidate_type: str
    source_role: str
    source_url: str
    source_domain: str
    pn_match_strength: str
    value: Any
    publishable_candidate: bool = True
    rejection_reason: Optional[str] = None
    dedupe_key: str = field(default="")
    cross_pollination_detected: bool = False
    candidate_id: str = field(default="")
    field_type: str = field(default="")
    run_id: str = field(default="")
    extraction_method: str = field(default="")
    evidence_context: str = field(default="")
    identity_level: str = field(default="")

    def __post_init__(self) -> None:
        if not self.field_type:
            self.field_type = self.candidate_type
        if not self.dedupe_key:
            self.dedupe_key = _make_dedupe_key(
                self.candidate_type, self.source_domain, self.value
            )
        if not self.candidate_id:
            self.candidate_id = "cand_" + self.dedupe_key.split(":", 1)[1]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Candidate":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


def _make_dedupe_key(candidate_type: str, source_domain: str, value: Any) -> str:
    raw = (
        f"{candidate_type}|{source_domain}|"
        f"{json.dumps(value, sort_keys=True, ensure_ascii=False)}"
    )
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()[:16]


class CandidateLake:
    """Per-SKU candidate pool with deterministic write-time guardrails."""

    def __init__(self, pn: str) -> None:
        self.pn = pn
        self._candidates: list[Candidate] = []
        self._dedupe_keys: set[str] = set()

    def add(self, candidate: Candidate) -> bool:
        """Add candidate when dedupe and hard limits permit it."""
        if candidate.dedupe_key in self._dedupe_keys:
            logger.debug(
                "Dedupe skip: type=%s domain=%s",
                candidate.candidate_type,
                candidate.source_domain,
            )
            return False

        if len(self._candidates) >= _MAX_TOTAL_CANDIDATES_PER_SKU:
            logger.debug("Total capacity full for pn=%s", self.pn)
            return False

        field_limit = _MAX_CANDIDATES_PER_FIELD.get(candidate.field_type, 10)
        field_count = sum(1 for c in self._candidates if c.field_type == candidate.field_type)
        if field_count >= field_limit:
            logger.debug("Field capacity full: field=%s limit=%d", candidate.field_type, field_limit)
            return False

        role_limit = _MAX_CANDIDATES_PER_ROLE.get(candidate.source_role, 4)
        role_count = sum(1 for c in self._candidates if c.source_role == candidate.source_role)
        if role_count >= role_limit:
            logger.debug("Role capacity full: role=%s limit=%d", candidate.source_role, role_limit)
            return False

        self._dedupe_keys.add(candidate.dedupe_key)
        self._candidates.append(candidate)
        return True

    def get_publishable(self, candidate_type: Optional[str] = None) -> list[Candidate]:
        result = [c for c in self._candidates if c.publishable_candidate]
        if candidate_type:
            result = [c for c in result if c.candidate_type == candidate_type]
        return result

    def get_best(self, candidate_type: str) -> Optional[Candidate]:
        candidates = self.get_publishable(candidate_type)
        if not candidates:
            return None
        strength_rank = {"strong": 3, "medium": 2, "weak": 1}
        return max(
            candidates,
            key=lambda c: (
                _ROLE_RANK.get(c.source_role, 0),
                strength_rank.get(c.pn_match_strength, 0),
            ),
        )

    def all_candidates(self) -> list[Candidate]:
        return list(self._candidates)

    def stats(self) -> dict[str, Any]:
        total: dict[str, int] = {}
        publishable: dict[str, int] = {}
        by_role: dict[str, int] = {}
        for c in self._candidates:
            total[c.field_type] = total.get(c.field_type, 0) + 1
            by_role[c.source_role] = by_role.get(c.source_role, 0) + 1
            if c.publishable_candidate:
                publishable[c.field_type] = publishable.get(c.field_type, 0) + 1
        return {
            "total": total,
            "publishable": publishable,
            "by_role": by_role,
            "total_candidates": len(self._candidates),
        }

    def to_dict(self) -> dict:
        return {
            "pn": self.pn,
            "candidates": [c.to_dict() for c in self._candidates],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CandidateLake":
        lake = cls(pn=d["pn"])
        for cd in d.get("candidates", []):
            c = Candidate.from_dict(cd)
            lake._dedupe_keys.add(c.dedupe_key)
            lake._candidates.append(c)
        return lake

    def to_sidecar_rows(
        self,
        run_manifest_id: str,
        bundle_ref: str,
        decision_ref: str,
        schema_version: str = "candidate_sidecar_schema_v1",
    ) -> list[dict]:
        """Return queryable sidecar rows for audit/analytics/replay."""
        rows: list[dict] = []
        for candidate in self._candidates:
            rows.append(
                {
                    "schema_version": schema_version,
                    "run_manifest_id": run_manifest_id,
                    "bundle_ref": bundle_ref,
                    "decision_ref": decision_ref,
                    "pn_primary": self.pn,
                    "pn": self.pn,
                    "candidate_id": candidate.candidate_id,
                    "field_type": candidate.field_type,
                    "source_role": candidate.source_role,
                    "publishable_candidate": candidate.publishable_candidate,
                    "rejection_reason": candidate.rejection_reason,
                    "source_url": candidate.source_url,
                    "source_domain": candidate.source_domain,
                    "dedupe_key": candidate.dedupe_key,
                }
            )
        return rows

"""tests/enrichment/test_candidate_lake.py — Deterministic tests for CandidateLake.

No live API calls. No file I/O. Pure logic tests.
"""
import sys
import os

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

import pytest
from candidate_lake import (
    Candidate,
    CandidateLake,
    _MAX_CANDIDATES_PER_FIELD,
    _MAX_CANDIDATES_PER_ROLE,
    _MAX_TOTAL_CANDIDATES_PER_SKU,
    _make_dedupe_key,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make(
    candidate_type="image",
    source_role="authorized_distributor",
    source_url="https://rs-online.com/img/123.jpg",
    source_domain="rs-online.com",
    pn_match_strength="strong",
    value="https://rs-online.com/img/123.jpg",
    publishable_candidate=True,
    rejection_reason=None,
    cross_pollination_detected=False,
    run_id="",
    extraction_method="",
    evidence_context="",
    identity_level="",
) -> Candidate:
    return Candidate(
        candidate_type=candidate_type,
        source_role=source_role,
        source_url=source_url,
        source_domain=source_domain,
        pn_match_strength=pn_match_strength,
        value=value,
        publishable_candidate=publishable_candidate,
        rejection_reason=rejection_reason,
        cross_pollination_detected=cross_pollination_detected,
        run_id=run_id,
        extraction_method=extraction_method,
        evidence_context=evidence_context,
        identity_level=identity_level,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Candidate dataclass
# ══════════════════════════════════════════════════════════════════════════════

class TestCandidateDataclass:

    def test_dedupe_key_auto_generated(self):
        c = _make()
        assert c.dedupe_key.startswith("sha256:")
        assert c.candidate_id.startswith("cand_")

    def test_dedupe_key_stable(self):
        c1 = _make()
        c2 = _make()
        assert c1.dedupe_key == c2.dedupe_key

    def test_different_values_different_keys(self):
        c1 = _make(value="https://example.com/img1.jpg")
        c2 = _make(value="https://example.com/img2.jpg")
        assert c1.dedupe_key != c2.dedupe_key

    def test_to_dict_has_all_fields(self):
        d = _make().to_dict()
        required = [
            "candidate_id", "candidate_type", "field_type", "source_role", "source_url", "source_domain",
            "pn_match_strength", "value", "publishable_candidate",
            "rejection_reason", "dedupe_key", "cross_pollination_detected",
            "run_id", "extraction_method", "evidence_context", "identity_level",
        ]
        for key in required:
            assert key in d

    def test_from_dict_roundtrip(self):
        c = _make()
        restored = Candidate.from_dict(c.to_dict())
        assert restored.source_domain == c.source_domain
        assert restored.dedupe_key == c.dedupe_key


# ══════════════════════════════════════════════════════════════════════════════
# CandidateLake.add()
# ══════════════════════════════════════════════════════════════════════════════

class TestCandidateLakeAdd:

    def test_add_returns_true(self):
        lake = CandidateLake("00020211")
        assert lake.add(_make()) is True

    def test_duplicate_returns_false(self):
        lake = CandidateLake("00020211")
        c = _make()
        lake.add(c)
        assert lake.add(c) is False

    def test_capacity_limit_enforced(self):
        lake = CandidateLake("00020211")
        limit = _MAX_CANDIDATES_PER_FIELD["image"]
        roles = [
            "manufacturer_proof",
            "official_pdf_proof",
            "authorized_distributor",
            "industrial_distributor",
            "organic_discovery",
        ]
        for i in range(limit + 5):
            c = _make(
                source_role=roles[i % len(roles)],
                value=f"https://example.com/img{i}.jpg",
                source_url=f"https://example.com/p{i}",
                source_domain=f"example{i}.com",
            )
            lake.add(c)
        count = sum(1 for c in lake.all_candidates() if c.candidate_type == "image")
        assert count == limit

    def test_capacity_separate_per_type(self):
        """Image limit does not affect price limit."""
        lake = CandidateLake("00020211")
        img_limit = _MAX_CANDIDATES_PER_FIELD["image"]
        roles = [
            "manufacturer_proof",
            "official_pdf_proof",
            "authorized_distributor",
            "industrial_distributor",
            "organic_discovery",
        ]
        for i in range(img_limit):
            lake.add(_make(candidate_type="image",
                           source_role=roles[i % len(roles)],
                           source_domain=f"image{i}.example",
                           value=f"https://example.com/img{i}.jpg",
                           source_url=f"https://example.com/i{i}"))
        price_c = _make(candidate_type="price",
                        value={"amount": 9.99, "currency": "EUR"},
                        source_url="https://rs-online.com/price")
        assert lake.add(price_c) is True

    def test_cross_pollination_stored_not_publishable(self):
        """Cross-pollination candidate is stored (for audit) but excluded from publishable."""
        lake = CandidateLake("00020211")
        c = _make(
            cross_pollination_detected=True,
            publishable_candidate=False,
            rejection_reason="cross_pollination",
        )
        lake.add(c)
        assert len(lake.all_candidates()) == 1
        assert lake.get_publishable("image") == []

    def test_role_limit_enforced(self):
        lake = CandidateLake("00020211")
        limit = _MAX_CANDIDATES_PER_ROLE["organic_discovery"]
        for i in range(limit + 2):
            accepted = lake.add(
                _make(
                    source_role="organic_discovery",
                    source_domain=f"example{i}.com",
                    source_url=f"https://example{i}.com/p",
                    value=f"https://example{i}.com/img.jpg",
                )
            )
            if i < limit:
                assert accepted is True
            else:
                assert accepted is False

    def test_total_limit_enforced(self):
        lake = CandidateLake("00020211")
        roles = [
            "manufacturer_proof",
            "official_pdf_proof",
            "authorized_distributor",
            "industrial_distributor",
            "organic_discovery",
        ]
        for i in range(_MAX_TOTAL_CANDIDATES_PER_SKU):
            added = lake.add(
                _make(
                    candidate_type="image" if i < 10 else "price" if i < 20 else "title",
                    source_role=roles[i % len(roles)],
                    source_domain=f"example{i}.com",
                    source_url=f"https://example{i}.com/p",
                    value=f"value-{i}",
                )
            )
            assert added is True
        overflow = lake.add(
            _make(
                candidate_type="description",
                source_role="manufacturer_proof",
                source_domain="overflow.example",
                source_url="https://overflow.example/p",
                value="overflow",
            )
        )
        assert overflow is False


# ══════════════════════════════════════════════════════════════════════════════
# get_publishable / get_best
# ══════════════════════════════════════════════════════════════════════════════

class TestCandidateLakeQuery:

    def test_get_publishable_filters_unpublishable(self):
        lake = CandidateLake("00020211")
        lake.add(_make(publishable_candidate=True))
        lake.add(_make(
            publishable_candidate=False,
            rejection_reason="cross_pollination",
            value="https://example.com/other.jpg",
            source_url="https://example.com/other",
        ))
        assert len(lake.get_publishable("image")) == 1

    def test_get_best_returns_highest_role(self):
        lake = CandidateLake("00020211")
        lake.add(_make(source_role="authorized_distributor",
                       value="https://rs.com/img.jpg",
                       source_url="https://rs.com/p"))
        lake.add(_make(source_role="manufacturer_proof",
                       source_domain="honeywell.com",
                       value="https://honeywell.com/img.jpg",
                       source_url="https://honeywell.com/p"))
        best = lake.get_best("image")
        assert best is not None
        assert best.source_role == "manufacturer_proof"

    def test_get_best_none_when_empty(self):
        lake = CandidateLake("00020211")
        assert lake.get_best("image") is None

    def test_get_best_none_all_unpublishable(self):
        lake = CandidateLake("00020211")
        lake.add(_make(publishable_candidate=False, rejection_reason="cross_pollination"))
        assert lake.get_best("image") is None

    def test_get_publishable_by_type(self):
        lake = CandidateLake("00020211")
        lake.add(_make(candidate_type="image"))
        lake.add(_make(candidate_type="price",
                       value={"amount": 9.99, "currency": "EUR"},
                       source_url="https://rs-online.com/price"))
        assert len(lake.get_publishable("image")) == 1
        assert len(lake.get_publishable("price")) == 1
        assert len(lake.get_publishable()) == 2


# ══════════════════════════════════════════════════════════════════════════════
# Serialization roundtrip
# ══════════════════════════════════════════════════════════════════════════════

class TestCandidateLakeSerialization:

    def test_to_dict_from_dict_roundtrip(self):
        lake = CandidateLake("00020211")
        lake.add(_make())
        lake.add(_make(candidate_type="price",
                       value={"amount": 9.99, "currency": "EUR"},
                       source_url="https://rs-online.com/price"))
        d = lake.to_dict()
        restored = CandidateLake.from_dict(d)
        assert restored.pn == "00020211"
        assert len(restored.all_candidates()) == 2

    def test_roundtrip_preserves_dedupe(self):
        """After deserialization, adding the same candidate is still rejected."""
        lake = CandidateLake("00020211")
        c = _make()
        lake.add(c)
        restored = CandidateLake.from_dict(lake.to_dict())
        assert restored.add(c) is False

    def test_stats_structure(self):
        lake = CandidateLake("00020211")
        lake.add(_make())
        s = lake.stats()
        assert "total" in s
        assert "publishable" in s
        assert "by_role" in s
        assert s["total"]["image"] == 1

    def test_sidecar_rows_have_required_refs(self):
        lake = CandidateLake("00020211")
        lake.add(_make(run_id="run-1"))
        rows = lake.to_sidecar_rows(
            run_manifest_id="manifest-1",
            bundle_ref="evidence_00020211.json",
            decision_ref="dec_00020211",
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["schema_version"] == "candidate_sidecar_schema_v1"
        assert row["run_manifest_id"] == "manifest-1"
        assert row["bundle_ref"] == "evidence_00020211.json"
        assert row["decision_ref"] == "dec_00020211"
        assert row["pn_primary"] == "00020211"
        assert row["pn"] == "00020211"
        assert row["candidate_id"].startswith("cand_")

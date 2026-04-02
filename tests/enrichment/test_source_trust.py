"""tests/enrichment/test_source_trust.py — Deterministic tests for SourceTrustRegistry.

No live API calls. No file I/O beyond loading config JSON (which must exist).
"""
import sys
import os

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

import pytest
from source_trust import (
    get_source_role,
    get_trust_scores,
    is_denied,
    SourceTrustRegistry,
    load_source_role_field_matrix,
    get_field_role_policy,
)


# ══════════════════════════════════════════════════════════════════════════════
# get_source_role
# ══════════════════════════════════════════════════════════════════════════════

class TestGetSourceRole:

    def test_honeywell_is_manufacturer(self):
        assert get_source_role("honeywell.com") == "manufacturer_proof"

    def test_sps_honeywell_is_manufacturer(self):
        assert get_source_role("sps.honeywell.com") == "manufacturer_proof"

    def test_esser_is_manufacturer(self):
        assert get_source_role("esser-systems.com") == "manufacturer_proof"

    def test_rs_online_is_authorized(self):
        assert get_source_role("rs-online.com") == "authorized_distributor"

    def test_mouser_is_authorized(self):
        assert get_source_role("mouser.com") == "authorized_distributor"

    def test_tme_is_industrial(self):
        assert get_source_role("tme.eu") == "industrial_distributor"

    def test_unknown_domain_is_organic(self):
        assert get_source_role("unknown-site.example.com") == "organic_discovery"

    def test_url_www_prefix_stripped(self):
        assert get_source_role("www.honeywell.com") == "manufacturer_proof"

    def test_full_url_domain_extracted(self):
        role = get_source_role("https://www.honeywell.com/us/en/products/123")
        assert role == "manufacturer_proof"

    def test_rs_online_url_resolved(self):
        role = get_source_role("https://www.rs-online.com/web/p/smoke-detectors/123")
        assert role == "authorized_distributor"


# ══════════════════════════════════════════════════════════════════════════════
# is_denied
# ══════════════════════════════════════════════════════════════════════════════

class TestIsDenied:

    def test_aliexpress_denied(self):
        assert is_denied("aliexpress.com") is True

    def test_wish_denied(self):
        assert is_denied("wish.com") is True

    def test_honeywell_not_denied(self):
        assert is_denied("honeywell.com") is False

    def test_rs_online_not_denied(self):
        assert is_denied("rs-online.com") is False

    def test_unknown_not_denied(self):
        assert is_denied("random-unknown-shop.net") is False


# ══════════════════════════════════════════════════════════════════════════════
# get_trust_scores
# ══════════════════════════════════════════════════════════════════════════════

class TestGetTrustScores:

    def test_manufacturer_identity_high(self):
        scores = get_trust_scores("honeywell.com")
        assert scores["identity"] == "HIGH"

    def test_manufacturer_photo_high(self):
        scores = get_trust_scores("honeywell.com")
        assert scores["photo"] == "HIGH"

    def test_authorized_price_high(self):
        scores = get_trust_scores("rs-online.com")
        assert scores["price"] == "HIGH"

    def test_unknown_returns_all_keys(self):
        scores = get_trust_scores("unknown.com")
        assert all(k in scores for k in ("identity", "price", "photo", "pdf"))

    def test_industrial_identity_med(self):
        scores = get_trust_scores("tme.eu")
        assert scores["identity"] == "MED"


# ══════════════════════════════════════════════════════════════════════════════
# rate limit helpers
# ══════════════════════════════════════════════════════════════════════════════

class TestRateLimits:

    def test_large_distributor_delay_higher(self):
        reg = SourceTrustRegistry()
        delay_large = reg.get_delay_sec("rs-online.com")
        delay_normal = reg.get_delay_sec("tme.eu")
        assert delay_large >= delay_normal

    def test_default_delay_at_least_2(self):
        reg = SourceTrustRegistry()
        assert reg.get_delay_sec("unknown-domain.com") >= 2

    def test_domain_timeout_positive(self):
        reg = SourceTrustRegistry()
        assert reg.domain_timeout_sec() > 0


class TestSourceRoleFieldMatrix:

    def test_matrix_has_version(self):
        matrix = load_source_role_field_matrix()
        assert matrix["matrix_version"] == "source_role_field_matrix_v1"

    def test_authorized_identity_conditions_explicit(self):
        policy = get_field_role_policy("identity", "authorized_distributor")
        assert policy["admissible"] is True
        assert any("proof_context" in cond for cond in policy["conditions"])

    def test_industrial_price_conditions_explicit(self):
        policy = get_field_role_policy("price", "industrial_distributor")
        assert policy["admissible"] is True
        assert any("exact_product_page=true" in cond for cond in policy["conditions"])

    def test_distributor_pdf_conditions_explicit(self):
        policy = get_field_role_policy("pdf", "authorized_distributor")
        assert policy["admissible"] is True
        assert any("pdf_exact_pn_confirmed=true" in cond for cond in policy["conditions"])

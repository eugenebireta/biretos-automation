"""tests/enrichment/test_pn_variants.py — Deterministic tests for PN variant generation.

No live API calls. No file I/O. Pure logic tests.

Coverage:
  - generate_variants() — canonical + variants output
  - leading zeros stripping
  - separator swaps (dot↔dash, remove)
  - is_short_pn() guard
  - generate_variants_list() convenience wrapper
  - deduplication
  - canonical always first in all_queries()
"""
import sys
import os

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

import pytest
from pn_variants import generate_variants, generate_variants_list, is_short_pn, MIN_PN_LENGTH


# ══════════════════════════════════════════════════════════════════════════════
# is_short_pn
# ══════════════════════════════════════════════════════════════════════════════

class TestIsShortPn:

    def test_short_below_threshold(self):
        assert is_short_pn("123") is True

    def test_short_at_boundary(self):
        # MIN_PN_LENGTH - 1 → short
        short = "x" * (MIN_PN_LENGTH - 1)
        assert is_short_pn(short) is True

    def test_not_short_at_threshold(self):
        ok = "x" * MIN_PN_LENGTH
        assert is_short_pn(ok) is False

    def test_normal_pn_not_short(self):
        assert is_short_pn("00020211") is False

    def test_dotted_not_short(self):
        assert is_short_pn("027913.10") is False


# ══════════════════════════════════════════════════════════════════════════════
# generate_variants — leading zeros
# ══════════════════════════════════════════════════════════════════════════════

class TestLeadingZeros:

    def test_double_leading_zeros(self):
        v = generate_variants("00020211")
        assert v.pn_canonical == "00020211"
        assert "020211" in v.variants
        assert "20211" in v.variants
        assert v.has_leading_zeros is True

    def test_single_leading_zero(self):
        v = generate_variants("020211")
        assert "20211" in v.variants
        assert v.has_leading_zeros is True

    def test_no_leading_zero(self):
        v = generate_variants("1000106")
        assert v.has_leading_zeros is False
        # No zero-stripped variants
        assert "1000106" == v.pn_canonical

    def test_leading_zeros_on_dotted_when_starts_with_zero(self):
        # "010130.10" starts with '0' — leading zero IS stripped (for search hints)
        # The canonical is preserved; "10130.10" becomes a search variant
        v = generate_variants("010130.10")
        assert v.has_leading_zeros is True
        assert "10130.10" in v.variants
        # canonical must be preserved unchanged
        assert v.pn_canonical == "010130.10"

    def test_canonical_preserved_with_zeros(self):
        v = generate_variants("00020211")
        assert v.pn_canonical == "00020211"
        # canonical must not appear in variants
        assert "00020211" not in v.variants


# ══════════════════════════════════════════════════════════════════════════════
# generate_variants — separator swaps
# ══════════════════════════════════════════════════════════════════════════════

class TestSeparatorSwaps:

    def test_dot_to_dash(self):
        v = generate_variants("027913.10")
        assert "027913-10" in v.variants

    def test_remove_separators_dot(self):
        v = generate_variants("027913.10")
        assert "02791310" in v.variants

    def test_dash_to_dot(self):
        v = generate_variants("027913-10")
        assert "027913.10" in v.variants

    def test_remove_separators_dash(self):
        v = generate_variants("027913-10")
        assert "02791310" in v.variants

    def test_no_separator_no_variants(self):
        # Pure digits with no separators → only leading-zero variants possible
        v = generate_variants("1000106")
        for var in v.variants:
            assert var != "1000106"

    def test_alphanumeric_dash_to_dot(self):
        v = generate_variants("CCB01-010BT")
        assert "CCB01.010BT" in v.variants

    def test_alphanumeric_remove_separators(self):
        v = generate_variants("CCB01-010BT")
        assert "CCB01010BT" in v.variants


# ══════════════════════════════════════════════════════════════════════════════
# Deduplication and canonical-first ordering
# ══════════════════════════════════════════════════════════════════════════════

class TestDeduplicationAndOrder:

    def test_canonical_first_in_all_queries(self):
        v = generate_variants("027913.10")
        queries = v.all_queries()
        assert queries[0] == "027913.10"

    def test_no_duplicates_in_all_queries(self):
        v = generate_variants("027913.10")
        queries = v.all_queries()
        assert len(queries) == len(set(queries))

    def test_canonical_not_in_variants(self):
        for pn in ["027913.10", "00020211", "CCB01-010BT", "1000106"]:
            v = generate_variants(pn)
            assert pn not in v.variants, f"canonical {pn} should not be in variants"

    def test_all_queries_includes_canonical(self):
        v = generate_variants("027913-10")
        assert "027913-10" in v.all_queries()


# ══════════════════════════════════════════════════════════════════════════════
# as_dict output
# ══════════════════════════════════════════════════════════════════════════════

class TestAsDict:

    def test_as_dict_keys(self):
        v = generate_variants("027913.10")
        d = v.as_dict()
        assert "pn_canonical" in d
        assert "variants" in d
        assert "all_queries" in d
        assert "is_short" in d
        assert "has_leading_zeros" in d

    def test_as_dict_canonical_correct(self):
        v = generate_variants("027913.10")
        assert v.as_dict()["pn_canonical"] == "027913.10"


# ══════════════════════════════════════════════════════════════════════════════
# generate_variants_list convenience wrapper
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerateVariantsList:

    def test_returns_list(self):
        result = generate_variants_list("027913.10")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_canonical_first(self):
        result = generate_variants_list("027913.10")
        assert result[0] == "027913.10"

    def test_pure_digits_no_separator_variants(self):
        result = generate_variants_list("1000106")
        # Only canonical (no separators, no leading zeros)
        assert result == ["1000106"]


# ══════════════════════════════════════════════════════════════════════════════
# Short PN flag propagation
# ══════════════════════════════════════════════════════════════════════════════

class TestShortPnFlag:

    def test_short_pn_flagged(self):
        v = generate_variants("808")
        assert v.is_short is True

    def test_normal_pn_not_flagged(self):
        v = generate_variants("00020211")
        assert v.is_short is False

    def test_short_pn_still_gets_variants(self):
        # Short PN can still have variants (for search), just flagged
        v = generate_variants("0123")   # 4 chars < MIN_PN_LENGTH=5
        assert v.is_short is True
        # Should still produce stripped variant "123"
        assert "123" in v.variants

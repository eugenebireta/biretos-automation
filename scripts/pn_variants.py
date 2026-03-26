"""pn_variants.py — PN variant generation for search queries.

Canonical PN is preserved as-is for identity proof.
Variants are ONLY for broadening search queries — they are NOT equal to canonical PN.

Rules (applied in order, duplicates removed, canonical always first):
  1. Quoted exact form (canonical)          — highest-priority search query
  2. Remove leading zeros                   — "00020211" → "020211", "20211"
  3. Replace "." with "-"                   — "027913.10" → "027913-10"
  4. Replace "-" with "."                   — "027913-10" → "027913.10"
  5. Remove all separators ("." and "-")    — "027913.10" → "02791310"

Weight policy for matching:
  canonical (exact with zeros)  = 1.0  (strong identity proof)
  body match on canonical       = 0.5  (numeric body) / 0.9 (alphanum body)
  variant match                 = 0.3  (search hint only, NOT identity proof)

Minimum length guard:
  PNs shorter than MIN_PN_LENGTH are flagged as high-collision risk.
  They still get variants, but should be treated as REVIEW_REQUIRED by default.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MIN_PN_LENGTH: int = 5  # shorter → high collision risk

_LEADING_ZEROS_RE = re.compile(r"^(0+)(\d+)$")
_DOTTED_NUMERIC_RE = re.compile(r"^\d+\.\d+$")
_ALL_SEPARATORS_RE = re.compile(r"[.\-]")


def is_short_pn(pn: str) -> bool:
    """True if PN is below minimum safe length (high collision risk)."""
    return len(pn.strip()) < MIN_PN_LENGTH


def _strip_leading_zeros(pn: str) -> list[str]:
    """Return variants with progressively stripped leading zeros.

    "00020211" → ["020211", "20211"]
    "020211"   → ["20211"]
    "20211"    → []
    Only applies when PN is all-digits (no separators).
    """
    stripped = re.sub(r"[.\-]", "", pn)
    if not stripped.isdigit():
        return []
    variants: list[str] = []
    current = pn
    while current.startswith("0") and len(current) > 1:
        current = current[1:]
        if current and current not in (pn,):
            variants.append(current)
    return variants


def _dot_to_dash(pn: str) -> str | None:
    """Replace '.' with '-': '027913.10' → '027913-10'."""
    if "." in pn:
        return pn.replace(".", "-")
    return None


def _dash_to_dot(pn: str) -> str | None:
    """Replace '-' with '.': '027913-10' → '027913.10'."""
    if "-" in pn:
        return pn.replace("-", ".")
    return None


def _remove_separators(pn: str) -> str | None:
    """Remove all '.' and '-': '027913.10' → '02791310'."""
    result = _ALL_SEPARATORS_RE.sub("", pn)
    if result != pn:
        return result
    return None


@dataclass
class PNVariants:
    """Canonical PN with search variants and metadata."""

    pn_canonical: str
    variants: list[str] = field(default_factory=list)
    is_short: bool = False
    has_leading_zeros: bool = False

    def all_queries(self) -> list[str]:
        """All search query strings: canonical first, then variants.

        Returns deduplicated list preserving order.
        """
        seen: set[str] = set()
        result: list[str] = []
        for q in [self.pn_canonical] + self.variants:
            if q and q not in seen:
                seen.add(q)
                result.append(q)
        return result

    def as_dict(self) -> dict:
        return {
            "pn_canonical": self.pn_canonical,
            "variants": self.variants,
            "all_queries": self.all_queries(),
            "is_short": self.is_short,
            "has_leading_zeros": self.has_leading_zeros,
        }


def generate_variants(pn: str) -> PNVariants:
    """Generate search variants for a given PN.

    Always returns PNVariants with canonical first.
    Variants are for SEARCH ONLY — not for identity proof.

    Examples:
        "00020211"   → canonical + ["020211", "20211"]
        "027913.10"  → canonical + ["027913-10", "02791310"]
        "027913-10"  → canonical + ["027913.10", "02791310"]
        "1000106"    → canonical (pure digits, no separators, no leading zeros)
        "CCB01-010BT"→ canonical + ["CCB01.010BT", "CCB01010BT"]
    """
    pn = pn.strip()
    result = PNVariants(pn_canonical=pn)
    result.is_short = is_short_pn(pn)

    variants: list[str] = []

    # Leading zeros (pure digits only)
    zeros = _strip_leading_zeros(pn)
    if zeros:
        variants.extend(zeros)
        result.has_leading_zeros = True

    # Separator swaps
    d2dash = _dot_to_dash(pn)
    if d2dash:
        variants.append(d2dash)

    dash2d = _dash_to_dot(pn)
    if dash2d:
        variants.append(dash2d)

    # Remove all separators
    no_sep = _remove_separators(pn)
    if no_sep:
        variants.append(no_sep)

    # Deduplicate, exclude canonical
    seen: set[str] = {pn}
    result.variants = [v for v in variants if v not in seen and not seen.add(v)]  # type: ignore[func-returns-value]

    return result


def generate_variants_list(pn: str) -> list[str]:
    """Convenience: return all_queries() for a PN (canonical first)."""
    return generate_variants(pn).all_queries()

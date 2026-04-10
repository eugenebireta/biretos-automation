"""category_resolver.py — Resolve product category with source-strength awareness.

Design: xlsx category = hint, NOT ground truth.
A trusted page (tier1/tier2 + exact PN confirmed) can override the xlsx hint.
An untrusted page + conflict → hint_conflicted (not auto-resolved).
Weak page evidence → xlsx hint stays.

Usage:
    from category_resolver import resolve_category, CategoryResult
    result = resolve_category(
        xlsx_hint="Электрические переключатели",
        page_category="Safety Equipment",
        source_tier=1,
        exact_pn_confirmed=True,
    )
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

# ── Category synonyms / normalisation ────────────────────────────────────────

_CATEGORY_SYNONYMS: dict[str, list[str]] = {
    "Электрические переключатели": ["switch", "switches", "выключатель", "переключатель"],
    "Термостаты": ["thermostat", "термостат", "temperature controller"],
    "Датчики": ["sensor", "датчик", "detector"],
    "Пожарная безопасность": ["fire", "smoke", "пожар", "fire detection"],
    "Клапаны": ["valve", "клапан"],
    "Электроустановочные изделия": ["electrical accessories", "socket", "розетка", "рамка", "frame"],
    "Средства индивидуальной защиты": ["ppe", "safety", "protection", "еarmuff", "earmuff", "glove"],
}


def _categories_match(cat1: Optional[str], cat2: Optional[str]) -> bool:
    """True if two category strings are semantically the same."""
    if not cat1 or not cat2:
        return False
    c1 = cat1.strip().lower()
    c2 = cat2.strip().lower()
    if c1 == c2:
        return True
    # Check synonym groups
    for _, synonyms in _CATEGORY_SYNONYMS.items():
        if any(s.lower() in c1 for s in synonyms) and any(s.lower() in c2 for s in synonyms):
            return True
    return False


@dataclass
class CategoryResult:
    resolved_category: Optional[str]      # Final category to use
    resolution_method: str                 # how it was resolved
    xlsx_hint: Optional[str]               # original xlsx value
    page_category: Optional[str]           # value from page
    conflict: bool = False                 # True if hint and page disagree
    conflict_reason: str = ""
    confidence: str = "low"               # "high" | "medium" | "low"

    # resolution_method values:
    # "xlsx_hint"           — kept xlsx hint (default / no override)
    # "page_override"       — trusted page overrode xlsx hint
    # "hint_conflicted"     — conflict detected, not resolved
    # "page_confirmed"      — page confirmed xlsx hint
    # "no_data"             — no data available


def resolve_category(
    xlsx_hint: Optional[str],
    page_category: Optional[str],
    source_tier: int,         # 1=manufacturer, 2=trusted distributor, 0=other
    exact_pn_confirmed: bool, # PN matched exactly on this page
    brand_match: bool = True,  # brand appears on this page
) -> CategoryResult:
    """Resolve product category from xlsx hint and page evidence.

    Rules (in order):
    1. No data at all → no_data/low
    2. Page only (no xlsx hint) → page_override if tier1/tier2+pn_confirmed, else no_data
    3. Xlsx hint only → xlsx_hint/medium (hint stays)
    4. Both present + match → page_confirmed/high
    5. Both present + conflict:
       a. Trusted page (tier1/2 + exact_pn) → page_override/medium
       b. Untrusted or not exact → hint_conflicted/low (do not auto-resolve)
    """
    has_xlsx = bool(xlsx_hint and xlsx_hint.strip())
    has_page = bool(page_category and page_category.strip())

    if not has_xlsx and not has_page:
        return CategoryResult(
            resolved_category=None, resolution_method="no_data",
            xlsx_hint=xlsx_hint, page_category=page_category, confidence="low",
        )

    if has_xlsx and not has_page:
        return CategoryResult(
            resolved_category=xlsx_hint, resolution_method="xlsx_hint",
            xlsx_hint=xlsx_hint, page_category=page_category, confidence="medium",
        )

    if not has_xlsx and has_page:
        if source_tier in (1, 2) and exact_pn_confirmed:
            return CategoryResult(
                resolved_category=page_category, resolution_method="page_override",
                xlsx_hint=xlsx_hint, page_category=page_category, confidence="high",
            )
        return CategoryResult(
            resolved_category=None, resolution_method="no_data",
            xlsx_hint=xlsx_hint, page_category=page_category, confidence="low",
        )

    # Both present
    if _categories_match(xlsx_hint, page_category):
        return CategoryResult(
            resolved_category=xlsx_hint,  # prefer xlsx form
            resolution_method="page_confirmed",
            xlsx_hint=xlsx_hint, page_category=page_category, confidence="high",
        )

    # Conflict
    trusted_page = source_tier in (1, 2) and exact_pn_confirmed and brand_match
    if trusted_page:
        return CategoryResult(
            resolved_category=page_category,
            resolution_method="page_override",
            xlsx_hint=xlsx_hint, page_category=page_category,
            conflict=True,
            conflict_reason=f"tier{source_tier}_pn_confirmed",
            confidence="medium",
        )

    return CategoryResult(
        resolved_category=xlsx_hint,  # keep hint when untrusted conflict
        resolution_method="hint_conflicted",
        xlsx_hint=xlsx_hint, page_category=page_category,
        conflict=True,
        conflict_reason=f"tier{source_tier}_not_exact" if not exact_pn_confirmed else "not_trusted_source",
        confidence="low",
    )


if __name__ == "__main__":
    cases = [
        ("Электрические переключатели", "switch", 1, True),
        ("Датчики", "Safety Equipment", 2, True),
        ("Термостаты", "thermostat accessories", 0, False),
        ("Клапаны", "valve", 1, False),
        (None, "Safety Equipment", 1, True),
        ("Датчики", None, 0, False),
        (None, None, 0, False),
    ]
    print("Category resolution tests:")
    for xlsx, page, tier, pn_confirmed in cases:
        result = resolve_category(xlsx, page, tier, pn_confirmed)
        print(f"  xlsx={xlsx!r:35s} page={page!r:25s} tier={tier} pn={pn_confirmed!r:5}")
        print(f"    -> {result.resolution_method:20s} resolved={result.resolved_category!r} conf={result.confidence}")

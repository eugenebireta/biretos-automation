"""research_merge_gate.py — Source-aware merge contract for research results.

Contract: merge decisions are based on SOURCE URLs/DOMAINS, not provider names.
The same URL from Gemini and Claude is one source — not two independent confirmations.

Source types (by trust level):
- manufacturer: honeywell.com, peha.de, etc.          → tier1
- authorized_distributor: rs-online.com, farnell.com  → tier2
- general_distributor: other distributors             → tier3
- marketplace: amazon, ebay, etc.                     → tier4 (low trust)
- datasheet_repo: alldatasheet.com, etc.              → tier5 (spec only)
- unknown: unlisted domains                           → tier0

Merge rules:
- Two results pointing to the SAME domain = 1 source (dedup by domain)
- Min 2 distinct tier1/tier2 sources → CONFIRMED
- 1 tier1 source → PROBABLE (strong, not confirmed)
- 1 tier2 + 1 tier3 → PROBABLE/medium
- tier3/tier4 only → UNCONFIRMED
- Any conflict between sources → CONFLICT (do not auto-merge)

Status: STUB implementation — returns "pending_pilot".
Full implementation after pilot completes and we see real multi-source data.

Usage:
    from research_merge_gate import merge_research_results, MergeResult
    result = merge_research_results(results_list)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# ── Domain classification ─────────────────────────────────────────────────────

_TIER1_DOMAINS = frozenset({
    "honeywell.com", "honeywellsensing.com", "honeywellstore.com",
    "honeywell-safety.com", "honeywellsafety.com",
    "peha.de", "peha.com",
    "abb.com", "siemens.com", "schneider-electric.com",
})

_TIER2_DOMAINS = frozenset({
    "rs-components.com", "rs-online.com", "farnell.com", "digikey.com",
    "mouser.com", "element14.com", "arrow.com", "avnet.com",
    "elec.ru", "chipdip.ru", "contrel.ru", "datchik.ru",
    "etm.ru", "iek.ru", "tdm-electro.ru",
})

_MARKETPLACE_DOMAINS = frozenset({
    "amazon.com", "ebay.com", "aliexpress.com", "ozon.ru", "wildberries.ru",
})

_DATASHEET_REPO_DOMAINS = frozenset({
    "alldatasheet.com", "datasheetspdf.com", "datasheetarchive.com",
    "datasheet4u.com", "manualslib.com",
})


def _classify_domain(domain: str) -> tuple[int, str]:
    """Return (tier, source_type) for a domain."""
    domain = domain.lower()
    for d in _TIER1_DOMAINS:
        if domain.endswith(d):
            return 1, "manufacturer"
    for d in _TIER2_DOMAINS:
        if domain.endswith(d):
            return 2, "authorized_distributor"
    for d in _MARKETPLACE_DOMAINS:
        if domain.endswith(d):
            return 4, "marketplace"
    for d in _DATASHEET_REPO_DOMAINS:
        if domain.endswith(d):
            return 5, "datasheet_repo"
    return 3, "general_distributor"


def _extract_domain(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1).lower() if m else ""


@dataclass
class ResearchResult:
    """A single research result from any provider."""
    provider: str               # "gemini", "claude", "manual", etc.
    source_url: Optional[str]   # URL of the source page
    pn_confirmed: bool = False
    product_name: Optional[str] = None
    price_rub: Optional[float] = None
    image_url: Optional[str] = None
    datasheet_url: Optional[str] = None
    confidence: str = "low"    # "high" | "medium" | "low"
    raw: Optional[dict] = None


@dataclass
class MergeResult:
    """Merged verdict from multiple research results."""
    merge_status: str           # "confirmed"|"probable"|"unconfirmed"|"conflict"|"pending_pilot"|"no_data"
    pn_confirmed: bool = False
    product_name: Optional[str] = None
    price_rub: Optional[float] = None
    image_url: Optional[str] = None
    datasheet_url: Optional[str] = None
    confidence: str = "low"
    source_count: int = 0
    distinct_domains: list[str] = field(default_factory=list)
    min_tier: int = 99          # lowest (best) tier among sources
    conflict_fields: list[str] = field(default_factory=list)
    merge_reason: str = ""


def _deduplicate_by_domain(results: list[ResearchResult]) -> list[tuple[ResearchResult, str, int, str]]:
    """Dedup results by domain. Returns [(result, domain, tier, source_type)]."""
    seen_domains: dict[str, ResearchResult] = {}
    for r in results:
        domain = _extract_domain(r.source_url or "")
        if domain and domain not in seen_domains:
            seen_domains[domain] = r

    deduped = []
    for domain, result in seen_domains.items():
        tier, source_type = _classify_domain(domain)
        deduped.append((result, domain, tier, source_type))

    return deduped


def _detect_conflicts(results: list[ResearchResult]) -> list[str]:
    """Detect conflicting fields across results."""
    conflicts = []
    if len(results) < 2:
        return []

    # Check price conflicts (>20% difference)
    prices = [r.price_rub for r in results if r.price_rub]
    if len(prices) >= 2:
        p_min, p_max = min(prices), max(prices)
        if p_max > 0 and (p_max - p_min) / p_max > 0.20:
            conflicts.append("price_conflict")

    # Check pn_confirmed conflicts
    confirmations = [r.pn_confirmed for r in results]
    if True in confirmations and False in confirmations:
        conflicts.append("pn_confirmation_conflict")

    return conflicts


def merge_research_results(results: list[ResearchResult]) -> MergeResult:
    """Merge multiple research results into a single verdict.

    STATUS: STUB — returns pending_pilot for non-trivial cases.
    Full implementation after pilot data shows real multi-source patterns.
    """
    if not results:
        return MergeResult(merge_status="no_data", merge_reason="no_results")

    # Simple cases: single result
    if len(results) == 1:
        r = results[0]
        domain = _extract_domain(r.source_url or "")
        tier, _ = _classify_domain(domain)
        status = "probable" if tier <= 2 and r.pn_confirmed else "unconfirmed"
        return MergeResult(
            merge_status=status,
            pn_confirmed=r.pn_confirmed,
            product_name=r.product_name,
            price_rub=r.price_rub,
            image_url=r.image_url,
            datasheet_url=r.datasheet_url,
            confidence=r.confidence,
            source_count=1,
            distinct_domains=[domain] if domain else [],
            min_tier=tier,
            merge_reason="single_source",
        )

    # Multi-source: STUB for pilot
    # TODO: implement full multi-source merge after pilot data available
    deduped = _deduplicate_by_domain(results)
    conflicts = _detect_conflicts(results)
    domains = [d for _, d, _, _ in deduped]
    min_tier = min((t for _, _, t, _ in deduped), default=99)

    if conflicts:
        return MergeResult(
            merge_status="conflict",
            source_count=len(deduped),
            distinct_domains=domains,
            min_tier=min_tier,
            conflict_fields=conflicts,
            merge_reason="conflict_detected_stub",
        )

    # Return pending_pilot for multi-source cases without conflict
    # Will be replaced with full merge logic after pilot
    return MergeResult(
        merge_status="pending_pilot",
        source_count=len(deduped),
        distinct_domains=domains,
        min_tier=min_tier,
        merge_reason="multi_source_stub_pending_pilot",
    )


if __name__ == "__main__":
    # Smoke test
    results = [
        ResearchResult("gemini", "https://www.honeywell.com/product/153711", pn_confirmed=True, price_rub=4500.0, confidence="high"),
        ResearchResult("claude", "https://www.rs-online.com/product/153711", pn_confirmed=True, price_rub=4800.0, confidence="medium"),
    ]
    merged = merge_research_results(results)
    print(f"Multi-source merge: status={merged.merge_status} domains={merged.distinct_domains} min_tier={merged.min_tier}")

    single = [ResearchResult("gemini", "https://www.honeywell.com/product/153711", pn_confirmed=True, confidence="high")]
    merged_single = merge_research_results(single)
    print(f"Single-source merge: status={merged_single.merge_status} min_tier={merged_single.min_tier}")

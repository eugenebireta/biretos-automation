"""page_ranker.py — Rank candidate URLs for enrichment pipeline.

Primary: Gemini Flash ranking (single call for all candidates).
Fallback: Deterministic ranking (domain tiering, PN-in-URL/title, reject home/category).

Designed to integrate after SerpAPI results and before download/extraction.
The fallback is NOT "return all" — it filters and scores safely.

Usage:
    from page_ranker import rank_candidates, PageCandidate

    ranked = rank_candidates(pn, brand, candidates, use_gemini=True)
    top = ranked[:5]  # take top 5 URLs
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# ── Domain tiers ─────────────────────────────────────────────────────────────

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

_REJECT_PATH_PATTERNS = [
    re.compile(r"/category[/\-]", re.IGNORECASE),
    re.compile(r"/catalog[/\-]$", re.IGNORECASE),
    re.compile(r"/search[/\?]", re.IGNORECASE),
    re.compile(r"/blog[/\-]", re.IGNORECASE),
    re.compile(r"/$"),  # bare domain root
    re.compile(r"/tag[/\-]", re.IGNORECASE),
    re.compile(r"/news[/\-]", re.IGNORECASE),
    re.compile(r"/index\.html?$", re.IGNORECASE),
]


@dataclass
class PageCandidate:
    url: str
    title: str = ""
    snippet: str = ""
    domain: str = ""
    # Filled by rank_candidates
    score: float = 0.0
    rank_reason: str = ""
    rejected: bool = False
    reject_reason: str = ""


def _extract_domain(url: str) -> str:
    """Extract bare domain from URL."""
    m = re.match(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1).lower() if m else ""


def _pn_in_url(pn: str, url: str) -> bool:
    """True if PN appears in the URL path (word-boundary)."""
    safe_pn = re.escape(pn)
    return bool(re.search(r"(?<![A-Za-z0-9])" + safe_pn + r"(?![A-Za-z0-9])", url or "", re.IGNORECASE))


def _pn_in_text(pn: str, text: str) -> bool:
    """True if PN appears in title/snippet (word-boundary)."""
    safe_pn = re.escape(pn)
    return bool(re.search(r"(?<![A-Za-z0-9])" + safe_pn + r"(?![A-Za-z0-9])", text or "", re.IGNORECASE))


def _is_reject_path(url: str) -> bool:
    """True if URL looks like a category/search/blog/home page."""
    path = re.sub(r"^https?://[^/]+", "", url or "")
    return any(p.search(path) for p in _REJECT_PATH_PATTERNS)


def _domain_tier(domain: str) -> int:
    """Return 1 (manufacturer), 2 (trusted distributor), or 0 (other)."""
    for tier1 in _TIER1_DOMAINS:
        if domain.endswith(tier1):
            return 1
    for tier2 in _TIER2_DOMAINS:
        if domain.endswith(tier2):
            return 2
    return 0


def _deterministic_score(pn: str, brand: str, candidate: PageCandidate) -> tuple[float, str]:
    """Score a candidate URL deterministically. Returns (score, reason)."""
    url = candidate.url or ""
    title = candidate.title or ""
    snippet = candidate.snippet or ""
    domain = candidate.domain or _extract_domain(url)

    if _is_reject_path(url):
        return -1.0, "rejected_path_pattern"

    score = 0.0
    reasons = []

    tier = _domain_tier(domain)
    if tier == 1:
        score += 50.0
        reasons.append("tier1_domain")
    elif tier == 2:
        score += 30.0
        reasons.append("tier2_domain")
    else:
        score += 5.0

    if _pn_in_url(pn, url):
        score += 20.0
        reasons.append("pn_in_url")

    if _pn_in_text(pn, title):
        score += 15.0
        reasons.append("pn_in_title")

    if _pn_in_text(pn, snippet):
        score += 8.0
        reasons.append("pn_in_snippet")

    if brand and brand.lower() in (title + " " + snippet).lower():
        score += 5.0
        reasons.append("brand_in_text")

    return score, ",".join(reasons) if reasons else "no_signals"


def rank_candidates_deterministic(
    pn: str,
    brand: str,
    candidates: list[PageCandidate],
) -> list[PageCandidate]:
    """Rank candidates without any API calls. Safe fallback."""
    results = []
    for c in candidates:
        if not c.domain:
            c.domain = _extract_domain(c.url)
        score, reason = _deterministic_score(pn, brand, c)
        c.score = score
        c.rank_reason = reason
        if score < 0:
            c.rejected = True
            c.reject_reason = reason
        results.append(c)

    results.sort(key=lambda x: (not x.rejected, x.score), reverse=False)
    results.sort(key=lambda x: x.rejected)
    results.sort(key=lambda x: x.score, reverse=True)
    return results


def rank_candidates_gemini(
    pn: str,
    brand: str,
    candidates: list[PageCandidate],
    api_key: str = "",
) -> list[PageCandidate]:
    """Rank candidates using Gemini Flash. Falls back to deterministic on failure."""
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        log.warning("page_ranker: no GEMINI_API_KEY, using deterministic fallback")
        return rank_candidates_deterministic(pn, brand, candidates)

    try:
        import google.genai as genai
        client = genai.Client(api_key=api_key)

        candidate_list = "\n".join(
            f"{i+1}. URL: {c.url}\n   Title: {c.title}\n   Snippet: {c.snippet}"
            for i, c in enumerate(candidates)
        )
        prompt = (
            f"You are ranking product pages for part number '{pn}' (brand: {brand}).\n"
            f"Return a JSON array of URL indices sorted by relevance (best first).\n"
            f"Reject category/search/blog pages (score -1). Score exact product pages highest.\n\n"
            f"Candidates:\n{candidate_list}\n\n"
            f"Return ONLY: {{\"ranked\": [1,3,2,...], \"rejected\": [4,5]}}"
        )
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        import json, re as _re
        text = response.text or ""
        m = _re.search(r"\{.*\}", text, _re.DOTALL)
        if m:
            data = json.loads(m.group())
            ranked_indices = [i - 1 for i in (data.get("ranked") or []) if 1 <= i <= len(candidates)]
            rejected_indices = set(i - 1 for i in (data.get("rejected") or []) if 1 <= i <= len(candidates))

            result = []
            seen = set()
            for idx in ranked_indices:
                if idx not in seen:
                    c = candidates[idx]
                    c.score = len(ranked_indices) - list(ranked_indices).index(idx)
                    c.rank_reason = "gemini_ranked"
                    if idx in rejected_indices:
                        c.rejected = True
                        c.reject_reason = "gemini_rejected"
                    result.append(c)
                    seen.add(idx)
            # Add any not in ranked list
            for i, c in enumerate(candidates):
                if i not in seen:
                    c.score = 0.0
                    c.rank_reason = "gemini_unranked"
                    result.append(c)
            return result

    except Exception as exc:
        log.warning(f"page_ranker: Gemini ranking failed ({exc}), using deterministic fallback")

    return rank_candidates_deterministic(pn, brand, candidates)


def rank_candidates(
    pn: str,
    brand: str,
    candidates: list[PageCandidate],
    use_gemini: bool = True,
    api_key: str = "",
) -> list[PageCandidate]:
    """Rank and filter candidate URLs for enrichment.

    Args:
        pn: Product number to search for.
        brand: Brand name for context.
        candidates: List of PageCandidate objects.
        use_gemini: If True, try Gemini Flash first; fall back to deterministic.
        api_key: Gemini API key (defaults to GEMINI_API_KEY env var).

    Returns:
        Sorted candidates, rejected items last (rejected=True).
    """
    for c in candidates:
        if not c.domain:
            c.domain = _extract_domain(c.url)

    if use_gemini:
        return rank_candidates_gemini(pn, brand, candidates, api_key=api_key)
    return rank_candidates_deterministic(pn, brand, candidates)


if __name__ == "__main__":
    # Quick smoke test
    test_candidates = [
        PageCandidate(url="https://www.honeywell.com/us/en/products/safety/153711", title="Honeywell 153711", snippet="Part number 153711"),
        PageCandidate(url="https://www.rs-online.com/search?q=153711", title="Search Results", snippet="153711"),
        PageCandidate(url="https://www.etm.ru/cat/nn/153711", title="153711 ETM", snippet="Артикул 153711"),
        PageCandidate(url="https://www.somesite.com/category/safety", title="Safety Category", snippet="Products"),
    ]
    ranked = rank_candidates("153711", "Honeywell", test_candidates, use_gemini=False)
    print("Deterministic ranking:")
    for r in ranked:
        print(f"  score={r.score:.1f} rejected={r.rejected} reason={r.rank_reason} url={r.url[:60]}")

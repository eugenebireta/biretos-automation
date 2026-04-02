"""search_orchestrator.py — Manufacturer-first waterfall search.

Waterfall stages per SKU:
  1. Manufacturer exact       — site:mfr.com "PN"
  2. Authorized distributors  — site:dist.com "PN"
  3. PDF-targeted             — filetype:pdf "PN" brand
  4. Broader fallback         — "PN" brand

Early-stop rule: if any stage yields a result from manufacturer_proof or
official_pdf_proof, stop and return — no need to continue the waterfall.

Per-SKU budget:
  max_search_requests = 12
  max_pdf_queries     = 4
  max_image_queries   = 6  (reserved for Phase B image search)

Rate limiting: per-domain min delay (2s default, 3s for large distributors).
Exponential backoff on 429/503: 2s → 4s → 8s → skip.
Domain failover: after 3 consecutive failures, degrade to organic_discovery.
Query cache: skip identical queries within one SKU.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from serpapi import GoogleSearch as _GoogleSearch
    _SERPAPI_AVAILABLE = True
except ImportError:
    _SERPAPI_AVAILABLE = False
    logger.debug("serpapi not installed — SearchOrchestrator operates in stub mode")

from source_trust import SourceTrustRegistry, _CONFIG_PATH

_SERPAPI_KEY_ENV = "SERPAPI_KEY"

_DEFAULT_MAX_SEARCH = 12
_DEFAULT_MAX_PDF = 4
_DEFAULT_MAX_IMAGE = 6


@dataclass
class SearchResult:
    """Single organic search result with provenance metadata."""
    url: str
    title: str
    snippet: str
    source_domain: str
    source_role: str
    result_type: str = "organic"   # organic | pdf | image


@dataclass
class _DomainState:
    fail_count: int = 0
    degraded: bool = False
    last_request_at: float = 0.0


class SearchOrchestrator:
    """Manufacturer-first waterfall search with budget, rate limiting, failover."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        max_search: int = _DEFAULT_MAX_SEARCH,
        max_pdf: int = _DEFAULT_MAX_PDF,
        max_image: int = _DEFAULT_MAX_IMAGE,
        trust_registry: Optional[SourceTrustRegistry] = None,
    ) -> None:
        self._api_key = api_key or os.environ.get(_SERPAPI_KEY_ENV, "")
        self._max_search = max_search
        self._max_pdf = max_pdf
        self._max_image = max_image
        self._registry = trust_registry or SourceTrustRegistry()
        self._domain_states: dict[str, _DomainState] = {}
        # Per-SKU state (reset by reset_budget)
        self._query_cache: set[str] = set()
        self._search_count = 0
        self._pdf_count = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def reset_budget(self) -> None:
        """Reset per-SKU counters. Must be called before each new SKU."""
        self._search_count = 0
        self._pdf_count = 0
        self._query_cache.clear()

    def search(
        self,
        pn: str,
        brand: str,
        manufacturer_domains: Optional[list[str]] = None,
        authorized_domains: Optional[list[str]] = None,
        subbrand: str = "",
    ) -> list[SearchResult]:
        """Run waterfall search for one SKU. Returns all collected results."""
        self.reset_budget()

        mfr_domains = manufacturer_domains or self._registry.get_manufacturer_domains()
        auth_domains = authorized_domains or self._registry.get_authorized_domains()

        all_results: list[SearchResult] = []

        # Stage 1: manufacturer-first
        for domain in mfr_domains:
            if self._budget_exhausted():
                break
            if self._domain_states.get(domain, _DomainState()).degraded:
                logger.info("Manufacturer domain %s degraded — skipping", domain)
                continue
            results = self._do_query(f'site:{domain} "{pn}"', domain)
            all_results.extend(results)
            if _has_strong_evidence(results):
                logger.info("Strong evidence at stage 1 (%s) — stopping waterfall", domain)
                return all_results

        # Stage 2: authorized distributors
        for domain in auth_domains:
            if self._budget_exhausted():
                break
            results = self._do_query(f'site:{domain} "{pn}"', domain)
            all_results.extend(results)
            if _has_strong_evidence(results):
                logger.info("Strong evidence at stage 2 (%s) — stopping waterfall", domain)
                return all_results

        # Stage 3: PDF-targeted
        if self._pdf_count < self._max_pdf and not self._budget_exhausted():
            results = self._do_query(f'filetype:pdf "{pn}" {brand}', "", result_type="pdf")
            self._pdf_count += 1
            all_results.extend(results)

        # Stage 4: broader fallback
        if not self._budget_exhausted():
            term = subbrand if subbrand else brand
            all_results.extend(self._do_query(f'"{pn}" {term}', ""))

        return all_results

    # ── Internal ──────────────────────────────────────────────────────────────

    def _do_query(
        self,
        query: str,
        hint_domain: str,
        result_type: str = "organic",
    ) -> list[SearchResult]:
        if query in self._query_cache:
            return []
        if self._budget_exhausted():
            return []

        self._query_cache.add(query)
        self._apply_rate_limit(hint_domain)

        raw = self._call_serpapi(query)
        self._search_count += 1

        if raw is None:
            self._record_failure(hint_domain)
            return []

        self._reset_failures(hint_domain)
        return self._parse_results(raw, result_type)

    def _call_serpapi(self, query: str) -> Optional[list[dict]]:
        if not _SERPAPI_AVAILABLE or not self._api_key:
            logger.debug("SerpAPI stub (no key or not installed): %s", query)
            return []

        backoff = self._registry._rate_limits.get("backoff_sequence_sec", [2, 4, 8])
        for delay in [0] + list(backoff):
            if delay:
                time.sleep(delay)
            try:
                params = {"q": query, "api_key": self._api_key, "num": 10}
                data = _GoogleSearch(params).get_dict()
                return data.get("organic_results", [])
            except Exception as exc:
                code = getattr(exc, "status_code", None)
                if code in (429, 503):
                    logger.warning("SerpAPI rate limit, backoff %ds", delay)
                    continue
                logger.error("SerpAPI error for query '%s': %s", query, exc)
                return None
        return None

    def _parse_results(self, raw: list[dict], result_type: str) -> list[SearchResult]:
        from urllib.parse import urlparse
        results = []
        for item in raw:
            url = item.get("link", "")
            if not url:
                continue
            netloc = urlparse(url).netloc.lower()
            if netloc.startswith("www."):
                netloc = netloc[4:]
            domain = netloc.split(":")[0]
            if self._registry.is_denied(domain):
                continue
            results.append(SearchResult(
                url=url,
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
                source_domain=domain,
                source_role=self._registry.get_source_role(domain),
                result_type=result_type,
            ))
        return results

    def _apply_rate_limit(self, domain: str) -> None:
        if not domain:
            return
        state = self._get_state(domain)
        delay = self._registry.get_delay_sec(domain)
        elapsed = time.time() - state.last_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)
        state.last_request_at = time.time()

    def _record_failure(self, domain: str) -> None:
        if not domain:
            return
        state = self._get_state(domain)
        state.fail_count += 1
        threshold = self._registry.domain_fail_threshold()
        if state.fail_count >= threshold and not state.degraded:
            state.degraded = True
            logger.warning(
                "Domain %s degraded after %d failures — manufacturer_domain_degraded=true",
                domain, state.fail_count,
            )

    def _reset_failures(self, domain: str) -> None:
        if domain:
            self._get_state(domain).fail_count = 0

    def _get_state(self, domain: str) -> _DomainState:
        if domain not in self._domain_states:
            self._domain_states[domain] = _DomainState()
        return self._domain_states[domain]

    def _budget_exhausted(self) -> bool:
        return self._search_count >= self._max_search


# ── Helpers ───────────────────────────────────────────────────────────────────

def _has_strong_evidence(results: list[SearchResult]) -> bool:
    """True if any result is from a top-tier source (early-stop signal)."""
    return any(
        r.source_role in ("manufacturer_proof", "official_pdf_proof")
        for r in results
    )

"""source_trust.py — Source role registry for enrichment pipeline vNext.

Loads config/seed_source_trust.json and provides role/trust lookups.
Unknown domains → organic_discovery (never denied unless in denylist).

Note: coexists with trust.py (different API, different purpose).
trust.py is used by the existing pipeline v1.5.
source_trust.py is used by vNext modules (search_orchestrator, candidate_lake, etc.)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "seed_source_trust.json"
_SOURCE_MATRIX_PATH = Path(__file__).parent.parent / "config" / "source_role_field_matrix_v1.json"

_ROLE_ORDER = [
    "manufacturer_proof",
    "official_pdf_proof",
    "authorized_distributor",
    "industrial_distributor",
]
_DEFAULT_ROLE = "organic_discovery"

_DEFAULT_TRUST_SCORES = {"identity": "MED", "price": "MED", "photo": "MED", "pdf": "LOW"}


class SourceTrustRegistry:
    """Registry loaded from seed_source_trust.json."""

    def __init__(self, config_path: Path = _CONFIG_PATH) -> None:
        with open(config_path, encoding="utf-8") as f:
            self._cfg = json.load(f)

        # Build domain → role index (first match wins by _ROLE_ORDER priority)
        self._domain_to_role: dict[str, str] = {}
        for role in _ROLE_ORDER:
            for domain in self._cfg.get(role, []):
                d = domain.lower()
                if d not in self._domain_to_role:
                    self._domain_to_role[d] = role

        self._denylist: set[str] = {
            d.lower() for d in self._cfg.get("denylist", [])
        }
        self._trust_matrix: dict[str, dict] = self._cfg.get("domain_trust_matrix", {})
        self._rate_limits: dict = self._cfg.get("rate_limits", {})

    # ── Public API ────────────────────────────────────────────────────────────

    def get_source_role(self, domain: str) -> str:
        """Return source role for domain. Unknown → organic_discovery."""
        return self._domain_to_role.get(_extract_domain(domain), _DEFAULT_ROLE)

    def get_trust_scores(self, domain: str) -> dict[str, str]:
        """Return trust scores dict {identity, price, photo, pdf} for domain's role."""
        role = self.get_source_role(domain)
        return dict(self._trust_matrix.get(role, _DEFAULT_TRUST_SCORES))

    def is_denied(self, domain: str) -> bool:
        """Return True if domain is on the denylist."""
        return _extract_domain(domain) in self._denylist

    def get_delay_sec(self, domain: str) -> float:
        """Return minimum inter-request delay for this domain (seconds)."""
        d = _extract_domain(domain)
        large = [x.lower() for x in self._rate_limits.get("large_distributors", [])]
        if d in large:
            return float(self._rate_limits.get("large_distributor_delay_sec", 3))
        return float(self._rate_limits.get("default_delay_sec", 2))

    def domain_timeout_sec(self) -> int:
        return int(self._rate_limits.get("domain_timeout_sec", 10))

    def domain_max_retries(self) -> int:
        return int(self._rate_limits.get("domain_max_retries", 2))

    def domain_fail_threshold(self) -> int:
        return int(self._rate_limits.get("domain_fail_threshold", 3))

    def get_manufacturer_domains(self) -> list[str]:
        """Return all manufacturer_proof domains."""
        return list(self._cfg.get("manufacturer_proof", []))

    def get_authorized_domains(self) -> list[str]:
        """Return all authorized_distributor domains."""
        return list(self._cfg.get("authorized_distributor", []))


# ── Domain extraction ─────────────────────────────────────────────────────────

def _extract_domain(raw: str) -> str:
    """Extract domain from URL or domain string. Strips www. prefix only."""
    raw = raw.strip().lower()
    if raw.startswith("http"):
        host = urlparse(raw).netloc or raw
    else:
        host = raw
    # Strip port
    host = host.split(":")[0]
    # Strip www. prefix only (keep sps.honeywell.com as-is)
    if host.startswith("www."):
        host = host[4:]
    return host


# ── Module-level convenience functions (singleton registry) ──────────────────

_registry: SourceTrustRegistry | None = None
_source_matrix_cache: dict | None = None


def _get_registry() -> SourceTrustRegistry:
    global _registry
    if _registry is None:
        _registry = SourceTrustRegistry()
    return _registry


def get_source_role(domain: str) -> str:
    """Module-level convenience: get source role for domain."""
    return _get_registry().get_source_role(domain)


def get_trust_scores(domain: str) -> dict[str, str]:
    """Module-level convenience: get trust scores for domain."""
    return _get_registry().get_trust_scores(domain)


def is_denied(domain: str) -> bool:
    """Module-level convenience: check denylist."""
    return _get_registry().is_denied(domain)


def load_source_role_field_matrix() -> dict:
    """Load the Phase A source-role-by-field matrix."""
    global _source_matrix_cache
    if _source_matrix_cache is None:
        with open(_SOURCE_MATRIX_PATH, encoding="utf-8") as f:
            _source_matrix_cache = json.load(f)
    return dict(_source_matrix_cache)


def get_field_role_policy(field_name: str, source_role: str) -> dict:
    """Return explicit admissibility policy for one field/source-role pair."""
    matrix = load_source_role_field_matrix()
    field_block = matrix.get("fields", {}).get(field_name, {})
    if source_role not in field_block:
        raise KeyError(f"Unknown field/source_role pair: {field_name}/{source_role}")
    return dict(field_block[source_role])

"""trust.py — Source trust table for Honeywell/Esser/Intermec/Sperian pipeline.

Tier hierarchy:
  official     — manufacturer direct (weight 0.95-1.0)
  authorized   — authorized global distributor (0.80-0.90)
  industrial   — industrial B2B, reliable pricing (0.65-0.80)
  ru_b2b       — Russian B2B distributors (0.55-0.75)
  aggregator   — PDF/manual aggregators, low price trust (0.25-0.40)
  weak         — marketplaces, forums, consumer sites (0.15-0.35)
  unknown      — default fallback (0.40)

Weight is used for candidate ranking: higher weight boosts price/photo confidence.
"""
from __future__ import annotations

from urllib.parse import urlparse


# ── Trust table ─────────────────────────────────────────────────────────────────

DOMAIN_TRUST: dict[str, dict] = {
    # ── Official manufacturer ───────────────────────────────────────────────────
    "honeywell.com":              {"tier": "official",    "weight": 1.00, "official": True},
    "honeywellprocess.com":       {"tier": "official",    "weight": 1.00, "official": True},
    "honeywellsensing.com":       {"tier": "official",    "weight": 1.00, "official": True},
    "honeywellstore.com":         {"tier": "official",    "weight": 0.95, "official": True},
    "esser-systems.com":          {"tier": "official",    "weight": 1.00, "official": True},
    "esser.de":                   {"tier": "official",    "weight": 1.00, "official": True},
    "intermec.com":               {"tier": "official",    "weight": 1.00, "official": True},
    "sperian.com":                {"tier": "official",    "weight": 1.00, "official": True},
    "sperian-protection.com":     {"tier": "official",    "weight": 0.98, "official": True},
    "uvex-safety.com":            {"tier": "official",    "weight": 0.95, "official": True},

    # ── Authorized global distributors ──────────────────────────────────────────
    "grainger.com":               {"tier": "authorized",  "weight": 0.90},
    "newark.com":                 {"tier": "authorized",  "weight": 0.90},
    "mouser.com":                 {"tier": "authorized",  "weight": 0.90},
    "digikey.com":                {"tier": "authorized",  "weight": 0.90},
    "rs-online.com":              {"tier": "authorized",  "weight": 0.90},
    "rsonline.ru":                {"tier": "authorized",  "weight": 0.88},
    "uk.rs-online.com":           {"tier": "authorized",  "weight": 0.88},
    "element14.com":              {"tier": "authorized",  "weight": 0.88},
    "farnell.com":                {"tier": "authorized",  "weight": 0.88},
    "automation24.com":           {"tier": "authorized",  "weight": 0.85},
    "automation24.de":            {"tier": "authorized",  "weight": 0.85},
    "igs-hagen.de":               {"tier": "authorized",  "weight": 0.85},
    "adiglobal.cz":               {"tier": "authorized",  "weight": 0.80},
    "adiglobal.com":              {"tier": "authorized",  "weight": 0.80},
    "elfa.se":                    {"tier": "authorized",  "weight": 0.82},
    "electrocomponents.com":      {"tier": "authorized",  "weight": 0.85},
    "futureelectronics.com":      {"tier": "authorized",  "weight": 0.83},

    # ── Industrial / technical B2B ──────────────────────────────────────────────
    "plcdistributors.com":        {"tier": "industrial",  "weight": 0.78},
    "instrumentationtoolbox.com": {"tier": "industrial",  "weight": 0.76},
    "tescomponents.com":          {"tier": "industrial",  "weight": 0.75},
    "modern-eastern.com":         {"tier": "industrial",  "weight": 0.72},
    "3kamido.com":                {"tier": "industrial",  "weight": 0.70},
    "plcparts.co.uk":             {"tier": "industrial",  "weight": 0.72},
    "industrialcontrolsonline.com": {"tier": "industrial","weight": 0.70},
    "directindustry.com":         {"tier": "industrial",  "weight": 0.68},
    "globalspec.com":             {"tier": "industrial",  "weight": 0.65},

    # ── Russian B2B ─────────────────────────────────────────────────────────────
    "armosystems.ru":             {"tier": "ru_b2b",      "weight": 0.75},
    "elreg.ru":                   {"tier": "ru_b2b",      "weight": 0.72},
    "tdst.ru":                    {"tier": "ru_b2b",      "weight": 0.70},
    "chipdip.ru":                 {"tier": "ru_b2b",      "weight": 0.68},
    "promelec.ru":                {"tier": "ru_b2b",      "weight": 0.68},
    "meanwell.ru":                {"tier": "ru_b2b",      "weight": 0.65},
    "rossonix.com":               {"tier": "ru_b2b",      "weight": 0.62},
    "platan.ru":                  {"tier": "ru_b2b",      "weight": 0.65},
    "compel.ru":                  {"tier": "ru_b2b",      "weight": 0.65},
    "elitan.ru":                  {"tier": "ru_b2b",      "weight": 0.62},
    "klemma.ru":                  {"tier": "ru_b2b",      "weight": 0.60},

    # ── Manual / datasheet aggregators ──────────────────────────────────────────
    "manualslib.com":             {"tier": "aggregator",  "weight": 0.30},
    "manualspro.net":             {"tier": "aggregator",  "weight": 0.25},
    "easymanua.ls":               {"tier": "aggregator",  "weight": 0.25},
    "datasheetarchive.com":       {"tier": "aggregator",  "weight": 0.35},
    "alldatasheet.com":           {"tier": "aggregator",  "weight": 0.35},
    "datasheet.octopart.com":     {"tier": "aggregator",  "weight": 0.40},
    "octopart.com":               {"tier": "aggregator",  "weight": 0.40},

    # ── Weak / marketplace / consumer ───────────────────────────────────────────
    "amazon.com":                 {"tier": "weak",        "weight": 0.30},
    "amazon.de":                  {"tier": "weak",        "weight": 0.30},
    "amazon.co.uk":               {"tier": "weak",        "weight": 0.30},
    "ebay.com":                   {"tier": "weak",        "weight": 0.25},
    "ebay.de":                    {"tier": "weak",        "weight": 0.25},
    "newegg.com":                 {"tier": "weak",        "weight": 0.20},
    "tameson.com":                {"tier": "weak",        "weight": 0.20},
    "airgas.com":                 {"tier": "weak",        "weight": 0.20},
    "inwest.ge":                  {"tier": "weak",        "weight": 0.15},
}

_DEFAULT_TRUST: dict = {"tier": "unknown", "weight": 0.40}


# ── Domain extraction ────────────────────────────────────────────────────────────

def get_domain(url: str) -> str:
    """Extract root domain from URL, strip www / subdomains."""
    try:
        netloc = (urlparse(url).netloc or "").split(":")[0].lower()
        parts = netloc.split(".")
        if len(parts) >= 2:
            # Handle two-part TLDs: .co.uk, .com.au, etc.
            if parts[-2] in ("co", "com", "org", "net") and len(parts) >= 3:
                return ".".join(parts[-3:])
            return ".".join(parts[-2:])
        return netloc
    except Exception:
        return ""


# ── Public API ───────────────────────────────────────────────────────────────────

def get_source_trust(url: str) -> dict:
    """Return trust dict for a given URL.

    Falls back to TLD heuristics, then default.
    Always includes 'domain' key for traceability.
    """
    domain = get_domain(url)

    if domain in DOMAIN_TRUST:
        return {**DOMAIN_TRUST[domain], "domain": domain}

    # TLD heuristics
    if domain.endswith(".ru"):
        return {"tier": "ru_b2b", "weight": 0.55, "domain": domain}

    if any(domain.endswith(tld) for tld in (".de", ".cz", ".pl", ".nl", ".be", ".at", ".ch")):
        return {"tier": "industrial", "weight": 0.65, "domain": domain}

    return {**_DEFAULT_TRUST, "domain": domain}


def get_source_tier(url: str) -> str:
    return get_source_trust(url)["tier"]


def get_source_weight(url: str) -> float:
    return float(get_source_trust(url).get("weight", 0.40))


def is_official(url: str) -> bool:
    trust = get_source_trust(url)
    return trust.get("official", False) or trust["tier"] == "official"

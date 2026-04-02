"""Deterministic pre-LLM price-source lineage helpers.

This module extracts exact-product lineage signals from the fetched source page
before any LLM price extraction. It does not infer prices. It only preserves
structured exact-product page evidence so downstream logic can distinguish:

- source seen but generic / unconfirmed
- source seen with exact structured product lineage
- source seen with exact structured lineage but weak source tier
"""
from __future__ import annotations

from typing import Any
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from no_price_coverage import materialize_no_price_coverage
from pn_match import extract_structured_pn_flags


PRICE_LINEAGE_SCHEMA_VERSION = "price_lineage_v1"
_ADMISSIBLE_LINEAGE_TIERS = {"official", "authorized", "industrial"}
_NOISY_PAGE_TOKENS = (
    "accessor",
    "accessory",
    "analog",
    "analogs",
    "bundle",
    "catalog",
    "category",
    "comparison",
    "datasheet",
    "family",
    "kit",
    "listing",
    "matrix",
    "replacement",
    "results",
    "search",
    "similar",
    "spare",
    "support community",
)
_BLOCKED_TITLE_TOKENS = (
    "access denied",
    "forbidden",
    "captcha",
    "cloudflare",
)
_OFFICIAL_ARTICLE_URL_DOMAIN = "sps-support.honeywell.com"
_OFFICIAL_ARTICLE_URL_PREFIX = "/s/article/"
_OFFICIAL_ARTICLE_SHELL_TOKENS = ("community",)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _domain(url: Any) -> str:
    if not url:
        return ""
    return (urlparse(str(url)).netloc or "").lower().removeprefix("www.")


def _best_title_h1_text(soup: BeautifulSoup) -> str:
    parts: list[str] = []
    if soup.title and soup.title.get_text(" ", strip=True):
        parts.append(soup.title.get_text(" ", strip=True))
    h1 = soup.find("h1")
    if h1 and h1.get_text(" ", strip=True):
        parts.append(h1.get_text(" ", strip=True))
    return " ".join(parts)


def _html_looks_blocked_or_non_product(soup: BeautifulSoup) -> bool:
    text = _normalized_text(_best_title_h1_text(soup))
    if any(token in text for token in _BLOCKED_TITLE_TOKENS):
        return True
    return False


def _structured_page_looks_clean(soup: BeautifulSoup) -> bool:
    text = _normalized_text(_best_title_h1_text(soup))
    if not text:
        return False
    return not any(token in text for token in _NOISY_PAGE_TOKENS)


def _official_article_url_exact_match(
    *,
    pn: str,
    source_url: str,
    source_tier: str,
    soup: BeautifulSoup,
) -> bool:
    if _normalized_text(source_tier) != "official":
        return False
    if _domain(source_url) != _OFFICIAL_ARTICLE_URL_DOMAIN:
        return False

    shell_text = _normalized_text(_best_title_h1_text(soup))
    if not shell_text or not any(token in shell_text for token in _OFFICIAL_ARTICLE_SHELL_TOKENS):
        return False

    path = unquote(urlparse(source_url).path or "")
    lowered_path = path.lower()
    if not lowered_path.startswith(_OFFICIAL_ARTICLE_URL_PREFIX):
        return False

    slug = path[len(_OFFICIAL_ARTICLE_URL_PREFIX):].strip()
    if not slug:
        return False

    pn_norm = pn.strip().lower()
    slug_norm = slug.lower()
    if not slug_norm.startswith(f"{pn_norm}-"):
        return False

    tail = slug_norm[len(pn_norm) + 1:]
    return any(ch.isalpha() for ch in tail)


def _derive_lineage_reason_code(
    *,
    content_type: str,
    blocked_or_non_html: bool,
    exact_structured_pn_match: bool,
    clean_product_page: bool,
    official_article_url_exact_match: bool,
    source_tier: str,
) -> str:
    if blocked_or_non_html:
        return "access_denied_or_non_html"
    if not exact_structured_pn_match:
        return "structured_exact_match_missing"
    if official_article_url_exact_match:
        return "official_article_url_exact_match"
    if not clean_product_page:
        return "structured_page_not_clean"
    if source_tier not in _ADMISSIBLE_LINEAGE_TIERS:
        return "structured_exact_product_page_weak_tier"
    if "html" not in _normalized_text(content_type):
        return "access_denied_or_non_html"
    return "structured_exact_product_page"


def materialize_pre_llm_price_lineage(
    *,
    pn: str,
    price_result: dict[str, Any] | None,
    html: str = "",
    source_url: str = "",
    source_type: str = "",
    source_tier: str = "",
    source_engine: str = "",
    content_type: str = "",
    status_code: int | None = None,
) -> dict[str, Any]:
    """Attach deterministic pre-LLM exact-product lineage signals."""
    result = dict(price_result or {})
    result = materialize_no_price_coverage(
        {
            **result,
            "source_url": result.get("source_url") or source_url,
            "source_type": result.get("source_type") or source_type,
            "source_tier": result.get("source_tier") or source_tier,
            "source_engine": result.get("source_engine") or source_engine,
        }
    )

    html_text = html or ""
    blocked_or_non_html = bool(
        (status_code is not None and status_code != 200)
        or not html_text
        or "html" not in _normalized_text(content_type)
    )

    lineage_flags = {
        "price_source_exact_title_pn_match": False,
        "price_source_exact_h1_pn_match": False,
        "price_source_exact_jsonld_pn_match": False,
        "price_source_exact_product_context_match": False,
        "price_source_clean_product_page": False,
        "price_source_exact_product_lineage_confirmed": False,
        "price_source_lineage_reason_code": "access_denied_or_non_html",
        "price_source_structured_match_location": "",
        "price_lineage_schema_version": PRICE_LINEAGE_SCHEMA_VERSION,
    }

    if blocked_or_non_html:
        result.update(lineage_flags)
        result["price_source_domain"] = result.get("price_source_domain") or _domain(result.get("price_source_url"))
        return result

    soup = BeautifulSoup(html_text, "html.parser")
    if _html_looks_blocked_or_non_product(soup):
        result.update(lineage_flags)
        result["price_source_lineage_confirmed"] = False
        result["price_exact_product_page"] = False
        result["price_source_lineage_reason_code"] = "access_denied_or_non_html"
        return result

    structured = extract_structured_pn_flags(pn, html_text)
    official_article_url_exact_match = (
        not bool(structured.get("exact_structured_pn_match"))
        and _official_article_url_exact_match(
            pn=pn,
            source_url=result.get("source_url") or source_url,
            source_tier=result.get("source_tier") or source_tier,
            soup=soup,
        )
    )
    exact_structured_match = bool(structured.get("exact_structured_pn_match") or official_article_url_exact_match)
    clean_product_page = bool(
        exact_structured_match
        and not official_article_url_exact_match
        and _structured_page_looks_clean(soup)
    )
    normalized_tier = _normalized_text(result.get("price_source_tier") or source_tier)
    lineage_confirmed = bool(clean_product_page or official_article_url_exact_match)
    reviewable_lineage = clean_product_page and normalized_tier in _ADMISSIBLE_LINEAGE_TIERS
    reason_code = _derive_lineage_reason_code(
        content_type=content_type,
        blocked_or_non_html=False,
        exact_structured_pn_match=exact_structured_match,
        clean_product_page=clean_product_page,
        official_article_url_exact_match=official_article_url_exact_match,
        source_tier=normalized_tier,
    )
    structured_match_location = structured.get("structured_pn_match_location", "")
    if not structured_match_location and official_article_url_exact_match:
        structured_match_location = "official_article_url"

    result.update(
        {
            "price_source_exact_title_pn_match": bool(structured.get("exact_title_pn_match")),
            "price_source_exact_h1_pn_match": bool(structured.get("exact_h1_pn_match")),
            "price_source_exact_jsonld_pn_match": bool(structured.get("exact_jsonld_pn_match")),
            "price_source_exact_product_context_match": bool(structured.get("exact_product_context_pn_match")),
            "price_source_structured_match_location": structured_match_location,
            "price_source_clean_product_page": clean_product_page,
            "price_source_exact_product_lineage_confirmed": lineage_confirmed,
            "price_source_lineage_reason_code": reason_code,
            "price_lineage_schema_version": PRICE_LINEAGE_SCHEMA_VERSION,
        }
    )
    if lineage_confirmed:
        result["price_source_lineage_confirmed"] = True
        result["price_exact_product_page"] = clean_product_page
        result["page_context_clean"] = clean_product_page
        result["price_page_context_clean"] = clean_product_page
        result["price_source_observed_only"] = False
        if result.get("price_status") in {"hidden_price", "no_price_found"}:
            if not clean_product_page:
                result["price_no_price_reason_code"] = "exact_page_context_not_clean"
            elif result.get("price_rfq_only"):
                result["price_no_price_reason_code"] = "rfq_only"
            elif result.get("price_quote_required"):
                result["price_no_price_reason_code"] = "quote_required"
            else:
                result["price_no_price_reason_code"] = "no_visible_price_exact_page"
        result["price_reviewable_no_price_candidate"] = bool(
            reviewable_lineage
            and result.get("price_status") in {"hidden_price", "no_price_found"}
            and not result.get("public_price_rejection_reasons")
        )
    else:
        result["price_reviewable_no_price_candidate"] = False
    return result


def choose_better_price_lineage_candidate(
    current: dict[str, Any] | None,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Pick the most useful pre-LLM lineage candidate deterministically."""
    if current is None:
        return candidate

    def score(item: dict[str, Any]) -> tuple[int, int, int, int]:
        return (
            1 if item.get("price_source_exact_product_lineage_confirmed") else 0,
            1 if item.get("price_source_clean_product_page") else 0,
            1 if any(
                (
                    item.get("price_source_exact_title_pn_match"),
                    item.get("price_source_exact_h1_pn_match"),
                    item.get("price_source_exact_jsonld_pn_match"),
                    item.get("price_source_exact_product_context_match"),
                )
            ) else 0,
            1 if item.get("price_source_seen") else 0,
        )

    return candidate if score(candidate) > score(current) else current

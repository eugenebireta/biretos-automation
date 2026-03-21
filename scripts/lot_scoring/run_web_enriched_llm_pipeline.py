from __future__ import annotations

import argparse
import json
import os
import re
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from scripts.lot_scoring.category_engine import BRAND_KEYWORDS, VALID_CATEGORIES
from scripts.lot_scoring.pipeline.helpers import normalize_category_key, to_float, to_str

try:
    from dotenv import load_dotenv as _load_dotenv
except Exception:  # noqa: BLE001
    _load_dotenv = None

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PRICE_CHECKER_ENV = _REPO_ROOT / "price-checker" / ".env"
if _load_dotenv is not None and _PRICE_CHECKER_ENV.exists():
    _load_dotenv(_PRICE_CHECKER_ENV)

_DEFAULT_CAPITAL_CORE_PATH = Path("audits/capital_core_unknown_set.json")
_DEFAULT_QUARANTINE_PATH = Path("data/quarantine/quarantine_candidates.json")
_DEFAULT_OUTPUT_PATH = Path("data/quarantine/auto_validated_candidates.json")
_DEFAULT_REPORT_PATH = Path("audits/web_enriched_llm_report.json")
_FALLBACK_CORE_PATH = Path("audits/llm_audit_input_core_robust.json")


def _normalize_pn(value: object) -> str:
    text = to_str(value).upper().replace(" ", "").replace("-", "")
    return re.sub(r"[^A-Z0-9]", "", text)


def _load_capital_core(path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    selected_path = path
    if not selected_path.exists() and _FALLBACK_CORE_PATH.exists():
        selected_path = _FALLBACK_CORE_PATH
    if not selected_path.exists():
        raise FileNotFoundError(f"Capital core file not found: {path}")

    payload = json.loads(selected_path.read_text(encoding="utf-8"))
    raw_items: list[Any] = []
    if isinstance(payload, dict):
        if isinstance(payload.get("capital_core_unknown_set"), list):
            raw_items = payload["capital_core_unknown_set"]
        elif isinstance(payload.get("items"), list):
            raw_items = payload["items"]
    elif isinstance(payload, list):
        raw_items = payload

    result: dict[str, dict[str, Any]] = {}
    for item in raw_items:
        if isinstance(item, str):
            pn = _normalize_pn(item)
            usd = 0.0
            sample_text = ""
        elif isinstance(item, dict):
            pn = _normalize_pn(item.get("pn") or item.get("sku_code"))
            usd = max(
                0.0,
                to_float(
                    item.get("usd", item.get("total_unknown_usd_per_pn", item.get("total_effective_usd_clean", 0.0))),
                    0.0,
                ),
            )
            sample_text = to_str(item.get("sample_text", item.get("raw_text")))
        else:
            continue
        if not pn:
            continue
        current = result.get(pn)
        candidate = {"pn": pn, "usd": usd, "sample_text": sample_text}
        if current is None:
            result[pn] = candidate
        else:
            if usd > to_float(current.get("usd"), 0.0):
                result[pn]["usd"] = usd
            if sample_text and (not to_str(current.get("sample_text")) or len(sample_text) > len(to_str(current.get("sample_text")))):
                result[pn]["sample_text"] = sample_text
    if not result:
        raise ValueError(f"Capital core set is empty: {selected_path}")
    return result, str(selected_path)


def _load_quarantine_candidates(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Quarantine candidates file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw: list[Any] = []
    if isinstance(payload, dict):
        raw = payload.get("candidates", [])
    elif isinstance(payload, list):
        raw = payload
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            rows.append(dict(item))
    return rows


def _http_get_json(url: str, *, headers: dict[str, str] | None = None, timeout: int = 30) -> dict[str, Any]:
    request = Request(url, headers=headers or {}, method="GET")
    with urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
    payload = json.loads(text)
    if isinstance(payload, dict):
        return payload
    return {}


def _http_get_text(url: str, *, timeout: int = 30) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _is_pdf_url(url: str) -> bool:
    lowered = to_str(url).lower()
    return lowered.endswith(".pdf") or ".pdf?" in lowered


def _decode_duckduckgo_redirect(url: str) -> str:
    raw = to_str(url).strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = "https:" + raw
    parsed = urlparse(raw)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [])
        if target:
            return unquote(to_str(target[0])).strip()
    return raw


def _search_serpapi(query: str, api_key: str) -> list[dict[str, str]]:
    endpoint = (
        "https://serpapi.com/search.json"
        f"?engine=google&q={quote_plus(query)}&num=5&api_key={quote_plus(api_key)}"
    )
    payload = _http_get_json(endpoint)
    organic = payload.get("organic_results", [])
    if not isinstance(organic, list):
        return []
    rows: list[dict[str, str]] = []
    for item in organic:
        if not isinstance(item, dict):
            continue
        url = to_str(item.get("link"))
        if not url or _is_pdf_url(url):
            continue
        rows.append(
            {
                "title": to_str(item.get("title")),
                "snippet": to_str(item.get("snippet")),
                "url": url,
            }
        )
        if len(rows) >= 2:
            break
    return rows


def _search_duckduckgo(query: str) -> list[dict[str, str]]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    html = _http_get_text(url)
    pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
        r'<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    rows: list[dict[str, str]] = []
    for match in pattern.finditer(html):
        raw_url = unescape(re.sub(r"<.*?>", "", match.group("url")))
        raw_title = unescape(re.sub(r"<.*?>", "", match.group("title")))
        raw_snippet = unescape(re.sub(r"<.*?>", "", match.group("snippet")))
        url_clean = _decode_duckduckgo_redirect(raw_url)
        if not url_clean or _is_pdf_url(url_clean):
            continue
        rows.append(
            {
                "title": raw_title.strip(),
                "snippet": raw_snippet.strip(),
                "url": url_clean,
            }
        )
        if len(rows) >= 2:
            break
    return rows


def _search_web_snippets(pn: str) -> list[dict[str, str]]:
    query = f"{pn} part number product"
    serpapi_key = to_str(os.getenv("SERPAPI_API_KEY"))
    if serpapi_key:
        try:
            rows = _search_serpapi(query, serpapi_key)
            if rows:
                return rows
        except Exception:
            pass
    try:
        return _search_duckduckgo(query)
    except Exception:
        return []


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = to_str(text).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def _call_heavy_llm(*, pn: str, sample_text: str, web_snippets: list[dict[str, str]]) -> dict[str, Any]:
    api_key = to_str(os.getenv("OPENROUTER_API_KEY"))
    base_url = to_str(os.getenv("OPENROUTER_BASE_URL"), "https://openrouter.ai/api/v1")
    model = to_str(os.getenv("OPENROUTER_HEAVY_MODEL"), "openai/gpt-4o")

    if not api_key:
        return {
            "pn": pn,
            "proposed_category": "unknown",
            "confidence": 0.0,
            "reasoning": "No OPENROUTER_API_KEY configured.",
        }

    prompt_payload = {
        "pn": pn,
        "sample_text": sample_text,
        "web_snippets": web_snippets,
        "instruction": "Classify industrial product category. If uncertain return 'unknown'. Do not hallucinate.",
        "valid_categories": sorted(VALID_CATEGORIES),
        "output_json_schema": {
            "pn": "string",
            "proposed_category": "string",
            "confidence": "number 0..1",
            "reasoning": "string",
        },
    }
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "Return strict JSON only."},
            {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)},
        ],
    }

    endpoint = base_url.rstrip("/") + "/chat/completions"
    request = Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return {
            "pn": pn,
            "proposed_category": "unknown",
            "confidence": 0.0,
            "reasoning": f"LLM request failed: {exc}",
        }
    try:
        parsed = json.loads(raw)
        content = to_str(parsed["choices"][0]["message"]["content"])
    except Exception as exc:
        return {
            "pn": pn,
            "proposed_category": "unknown",
            "confidence": 0.0,
            "reasoning": f"LLM invalid response: {exc}",
        }
    extracted = _extract_json_object(content)
    proposed_category = normalize_category_key(extracted.get("proposed_category"))
    if proposed_category not in VALID_CATEGORIES:
        proposed_category = "unknown"
    return {
        "pn": _normalize_pn(extracted.get("pn") or pn),
        "proposed_category": proposed_category,
        "confidence": max(0.0, min(1.0, to_float(extracted.get("confidence"), 0.0))),
        "reasoning": to_str(extracted.get("reasoning")),
    }


def _brand_present_in_snippets(snippets: list[dict[str, str]]) -> bool:
    corpus = " ".join(
        [
            to_str(item.get("title"))
            + " "
            + to_str(item.get("snippet"))
            for item in snippets
            if isinstance(item, dict)
        ]
    ).lower()
    if not corpus:
        return False
    markers: set[str] = set()
    for tokens in BRAND_KEYWORDS.values():
        for token in tokens:
            token_clean = to_str(token).strip().lower()
            if token_clean:
                markers.add(token_clean)
    return any(marker in corpus for marker in sorted(markers))


def _reasoning_has_web_facts(reasoning: str, snippets: list[dict[str, str]]) -> bool:
    reason = to_str(reasoning).lower()
    if not reason:
        return False
    fact_tokens: set[str] = set()
    for item in snippets:
        if not isinstance(item, dict):
            continue
        combined = f"{to_str(item.get('title'))} {to_str(item.get('snippet'))}".lower()
        for token in re.findall(r"[a-z0-9][a-z0-9\-/]{3,}", combined):
            fact_tokens.add(token)
    if not fact_tokens:
        return False
    return any(token in reason for token in sorted(fact_tokens))


def _auto_validate(
    *,
    proposed_category: str,
    confidence: float,
    reasoning: str,
    web_sources: list[dict[str, str]],
) -> tuple[bool, str]:
    reasons: list[str] = []
    if confidence < 0.75:
        reasons.append("confidence_below_0.75")
    if not _brand_present_in_snippets(web_sources):
        reasons.append("web_snippet_missing_brand")
    if normalize_category_key(proposed_category) == "unknown":
        reasons.append("category_unknown")
    if not _reasoning_has_web_facts(reasoning, web_sources):
        reasons.append("reasoning_missing_web_facts")
    if reasons:
        return False, ";".join(reasons)
    return True, ""


def run_web_enriched_llm_pipeline(
    *,
    capital_core_path: Path,
    quarantine_path: Path,
    output_path: Path,
    report_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    core_map, core_path_used = _load_capital_core(capital_core_path)
    quarantine_candidates = _load_quarantine_candidates(quarantine_path)

    selected: list[dict[str, Any]] = []
    for row in quarantine_candidates:
        pn = _normalize_pn(row.get("pn"))
        if not pn:
            continue
        if pn not in core_map:
            continue
        tier = to_str(row.get("tier"))
        status = to_str(row.get("status"))
        if tier != "TIER1":
            continue
        if status == "APPROVED":
            continue
        usd = max(0.0, to_float(row.get("usd", core_map[pn].get("usd")), 0.0))
        selected.append(
            {
                "pn": pn,
                "usd": usd,
                "sample_text": to_str(core_map[pn].get("sample_text")),
            }
        )

    selected.sort(key=lambda item: (-to_float(item.get("usd"), 0.0), to_str(item.get("pn"))))

    results: list[dict[str, Any]] = []
    for item in selected:
        pn = to_str(item.get("pn"))
        usd = max(0.0, to_float(item.get("usd"), 0.0))
        sample_text = to_str(item.get("sample_text"))
        web_sources = _search_web_snippets(pn)
        llm = _call_heavy_llm(pn=pn, sample_text=sample_text, web_snippets=web_sources)
        proposed_category = normalize_category_key(llm.get("proposed_category"))
        confidence = max(0.0, min(1.0, to_float(llm.get("confidence"), 0.0)))
        reasoning = to_str(llm.get("reasoning"))
        auto_validated, rejection_reason = _auto_validate(
            proposed_category=proposed_category,
            confidence=confidence,
            reasoning=reasoning,
            web_sources=web_sources,
        )
        results.append(
            {
                "pn": pn,
                "usd": round(usd, 6),
                "proposed_category": proposed_category,
                "confidence": round(confidence, 6),
                "web_sources": web_sources,
                "auto_validated": bool(auto_validated),
                "rejection_reason": rejection_reason,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    validated = [item for item in results if bool(item.get("auto_validated"))]
    rejected = [item for item in results if not bool(item.get("auto_validated"))]
    avg_conf = sum(to_float(item.get("confidence"), 0.0) for item in results) / float(len(results) or 1)
    top_usd_validated = sorted(validated, key=lambda item: (-to_float(item.get("usd"), 0.0), to_str(item.get("pn"))))[:10]

    report = {
        "input": {
            "capital_core_unknown_set": str(capital_core_path),
            "capital_core_used": core_path_used,
            "quarantine_candidates": str(quarantine_path),
        },
        "output": {
            "auto_validated_candidates": str(output_path),
        },
        "summary": {
            "total_tier1": len(selected),
            "auto_validated_count": len(validated),
            "rejected_count": len(rejected),
            "avg_confidence": round(avg_conf, 6),
            "top_usd_validated": [
                {
                    "pn": to_str(item.get("pn")),
                    "usd": round(to_float(item.get("usd"), 0.0), 6),
                    "proposed_category": to_str(item.get("proposed_category")),
                    "confidence": round(to_float(item.get("confidence"), 0.0), 6),
                }
                for item in top_usd_validated
            ],
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return results, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Web-Enriched LLM Tier1 auto-validation pipeline.")
    parser.add_argument(
        "--capital-core-set",
        default=str(_DEFAULT_CAPITAL_CORE_PATH),
        help="Path to capital_core_unknown_set.json",
    )
    parser.add_argument(
        "--quarantine",
        default=str(_DEFAULT_QUARANTINE_PATH),
        help="Path to quarantine_candidates.json",
    )
    parser.add_argument(
        "--out",
        default=str(_DEFAULT_OUTPUT_PATH),
        help="Path to auto_validated_candidates.json",
    )
    parser.add_argument(
        "--report",
        default=str(_DEFAULT_REPORT_PATH),
        help="Path to web_enriched_llm_report.json",
    )
    args = parser.parse_args()

    _, report = run_web_enriched_llm_pipeline(
        capital_core_path=Path(args.capital_core_set),
        quarantine_path=Path(args.quarantine),
        output_path=Path(args.out),
        report_path=Path(args.report),
    )
    print("===WEB_ENRICHED_LLM_REPORT_START===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("===WEB_ENRICHED_LLM_REPORT_END===")


if __name__ == "__main__":
    main()

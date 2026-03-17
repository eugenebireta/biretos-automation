from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.lot_scoring.category_engine import VALID_CATEGORIES
from scripts.lot_scoring.pipeline.helpers import normalize_category_key, to_float, to_str

try:
    from dotenv import load_dotenv as _load_dotenv
except Exception:  # noqa: BLE001
    _load_dotenv = None


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRICE_CHECKER_ENV_PATH = _REPO_ROOT / "price-checker" / ".env"
if _load_dotenv is not None and _PRICE_CHECKER_ENV_PATH.exists():
    _load_dotenv(_PRICE_CHECKER_ENV_PATH)


_DEFAULT_CAPITAL_CORE_SET_PATH = Path("audits/capital_core_unknown_set.json")
_DEFAULT_UNKNOWN_AGGREGATE_PATH = Path("audits/llm_audit_input.json")
_DEFAULT_OUT_PATH = Path("data/quarantine/llm_v2_candidates.json")
_DEFAULT_REPORT_PATH = Path("audits/llm_v2_report.json")
_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_MAX_PN = 300
_TIMEOUT_SECONDS = 45
_MAX_TOKENS = 256
_MAX_RETRIES = 2
_RETRY_DELAYS_SECONDS = (2, 4)
_CONFIDENCE_THRESHOLD = 0.60
_TOKEN_RE = re.compile(r"[A-Za-z0-9\u0400-\u04ff][A-Za-z0-9\u0400-\u04ff/\-]{3,}")
_CLASSIFIABLE_CATEGORIES = tuple(sorted(VALID_CATEGORIES - {"unknown"}))

_SYSTEM_PROMPT = (
    "You are an industrial product classifier.\n"
    "You will receive a part number (PN), a product description (sample_text),\n"
    "and a brand hint. Classify the product into exactly one category.\n\n"
    "Valid categories: construction_supplies, fire_safety, gas_safety,\n"
    "hvac_components, industrial_sensors, it_hardware, packaging_materials,\n"
    "toxic_fake, valves_actuators.\n\n"
    "Rules:\n"
    "- If you cannot confidently classify, return \"unknown\".\n"
    "- Do not hallucinate. Use only information present in the inputs.\n"
    "- Confidence must reflect how certain you are (0.0 to 1.0).\n"
    "- Reasoning must reference specific facts from the sample_text.\n\n"
    "Return strict JSON only, no markdown, no explanation outside JSON."
)


def _normalize_pn(value: object) -> str:
    text = to_str(value).upper().replace(" ", "").replace("-", "")
    return re.sub(r"[^A-Z0-9]", "", text)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _load_core_set(path: Path) -> dict[str, float]:
    if not path.exists():
        raise FileNotFoundError(f"Missing capital core set: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))

    raw_items: list[Any] = []
    if isinstance(payload, dict):
        if isinstance(payload.get("capital_core_unknown_set"), list):
            raw_items = payload["capital_core_unknown_set"]
        elif isinstance(payload.get("items"), list):
            raw_items = payload["items"]
    elif isinstance(payload, list):
        raw_items = payload

    result: dict[str, float] = {}
    for item in raw_items:
        if isinstance(item, str):
            pn = _normalize_pn(item)
            usd = 0.0
        elif isinstance(item, dict):
            pn = _normalize_pn(item.get("pn") or item.get("sku_code"))
            usd = max(
                0.0,
                to_float(
                    item.get("usd", item.get("total_unknown_usd_per_pn", item.get("total_effective_usd_clean", 0.0))),
                    0.0,
                ),
            )
        else:
            continue
        if not pn:
            continue
        result[pn] = max(result.get(pn, 0.0), usd)
    if not result:
        raise ValueError(f"Capital core set is empty or invalid: {path}")
    return result


def _load_unknown_aggregate(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing unknown aggregate input: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        items = []

    by_pn: dict[str, dict[str, Any]] = {}
    for row in items:
        if not isinstance(row, dict):
            continue
        pn = _normalize_pn(row.get("sku_code"))
        if not pn:
            continue
        effective_line_usd = max(0.0, to_float(row.get("effective_line_usd"), 0.0))
        effective_total_usd = max(0.0, to_float(row.get("effective_line_usd_total"), effective_line_usd))
        line_count = int(to_float(row.get("line_count"), 1.0))
        if line_count <= 0:
            line_count = 1
        brand = to_str(row.get("brand"), "unknown").strip().lower() or "unknown"
        raw_text = to_str(row.get("raw_text"))

        rec = by_pn.setdefault(
            pn,
            {
                "pn": pn,
                "total_usd": 0.0,
                "best_line_usd": -1.0,
                "sample_text": "",
                "brand_counts": {},
            },
        )
        rec["total_usd"] = to_float(rec.get("total_usd"), 0.0) + effective_total_usd
        if effective_line_usd > to_float(rec.get("best_line_usd"), -1.0):
            rec["best_line_usd"] = effective_line_usd
            rec["sample_text"] = raw_text
        elif effective_line_usd == to_float(rec.get("best_line_usd"), -1.0):
            current = to_str(rec.get("sample_text"))
            if raw_text and (not current or raw_text < current):
                rec["sample_text"] = raw_text

        brand_counts = rec.get("brand_counts")
        if isinstance(brand_counts, dict):
            brand_counts[brand] = int(brand_counts.get(brand, 0)) + line_count

    for pn in sorted(by_pn.keys()):
        rec = by_pn[pn]
        brand_counts = rec.get("brand_counts", {})
        if isinstance(brand_counts, dict) and brand_counts:
            top_brand = sorted(brand_counts.items(), key=lambda pair: (-int(pair[1]), pair[0]))[0][0]
        else:
            top_brand = "unknown"
        rec["brand"] = top_brand
    return by_pn


def _compose_core_rows(
    core_set: dict[str, float],
    aggregate: dict[str, dict[str, Any]],
    *,
    max_pn: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pn in sorted(core_set.keys()):
        core_usd = max(0.0, to_float(core_set.get(pn), 0.0))
        agg = aggregate.get(pn, {})
        usd = core_usd if core_usd > 0 else max(0.0, to_float(agg.get("total_usd"), 0.0))
        rows.append(
            {
                "pn": pn,
                "usd": usd,
                "sample_text": to_str(agg.get("sample_text")),
                "brand": to_str(agg.get("brand"), "unknown").strip().lower() or "unknown",
            }
        )
    rows.sort(key=lambda row: (-to_float(row.get("usd"), 0.0), to_str(row.get("pn"))))
    bounded = max(1, int(max_pn))
    return rows[:bounded]


def _build_user_prompt(*, pn: str, sample_text: str, brand_hint: str) -> dict[str, Any]:
    return {
        "pn": pn,
        "sample_text": sample_text,
        "brand_hint": brand_hint,
        "output_schema": {
            "proposed_category": "string (one of valid categories or 'unknown')",
            "confidence": "float 0.0..1.0",
            "reasoning": "string (must reference facts from sample_text)",
        },
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = to_str(text)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, ch in enumerate(raw):
        if ch != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _build_openai_request_body(*, model: str, user_prompt: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": model,
        "temperature": 0,
        "max_tokens": _MAX_TOKENS,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
    }


def _is_retryable_http_error(code: int) -> bool:
    return code == 429 or 500 <= code <= 599


def _sleep_before_retry(attempt: int) -> None:
    if attempt <= _MAX_RETRIES:
        time.sleep(_RETRY_DELAYS_SECONDS[attempt - 1])


def _call_openai_json_with_retry(
    *,
    api_key: str,
    model: str,
    base_url: str,
    user_prompt: dict[str, Any],
) -> tuple[dict[str, Any], int, bool, str]:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    request_body = _build_openai_request_body(model=model, user_prompt=user_prompt)

    attempts_total = _MAX_RETRIES + 1
    for attempt in range(1, attempts_total + 1):
        request = Request(
            endpoint,
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                raw_response = response.read().decode("utf-8", errors="replace")
            parsed_response = json.loads(raw_response)
            content = to_str(parsed_response["choices"][0]["message"]["content"])
            extracted = _extract_json_object(content)
            if extracted:
                return extracted, attempt, False, ""
            error_text = "json_parse_failed"
            if attempt <= _MAX_RETRIES:
                _sleep_before_retry(attempt)
                continue
            return {}, attempt, True, error_text
        except HTTPError as exc:
            code = int(getattr(exc, "code", 0))
            reason = to_str(getattr(exc, "reason", "HTTPError"))
            error_text = f"HTTP {code}: {reason}"
            if code in {400, 401, 403}:
                return {}, attempt, True, error_text
            if _is_retryable_http_error(code) and attempt <= _MAX_RETRIES:
                _sleep_before_retry(attempt)
                continue
            return {}, attempt, True, error_text
        except (TimeoutError, URLError, OSError) as exc:
            error_text = f"NETWORK_ERROR: {exc}"
            if attempt <= _MAX_RETRIES:
                _sleep_before_retry(attempt)
                continue
            return {}, attempt, True, error_text
        except Exception as exc:  # noqa: BLE001
            error_text = f"UNEXPECTED_ERROR: {exc}"
            return {}, attempt, True, error_text
    return {}, attempts_total, True, "UNREACHABLE"


def _extract_grounding_tokens(text: str) -> list[str]:
    tokens = {token.lower() for token in _TOKEN_RE.findall(to_str(text).lower())}
    return sorted(tokens)


def _reasoning_has_sample_text_facts(sample_text: str, reasoning: str) -> bool:
    tokens = _extract_grounding_tokens(sample_text)
    if not tokens:
        return False
    lowered_reasoning = to_str(reasoning).lower()
    return any(token in lowered_reasoning for token in tokens)


def _auto_validation_checks(
    *,
    category_in_valid: bool,
    proposed_category: str,
    confidence: float,
    sample_text: str,
    reasoning: str,
) -> tuple[dict[str, bool], str]:
    checks = {
        "category_not_unknown": normalize_category_key(proposed_category) != "unknown",
        "confidence_pass": confidence >= _CONFIDENCE_THRESHOLD,
        "reasoning_grounded": _reasoning_has_sample_text_facts(sample_text, reasoning),
        "category_in_valid_set": bool(category_in_valid),
    }
    rejection_reasons: list[str] = []
    if not checks["category_not_unknown"]:
        rejection_reasons.append("category_is_unknown")
    if not checks["confidence_pass"]:
        rejection_reasons.append("confidence_below_0.60")
    if not checks["reasoning_grounded"]:
        rejection_reasons.append("reasoning_not_grounded")
    if not checks["category_in_valid_set"]:
        rejection_reasons.append("category_invalid")
    return checks, ";".join(rejection_reasons)


def run_llm_classify_v2(
    *,
    capital_core_set_path: Path,
    unknown_aggregate_path: Path,
    out_path: Path,
    report_path: Path,
    model: str,
    max_pn: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    api_key = to_str(os.getenv("OPENAI_API_KEY"))
    base_url = to_str(os.getenv("OPENAI_BASE_URL"), _DEFAULT_BASE_URL)
    resolved_model = to_str(model, _DEFAULT_MODEL) or _DEFAULT_MODEL
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")

    core_set = _load_core_set(capital_core_set_path)
    aggregate = _load_unknown_aggregate(unknown_aggregate_path)
    rows = _compose_core_rows(core_set, aggregate, max_pn=max_pn)

    records: list[dict[str, Any]] = []
    category_distribution: dict[str, int] = {}
    for row in rows:
        pn = to_str(row.get("pn"))
        usd = max(0.0, to_float(row.get("usd"), 0.0))
        sample_text = to_str(row.get("sample_text"))
        brand = to_str(row.get("brand"), "unknown").strip().lower() or "unknown"

        user_prompt = _build_user_prompt(pn=pn, sample_text=sample_text, brand_hint=brand)
        llm_json, attempt_count, llm_error, error_reason = _call_openai_json_with_retry(
            api_key=api_key,
            model=resolved_model,
            base_url=base_url,
            user_prompt=user_prompt,
        )

        raw_category = normalize_category_key(llm_json.get("proposed_category"))
        category_in_valid = raw_category in VALID_CATEGORIES
        proposed_category = raw_category if category_in_valid else "unknown"
        confidence = _clamp01(to_float(llm_json.get("confidence"), 0.0))
        reasoning = to_str(llm_json.get("reasoning"))
        if llm_error:
            proposed_category = "unknown"
            confidence = 0.0
            reasoning = f"LLM_ERROR: {error_reason}"

        checks, rejection_reason = _auto_validation_checks(
            category_in_valid=category_in_valid,
            proposed_category=proposed_category,
            confidence=confidence,
            sample_text=sample_text,
            reasoning=reasoning,
        )
        auto_validated = all(checks.values()) and not llm_error
        if llm_error and rejection_reason:
            rejection_reason = f"{rejection_reason};llm_error"
        elif llm_error:
            rejection_reason = "llm_error"

        record = {
            "pn": pn,
            "usd": round(usd, 6),
            "brand": brand,
            "sample_text": sample_text,
            "proposed_category": proposed_category,
            "confidence": round(confidence, 6),
            "reasoning": reasoning,
            "auto_validated": bool(auto_validated),
            "rejection_reason": rejection_reason,
            "llm_error": bool(llm_error),
            "model_used": resolved_model,
            "attempt_count": int(attempt_count),
        }
        records.append(record)
        category_distribution[proposed_category] = int(category_distribution.get(proposed_category, 0)) + 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    validated = [item for item in records if bool(item.get("auto_validated"))]
    rejected = [item for item in records if not bool(item.get("auto_validated"))]
    llm_error_count = sum(1 for item in records if bool(item.get("llm_error")))
    avg_confidence = (
        sum(to_float(item.get("confidence"), 0.0) for item in records) / float(len(records))
        if records
        else 0.0
    )
    top_validated_by_usd = sorted(
        validated,
        key=lambda item: (-to_float(item.get("usd"), 0.0), to_str(item.get("pn"))),
    )[:10]

    report = {
        "config": {
            "model": resolved_model,
            "base_url": base_url,
            "temperature": 0,
            "timeout_seconds": _TIMEOUT_SECONDS,
            "max_tokens": _MAX_TOKENS,
            "max_retries": _MAX_RETRIES,
            "retry_delays_seconds": list(_RETRY_DELAYS_SECONDS),
            "confidence_threshold": _CONFIDENCE_THRESHOLD,
            "max_pn": int(max(1, max_pn)),
            "valid_categories": sorted(VALID_CATEGORIES),
            "classifiable_categories": list(_CLASSIFIABLE_CATEGORIES),
        },
        "input": {
            "capital_core_set": str(capital_core_set_path),
            "unknown_aggregate": str(unknown_aggregate_path),
        },
        "summary": {
            "total_pn_processed": len(records),
            "auto_validated_count": len(validated),
            "rejected_count": len(rejected),
            "llm_error_count": llm_error_count,
            "avg_confidence": round(avg_confidence, 6),
        },
        "category_distribution": {key: category_distribution[key] for key in sorted(category_distribution.keys())},
        "top_validated_by_usd": [
            {
                "pn": to_str(item.get("pn")),
                "usd": round(to_float(item.get("usd"), 0.0), 6),
                "proposed_category": to_str(item.get("proposed_category")),
                "confidence": round(to_float(item.get("confidence"), 0.0), 6),
            }
            for item in top_validated_by_usd
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return records, report


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM Layer v2.0 (OpenAI-only, deterministic, no web-search).")
    parser.add_argument(
        "--capital-core-set",
        default=str(_DEFAULT_CAPITAL_CORE_SET_PATH),
        help="Path to capital core unknown set JSON.",
    )
    parser.add_argument(
        "--unknown-aggregate",
        default=str(_DEFAULT_UNKNOWN_AGGREGATE_PATH),
        help="Path to unknown aggregate JSON.",
    )
    parser.add_argument(
        "--out",
        default=str(_DEFAULT_OUT_PATH),
        help="Output path for llm_v2_candidates.json.",
    )
    parser.add_argument(
        "--report",
        default=str(_DEFAULT_REPORT_PATH),
        help="Output path for llm_v2_report.json.",
    )
    parser.add_argument(
        "--model",
        default=_DEFAULT_MODEL,
        help="OpenAI model to use.",
    )
    parser.add_argument(
        "--max-pn",
        type=int,
        default=_DEFAULT_MAX_PN,
        help="Max number of capital-core PN to process.",
    )
    args = parser.parse_args()

    _, report = run_llm_classify_v2(
        capital_core_set_path=Path(args.capital_core_set),
        unknown_aggregate_path=Path(args.unknown_aggregate),
        out_path=Path(args.out),
        report_path=Path(args.report),
        model=to_str(args.model, _DEFAULT_MODEL),
        max_pn=max(1, int(args.max_pn)),
    )
    print("===LLM_CLASSIFY_V2_REPORT_START===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("===LLM_CLASSIFY_V2_REPORT_END===")


if __name__ == "__main__":
    main()

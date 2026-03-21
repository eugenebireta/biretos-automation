from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.lot_scoring.category_engine import BRAND_CATEGORY_MAP, CATEGORY_KEYWORDS
from scripts.lot_scoring.pipeline.helpers import normalize_category_key, to_float, to_str


_ISO8601_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_DEFAULT_CREATED_AT = "1970-01-01T00:00:00Z"
_SCHEMA_PATH = Path("data/quarantine/llm_candidate_schema.json")
_DEFAULT_OUT_JSON = Path("data/quarantine/quarantine_candidates.json")
_DEFAULT_OUT_XLSX = Path("data/quarantine/quarantine_candidates.xlsx")


def _normalize_pn(value: object) -> str:
    text = to_str(value).upper().replace(" ", "").replace("-", "")
    return re.sub(r"[^A-Z0-9]", "", text)


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


def _compose_core_rows(core_set: dict[str, float], aggregate: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
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
    return rows


def _infer_category_deterministic(*, pn: str, sample_text: str, brand: str, model_used: str) -> tuple[str, float, str]:
    lowered = f"{pn} {sample_text} {brand}".lower()
    brand_key = to_str(brand).strip().lower()
    mapped_from_brand = BRAND_CATEGORY_MAP.get(brand_key, "")
    if mapped_from_brand:
        confidence = 0.95 if model_used == "HEAVY" else 0.90
        return mapped_from_brand, confidence, f"brand_map:{brand_key}->{mapped_from_brand}"

    hit_rows: list[tuple[str, int, list[str]]] = []
    for category in sorted(CATEGORY_KEYWORDS.keys()):
        markers = CATEGORY_KEYWORDS[category]
        hits = [marker for marker in markers if marker in lowered]
        if hits:
            hit_rows.append((category, len(hits), hits))
    if not hit_rows:
        return "unknown", 0.40 if model_used == "HEAVY" else 0.35, "no_keyword_hits"

    best_category, hit_count, hit_markers = sorted(hit_rows, key=lambda row: (-row[1], row[0]))[0]
    base = 0.72 if model_used == "HEAVY" else 0.65
    confidence = min(0.98, base + 0.06 * hit_count)
    marker_preview = ",".join(sorted(hit_markers)[:5])
    return best_category, confidence, f"keyword_hits:{marker_preview}"


def _sanity_pass(proposed_category: str, sample_text: str) -> bool:
    normalized = normalize_category_key(proposed_category)
    if normalized == "unknown":
        return False
    markers = CATEGORY_KEYWORDS.get(normalized)
    if not markers:
        return False
    lowered = to_str(sample_text).lower()
    return any(marker in lowered for marker in markers)


def _status_for_candidate(*, tier: str, confidence: float, sanity_pass: bool) -> str:
    if tier == "TIER1":
        return "CRITICAL_REVIEW"
    if confidence < 0.85:
        return "REQUIRES_REVIEW"
    if not sanity_pass:
        return "REQUIRES_REVIEW"
    return "AUTO"


def _assert_iso8601_utc(value: str) -> None:
    if not _ISO8601_UTC_RE.fullmatch(value):
        raise ValueError(f"created_at must match ISO8601 UTC (YYYY-MM-DDTHH:MM:SSZ), got: {value}")


def _validate_candidate_schema(candidate: dict[str, Any], schema: dict[str, Any]) -> None:
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    for key in required:
        if key not in candidate:
            raise ValueError(f"candidate missing required field: {key}")
    if schema.get("additionalProperties") is False:
        extra = sorted(set(candidate.keys()) - set(properties.keys()))
        if extra:
            raise ValueError(f"candidate has unsupported fields: {extra}")

    for key, spec in properties.items():
        if key not in candidate:
            continue
        value = candidate[key]
        t = spec.get("type")
        if t == "string" and not isinstance(value, str):
            raise ValueError(f"candidate field {key} must be string")
        if t == "number" and not isinstance(value, (int, float)):
            raise ValueError(f"candidate field {key} must be number")
        if t == "boolean" and not isinstance(value, bool):
            raise ValueError(f"candidate field {key} must be boolean")
        if "enum" in spec and value not in spec["enum"]:
            raise ValueError(f"candidate field {key} invalid enum value: {value}")
        if key == "created_at":
            _assert_iso8601_utc(to_str(value))


def run_llm_quarantine_pipeline(
    *,
    capital_core_set_path: Path,
    unknown_aggregate_path: Path,
    schema_path: Path,
    out_json_path: Path,
    out_xlsx_path: Path,
    usd_heavy_threshold: float,
    created_at: str,
) -> dict[str, Any]:
    _assert_iso8601_utc(created_at)
    if not schema_path.exists():
        raise FileNotFoundError(f"Missing schema file: {schema_path}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    core_set = _load_core_set(capital_core_set_path)
    aggregate = _load_unknown_aggregate(unknown_aggregate_path)
    rows = _compose_core_rows(core_set, aggregate)

    candidates: list[dict[str, Any]] = []
    for row in rows:
        pn = to_str(row.get("pn"))
        usd = max(0.0, to_float(row.get("usd"), 0.0))
        sample_text = to_str(row.get("sample_text"))
        brand = to_str(row.get("brand"), "unknown").strip().lower() or "unknown"
        tier = "TIER1" if usd > usd_heavy_threshold else "TIER2"
        model_used = "HEAVY" if tier == "TIER1" else "LITE"
        proposed_category, confidence, reasoning = _infer_category_deterministic(
            pn=pn,
            sample_text=sample_text,
            brand=brand,
            model_used=model_used,
        )
        sanity = _sanity_pass(proposed_category, sample_text)
        status = _status_for_candidate(tier=tier, confidence=confidence, sanity_pass=sanity)
        candidate = {
            "pn": pn,
            "usd": round(usd, 6),
            "tier": tier,
            "model_used": model_used,
            "proposed_category": proposed_category,
            "confidence": round(max(0.0, min(1.0, confidence)), 6),
            "reasoning": to_str(reasoning),
            "sanity_pass": bool(sanity),
            "status": status,
            "created_at": created_at,
        }
        _validate_candidate_schema(candidate, schema)
        candidates.append(candidate)

    payload = {
        "schema_path": str(schema_path),
        "inputs": {
            "capital_core_unknown_set": str(capital_core_set_path),
            "unknown_aggregate": str(unknown_aggregate_path),
        },
        "config": {
            "USD_HEAVY_THRESHOLD": float(usd_heavy_threshold),
            "created_at": created_at,
        },
        "summary": {
            "total_candidates": len(candidates),
            "tier1_count": sum(1 for item in candidates if item["tier"] == "TIER1"),
            "tier2_count": sum(1 for item in candidates if item["tier"] == "TIER2"),
            "status_counts": {
                status: sum(1 for item in candidates if item["status"] == status)
                for status in ["AUTO", "REQUIRES_REVIEW", "CRITICAL_REVIEW", "APPROVED", "REJECTED"]
            },
        },
        "candidates": candidates,
    }

    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    out_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    frame = pd.DataFrame(candidates)
    frame = frame.sort_values(by=["tier", "usd", "pn"], ascending=[True, False, True], kind="mergesort")
    out_xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_excel(out_xlsx_path, index=False)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM Cascading + Quarantine Zone pipeline (no direct dictionary writes).")
    parser.add_argument(
        "--capital-core-set",
        default="audits/capital_core_unknown_set.json",
        help="Path to capital core unknown set JSON.",
    )
    parser.add_argument(
        "--unknown-aggregate",
        default="audits/llm_audit_input.json",
        help="Path to unknown PN aggregate JSON with usd/sample_text.",
    )
    parser.add_argument(
        "--schema",
        default=str(_SCHEMA_PATH),
        help="Path to strict candidate JSON schema.",
    )
    parser.add_argument(
        "--out-json",
        default=str(_DEFAULT_OUT_JSON),
        help="Output path for quarantine_candidates.json.",
    )
    parser.add_argument(
        "--out-xlsx",
        default=str(_DEFAULT_OUT_XLSX),
        help="Output path for quarantine_candidates.xlsx.",
    )
    parser.add_argument(
        "--usd-heavy-threshold",
        type=float,
        default=100000.0,
        help="USD threshold for TIER1/HEAVY split.",
    )
    parser.add_argument(
        "--created-at",
        default=_DEFAULT_CREATED_AT,
        help="Deterministic created_at timestamp in UTC ISO8601 (YYYY-MM-DDTHH:MM:SSZ).",
    )
    args = parser.parse_args()

    payload = run_llm_quarantine_pipeline(
        capital_core_set_path=Path(args.capital_core_set),
        unknown_aggregate_path=Path(args.unknown_aggregate),
        schema_path=Path(args.schema),
        out_json_path=Path(args.out_json),
        out_xlsx_path=Path(args.out_xlsx),
        usd_heavy_threshold=max(0.0, float(args.usd_heavy_threshold)),
        created_at=to_str(args.created_at),
    )
    print("===LLM_QUARANTINE_PIPELINE_SUMMARY_START===")
    print(
        json.dumps(
            {
                "out_json": str(Path(args.out_json)),
                "out_xlsx": str(Path(args.out_xlsx)),
                "summary": payload.get("summary", {}),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print("===LLM_QUARANTINE_PIPELINE_SUMMARY_END===")


if __name__ == "__main__":
    main()

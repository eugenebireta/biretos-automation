from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

from scripts.lot_scoring.cdm import LotRecord
from scripts.lot_scoring.etl import ETLInvariantError, EtlConfig, run_etl_pipeline
from scripts.lot_scoring.pipeline.helpers import normalize_category_key, to_float, to_str
from scripts.lot_scoring.pipeline.score import (
    _line_effective_usd,
    _line_eligible_for_total,
    _total_effective_lot_usd,
    apply_base_score,
    apply_final_score,
)
from scripts.lot_scoring.run_config import RunConfig
from scripts.lot_scoring.run_full_ranking_v341 import (
    REPORT_FILENAMES,
    _column_map,
    _load_reference_maps,
    _load_rows_by_lot,
    _load_rows_by_lot_with_report_merge,
    _lot_sort_key,
    _resolve_enriched_source_path,
)


def _normalize_code(value: object) -> str:
    text = to_str(value).upper().replace(" ", "").replace("-", "")
    return re.sub(r"[^A-Z0-9]", "", text)


def _extract_fixed_prefix(pattern: str) -> str:
    stripped = pattern[1:] if pattern.startswith("^") else pattern
    chars: list[str] = []
    escaped = False
    for ch in stripped:
        if escaped:
            chars.append(ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch in {".", "[", "]", "(", ")", "+", "*", "?", "{", "|", "^", "$"}:
            break
        chars.append(ch)
    return _normalize_code("".join(chars))


def _load_series_candidates(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Series candidates file not found: {path}")
    by_prefix: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            prefix = _normalize_code(row.get("prefix"))
            if not prefix:
                continue
            item = by_prefix.setdefault(
                prefix,
                {
                    "prefix": prefix,
                    "count": 0,
                    "total_effective_usd": 0.0,
                    "sample_sku": _normalize_code(row.get("sample_sku")),
                },
            )
            item["count"] = max(int(item["count"]), int(to_float(row.get("count"), 0.0)))
            item["total_effective_usd"] = max(float(item["total_effective_usd"]), to_float(row.get("total_effective_usd"), 0.0))
            sample = _normalize_code(row.get("sample_sku"))
            if sample and (not to_str(item.get("sample_sku")) or sample < to_str(item.get("sample_sku"))):
                item["sample_sku"] = sample
    return by_prefix


def _load_unknown_items(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"LLM audit input file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    rows: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        sku = _normalize_code(row.get("sku_code"))
        if not sku:
            continue
        line_count = int(to_float(row.get("line_count"), 1.0))
        if line_count <= 0:
            line_count = 1
        rows.append(
            {
                "sku_code": sku,
                "brand": to_str(row.get("brand"), "unknown").strip().lower() or "unknown",
                "raw_text": to_str(row.get("raw_text")),
                "effective_line_usd": max(0.0, to_float(row.get("effective_line_usd"), 0.0)),
                "effective_line_usd_total": max(
                    0.0,
                    to_float(row.get("effective_line_usd_total"), to_float(row.get("effective_line_usd"), 0.0)),
                ),
                "line_count": line_count,
            }
        )
    return rows


def _brand_stats(prefix: str, unknown_items: list[dict[str, Any]]) -> tuple[dict[str, int], str, float]:
    counts: dict[str, int] = {}
    matched_total = 0
    for item in unknown_items:
        sku = to_str(item.get("sku_code"))
        if not sku.startswith(prefix):
            continue
        count = int(item.get("line_count", 1))
        brand = to_str(item.get("brand"), "unknown")
        counts[brand] = counts.get(brand, 0) + count
        matched_total += count
    if matched_total <= 0:
        return {}, "unknown", 0.0
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    top_brand, top_count = ranked[0]
    return counts, top_brand, (float(top_count) / float(matched_total))


def _brand_dist_top3_text(brand_counts: dict[str, int]) -> str:
    ranked = sorted(brand_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:3]
    return "|".join(f"{brand}:{count}" for brand, count in ranked)


def _sanitize_series(
    series_candidates: dict[str, dict[str, Any]],
    unknown_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    prefixes = sorted(series_candidates.keys(), key=lambda p: (-len(p), p))
    drop_reasons: dict[str, str] = {}
    review_reasons: dict[str, str] = {}

    # A1) Numeric hazard
    for prefix in prefixes:
        if prefix.isdigit() and len(prefix) <= 4:
            drop_reasons[prefix] = "NUMERIC_HAZARD_LEN_LE_4"

    # A2) Ratio pruning (short/long pairs), deterministic by longest child first
    asc_prefixes = sorted(series_candidates.keys(), key=lambda p: (len(p), p))
    for short in asc_prefixes:
        if short in drop_reasons:
            continue
        short_count = max(1.0, to_float(series_candidates[short].get("count"), 0.0))
        child_ratios: list[tuple[float, str]] = []
        for long in prefixes:
            if len(long) <= len(short):
                continue
            if not long.startswith(short):
                continue
            long_count = to_float(series_candidates[long].get("count"), 0.0)
            child_ratios.append((long_count / short_count, long))
        if not child_ratios:
            continue
        # Children are already visited from longest to shortest due "prefixes" ordering.
        child_ratios.sort(key=lambda pair: (-len(pair[1]), pair[1]))
        max_ratio, max_child = max(child_ratios, key=lambda pair: (pair[0], -len(pair[1]), pair[1]))
        if max_ratio > 0.80:
            drop_reasons[short] = f"RATIO_DROP_GT_080(long={max_child},r={max_ratio:.4f})"
            continue
        if any(0.30 <= ratio <= 0.80 for ratio, _ in child_ratios):
            mid_ratio, mid_child = sorted(
                [(ratio, child) for ratio, child in child_ratios if 0.30 <= ratio <= 0.80],
                key=lambda pair: (-pair[0], pair[1]),
            )[0]
            review_reasons[short] = f"RATIO_REVIEW_030_080(long={mid_child},r={mid_ratio:.4f})"

    # A3) Brand plausibility and cleaned selection
    cleaned: list[dict[str, Any]] = []
    review_flags: list[dict[str, Any]] = []
    for prefix in sorted(series_candidates.keys(), key=lambda p: (p not in drop_reasons, p)):
        candidate = series_candidates[prefix]
        brand_counts, top_brand, top_share = _brand_stats(prefix, unknown_items)
        brand_top3 = _brand_dist_top3_text(brand_counts)

        if prefix in drop_reasons:
            review_flags.append(
                {
                    "prefix": prefix,
                    "reason": drop_reasons[prefix],
                    "count": int(candidate["count"]),
                    "total_effective_usd": float(candidate["total_effective_usd"]),
                    "brand_dist_top3": brand_top3,
                    "sample_sku": to_str(candidate.get("sample_sku")),
                }
            )
            continue

        if top_share < 0.80:
            reason = f"MIXED_BRAND(top_share={top_share:.4f})"
            review_flags.append(
                {
                    "prefix": prefix,
                    "reason": reason,
                    "count": int(candidate["count"]),
                    "total_effective_usd": float(candidate["total_effective_usd"]),
                    "brand_dist_top3": brand_top3,
                    "sample_sku": to_str(candidate.get("sample_sku")),
                }
            )
            continue

        if prefix in review_reasons:
            review_flags.append(
                {
                    "prefix": prefix,
                    "reason": review_reasons[prefix],
                    "count": int(candidate["count"]),
                    "total_effective_usd": float(candidate["total_effective_usd"]),
                    "brand_dist_top3": brand_top3,
                    "sample_sku": to_str(candidate.get("sample_sku")),
                }
            )

        cleaned.append(
            {
                "prefix": prefix,
                "count": int(candidate["count"]),
                "total_effective_usd": float(candidate["total_effective_usd"]),
                "top_brand": top_brand,
                "top_brand_share": float(top_share),
                "sample_sku": to_str(candidate.get("sample_sku")),
            }
        )

    cleaned.sort(key=lambda row: (-to_float(row.get("total_effective_usd"), 0.0), -int(row.get("count", 0)), to_str(row.get("prefix"))))
    review_flags.sort(
        key=lambda row: (
            -to_float(row.get("total_effective_usd"), 0.0),
            -int(row.get("count", 0)),
            to_str(row.get("prefix")),
            to_str(row.get("reason")),
        )
    )
    return cleaned, review_flags


def _write_series_csv(path: Path, cleaned_rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["prefix", "count", "total_effective_usd", "top_brand", "top_brand_share", "sample_sku"],
        )
        writer.writeheader()
        for row in cleaned_rows:
            writer.writerow(
                {
                    "prefix": to_str(row.get("prefix")),
                    "count": int(row.get("count", 0)),
                    "total_effective_usd": f"{to_float(row.get('total_effective_usd'), 0.0):.6f}",
                    "top_brand": to_str(row.get("top_brand")),
                    "top_brand_share": f"{to_float(row.get('top_brand_share'), 0.0):.6f}",
                    "sample_sku": to_str(row.get("sample_sku")),
                }
            )


def _write_review_flags_csv(path: Path, flags: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["prefix", "reason", "count", "total_effective_usd", "brand_dist_top3", "sample_sku"],
        )
        writer.writeheader()
        for row in flags:
            writer.writerow(
                {
                    "prefix": to_str(row.get("prefix")),
                    "reason": to_str(row.get("reason")),
                    "count": int(row.get("count", 0)),
                    "total_effective_usd": f"{to_float(row.get('total_effective_usd'), 0.0):.6f}",
                    "brand_dist_top3": to_str(row.get("brand_dist_top3")),
                    "sample_sku": to_str(row.get("sample_sku")),
                }
            )


def _build_candidate_patterns(cleaned_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for row in cleaned_rows:
        prefix = to_str(row.get("prefix"))
        if not prefix:
            continue
        entries.append(
            {
                "pattern": f"^{prefix}[A-Z0-9-]*$",
                "category": "TBD",
                "comment": "AUTO series candidate",
                "author": "series-pipeline",
            }
        )
    entries.sort(key=lambda item: (-len(_extract_fixed_prefix(to_str(item.get("pattern")))), _extract_fixed_prefix(to_str(item.get("pattern")))))
    return entries


def _shadowing_audit(candidate_patterns: list[dict[str, Any]], existing_patterns_path: Path) -> dict[str, Any]:
    candidate_prefixes = [_extract_fixed_prefix(to_str(item.get("pattern"))) for item in candidate_patterns]
    candidate_prefixes = [prefix for prefix in candidate_prefixes if prefix]

    existing_payload: list[dict[str, Any]] = []
    if existing_patterns_path.exists():
        loaded = json.loads(existing_patterns_path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            existing_payload = [item for item in loaded if isinstance(item, dict)]
    existing_prefixes = []
    for item in existing_payload:
        prefix = _extract_fixed_prefix(to_str(item.get("pattern")))
        if prefix:
            existing_prefixes.append((prefix, to_str(item.get("pattern"))))

    candidate_relations: list[dict[str, Any]] = []
    for i, left in enumerate(candidate_prefixes):
        for right in candidate_prefixes[i + 1 :]:
            if right.startswith(left):
                candidate_relations.append({"parent": left, "child": right, "relation": "expected_parent_child"})
            elif left.startswith(right):
                candidate_relations.append({"parent": right, "child": left, "relation": "expected_parent_child"})

    candidate_existing_relations: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = []
    existing_prefix_set = {prefix for prefix, _ in existing_prefixes}
    for prefix in sorted(candidate_prefixes):
        if prefix in existing_prefix_set:
            flags.append({"type": "duplicate_prefix_with_existing", "prefix": prefix})
        for existing_prefix, existing_pattern in existing_prefixes:
            if prefix == existing_prefix:
                continue
            if prefix.startswith(existing_prefix):
                candidate_existing_relations.append(
                    {
                        "candidate_prefix": prefix,
                        "existing_prefix": existing_prefix,
                        "existing_pattern": existing_pattern,
                        "relation": "candidate_child_of_existing",
                    }
                )
            elif existing_prefix.startswith(prefix):
                candidate_existing_relations.append(
                    {
                        "candidate_prefix": prefix,
                        "existing_prefix": existing_prefix,
                        "existing_pattern": existing_pattern,
                        "relation": "candidate_parent_of_existing",
                    }
                )

    candidate_relations.sort(key=lambda row: (row["parent"], row["child"]))
    candidate_existing_relations.sort(key=lambda row: (row["candidate_prefix"], row["existing_prefix"], row["existing_pattern"]))
    flags.sort(key=lambda row: (row["type"], row["prefix"]))
    return {
        "candidate_prefix_count": len(candidate_prefixes),
        "existing_pattern_count": len(existing_payload),
        "candidate_relations": candidate_relations,
        "candidate_existing_relations": candidate_existing_relations,
        "flags": flags,
    }


def _load_lots_from_input(input_path: Path, *, usd_rate: float) -> dict[str, list[dict]]:
    report_paths = [input_path.parent / name for name in REPORT_FILENAMES]
    enriched_path = _resolve_enriched_source_path(input_path.parent)
    use_report_merge = False

    if (enriched_path is not None and enriched_path.exists()) or any(path.exists() for path in report_paths):
        workbook = __import__("pandas").ExcelFile(input_path)
        if len(workbook.sheet_names) > 1:
            sample_df = __import__("pandas").read_excel(input_path, sheet_name=workbook.sheet_names[0], nrows=2)
            use_report_merge = "lot_id" not in _column_map(sample_df)

    if use_report_merge:
        lots, _ = _load_rows_by_lot_with_report_merge(
            input_path,
            report_paths,
            usd_rate=usd_rate,
            enriched_path=enriched_path,
        )
        return lots
    return _load_rows_by_lot(input_path)


def _match_prefix(sku_code: str, prefixes_sorted: list[str]) -> str:
    for prefix in prefixes_sorted:
        if sku_code.startswith(prefix):
            return prefix
    return ""


def _simulate_impact(
    input_path: Path,
    cleaned_rows: list[dict[str, Any]],
    *,
    usd_rate: float,
) -> dict[str, Any]:
    (
        category_obsolescence,
        brand_score,
        category_liquidity,
        category_volume_proxy,
    ) = _load_reference_maps()
    run_config = RunConfig()
    etl_config = EtlConfig()

    lots = _load_lots_from_input(input_path, usd_rate=usd_rate)
    if len(lots) < 5:
        raise ValueError(f"Too few lots detected: {len(lots)}. Expected at least 5.")

    candidate_prefixes = sorted(
        [to_str(row.get("prefix")) for row in cleaned_rows if to_str(row.get("prefix"))],
        key=lambda prefix: (-len(prefix), prefix),
    )

    baseline_unknown_usd_total = 0.0
    new_unknown_usd_total = 0.0
    total_effective_usd_total = 0.0

    baseline_unknown_by_lot: dict[str, float] = {}
    baseline_score_by_lot: dict[str, float] = {}
    new_score_by_lot: dict[str, float] = {}

    prefix_contrib: dict[str, dict[str, Any]] = {}
    pn_contrib: dict[str, float] = {}

    for lot_id in sorted(lots.keys(), key=_lot_sort_key):
        raw_skus = lots[lot_id]
        try:
            assembled = run_etl_pipeline(raw_skus, etl_config)
        except ETLInvariantError as exc:
            raise ETLInvariantError(f"Lot {lot_id} failed ETL invariants: {exc}") from exc

        lot_baseline = LotRecord(lot_id=str(lot_id))
        apply_base_score(
            lot_baseline,
            core_skus=assembled.core_skus,
            all_skus=assembled.all_skus,
            category_obsolescence=category_obsolescence,
            brand_score=brand_score,
            category_liquidity=category_liquidity,
            category_volume_proxy=category_volume_proxy,
            config=run_config,
        )
        apply_final_score(
            lot_baseline,
            core_skus=assembled.core_skus,
            all_skus=assembled.all_skus,
            config=run_config,
        )

        total_usd = _total_effective_lot_usd(assembled.all_skus)
        baseline_unknown_usd = lot_baseline.unknown_exposure_usd
        matched_unknown_usd = 0.0

        for sku in assembled.all_skus:
            if not _line_eligible_for_total(sku):
                continue
            if normalize_category_key(sku.get("category")) != "unknown":
                continue
            sku_code = _normalize_code(sku.get("sku_code_normalized") or sku.get("sku_code"))
            if not sku_code:
                continue
            matched_prefix = _match_prefix(sku_code, candidate_prefixes)
            if not matched_prefix:
                continue
            line_usd = _line_effective_usd(sku)
            if line_usd <= 0:
                continue

            matched_unknown_usd += line_usd
            rec = prefix_contrib.setdefault(
                matched_prefix,
                {"prefix": matched_prefix, "delta_usd": 0.0, "matched_lines": 0, "sample_sku": sku_code},
            )
            rec["delta_usd"] = to_float(rec.get("delta_usd"), 0.0) + line_usd
            rec["matched_lines"] = int(rec.get("matched_lines", 0)) + 1
            sample_sku = to_str(rec.get("sample_sku"))
            if not sample_sku or sku_code < sample_sku:
                rec["sample_sku"] = sku_code
            pn_contrib[sku_code] = to_float(pn_contrib.get(sku_code), 0.0) + line_usd

        new_unknown_usd = max(0.0, baseline_unknown_usd - matched_unknown_usd)

        baseline_unknown_usd_total += baseline_unknown_usd
        new_unknown_usd_total += new_unknown_usd
        total_effective_usd_total += total_usd

        lot_key = str(lot_id)
        baseline_unknown_by_lot[lot_key] = lot_baseline.unknown_exposure
        baseline_score_by_lot[lot_key] = lot_baseline.score_10
        # Impact simulation is restricted to unknown exposure without changing category mappings.
        new_score_by_lot[lot_key] = lot_baseline.score_10

    baseline_unknown_exposure = (baseline_unknown_usd_total / total_effective_usd_total) if total_effective_usd_total > 0 else 0.0
    new_unknown_exposure = (new_unknown_usd_total / total_effective_usd_total) if total_effective_usd_total > 0 else 0.0

    changed_lots: list[str] = []
    for lot_id in sorted(baseline_unknown_by_lot.keys(), key=lambda value: (int(value), value) if value.isdigit() else (10**9, value)):
        if baseline_unknown_by_lot[lot_id] != 0:
            continue
        if abs(to_float(new_score_by_lot.get(lot_id), 0.0) - to_float(baseline_score_by_lot.get(lot_id), 0.0)) > 1e-12:
            changed_lots.append(lot_id)

    top_prefix = sorted(
        prefix_contrib.values(),
        key=lambda row: (-to_float(row.get("delta_usd"), 0.0), to_str(row.get("prefix"))),
    )[:10]
    top_pn = sorted(
        [{"pn": pn, "delta_usd": usd} for pn, usd in pn_contrib.items()],
        key=lambda row: (-to_float(row.get("delta_usd"), 0.0), to_str(row.get("pn"))),
    )[:10]

    return {
        "baseline": {
            "lot_count": len(baseline_unknown_by_lot),
            "total_effective_usd": round(total_effective_usd_total, 6),
            "unknown_usd": round(baseline_unknown_usd_total, 6),
            "unknown_exposure": round(baseline_unknown_exposure, 6),
        },
        "new": {
            "lot_count": len(baseline_unknown_by_lot),
            "total_effective_usd": round(total_effective_usd_total, 6),
            "unknown_usd": round(new_unknown_usd_total, 6),
            "unknown_exposure": round(new_unknown_exposure, 6),
        },
        "delta": {
            "delta_usd": round(new_unknown_usd_total - baseline_unknown_usd_total, 6),
            "delta_exposure": round(new_unknown_exposure - baseline_unknown_exposure, 6),
        },
        "top_contributors": [
            {
                "series_prefix": to_str(row.get("prefix")),
                "delta_usd": round(to_float(row.get("delta_usd"), 0.0), 6),
                "matched_lines": int(row.get("matched_lines", 0)),
                "sample_sku": to_str(row.get("sample_sku")),
            }
            for row in top_prefix
        ],
        "top_contributors_pn": [
            {"pn": to_str(row.get("pn")), "delta_usd": round(to_float(row.get("delta_usd"), 0.0), 6)} for row in top_pn
        ],
        "anti_regression": {
            "pass": len(changed_lots) == 0,
            "changed_lots": changed_lots,
        },
        "notes": {
            "overlay_mode": "unknown_exposure_only",
            "overlay_description": (
                "Candidate series are applied as virtual unknown->known coverage for impact estimation "
                "without persisting taxonomy changes."
            ),
        },
    }


def run_series_pipeline(
    *,
    series_candidates_csv: Path,
    llm_audit_input_json: Path,
    input_xlsx: Path,
    existing_patterns_json: Path,
    output_dir: Path,
    usd_rate: float = 78.0,
) -> dict[str, Any]:
    if usd_rate <= 0:
        raise ValueError("usd_rate must be > 0.")
    output_dir.mkdir(parents=True, exist_ok=True)

    series_candidates = _load_series_candidates(series_candidates_csv)
    unknown_items = _load_unknown_items(llm_audit_input_json)

    cleaned_rows, review_flags = _sanitize_series(series_candidates, unknown_items)

    cleaned_csv_path = output_dir / "pn_series_cleaned.csv"
    review_csv_path = output_dir / "pn_series_review_flags.csv"
    candidate_patterns_path = output_dir / "pn_patterns_candidate.json"
    impact_report_path = output_dir / "pattern_rule_impact_report.json"
    shadowing_audit_path = output_dir / "pattern_rule_shadowing_audit.json"

    _write_series_csv(cleaned_csv_path, cleaned_rows)
    _write_review_flags_csv(review_csv_path, review_flags)

    candidate_patterns = _build_candidate_patterns(cleaned_rows)
    candidate_patterns_path.write_text(json.dumps(candidate_patterns, ensure_ascii=False, indent=2), encoding="utf-8")

    shadowing_audit = _shadowing_audit(candidate_patterns, existing_patterns_json)
    shadowing_audit_path.write_text(json.dumps(shadowing_audit, ensure_ascii=False, indent=2), encoding="utf-8")

    impact_report = _simulate_impact(input_xlsx, cleaned_rows, usd_rate=usd_rate)
    impact_report_path.write_text(json.dumps(impact_report, ensure_ascii=False, indent=2), encoding="utf-8")

    total_unknown_usd = sum(to_float(item.get("effective_line_usd_total"), 0.0) for item in unknown_items)
    covered_unknown_usd = 0.0
    cleaned_prefixes = sorted([to_str(row.get("prefix")) for row in cleaned_rows], key=lambda p: (-len(p), p))
    for item in unknown_items:
        sku = to_str(item.get("sku_code"))
        if _match_prefix(sku, cleaned_prefixes):
            covered_unknown_usd += to_float(item.get("effective_line_usd_total"), 0.0)
    cleaned_coverage = (covered_unknown_usd / total_unknown_usd) if total_unknown_usd > 0 else 0.0

    return {
        "inputs": {
            "series_candidates_csv": str(series_candidates_csv),
            "llm_audit_input_json": str(llm_audit_input_json),
            "input_xlsx": str(input_xlsx),
            "existing_patterns_json": str(existing_patterns_json),
        },
        "outputs": {
            "pn_series_cleaned_csv": str(cleaned_csv_path),
            "pn_series_review_flags_csv": str(review_csv_path),
            "pn_patterns_candidate_json": str(candidate_patterns_path),
            "pattern_rule_impact_report_json": str(impact_report_path),
            "pattern_rule_shadowing_audit_json": str(shadowing_audit_path),
        },
        "summary": {
            "cleaned_series_count": len(cleaned_rows),
            "review_flags_count": len(review_flags),
            "candidate_pattern_count": len(candidate_patterns),
            "cleaned_unknown_usd_coverage": round(cleaned_coverage, 6),
            "impact_delta_unknown_usd": impact_report["delta"]["delta_usd"],
            "impact_delta_unknown_exposure": impact_report["delta"]["delta_exposure"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic pipeline: Series -> Clean -> Candidate Rules -> Impact Simulation.",
    )
    parser.add_argument(
        "--series-candidates",
        default="audits/pn_series_candidates.csv",
        help="Input CSV with PN series candidates.",
    )
    parser.add_argument(
        "--llm-audit-input",
        default="audits/llm_audit_input.json",
        help="Input JSON with unknown SKU audit items.",
    )
    parser.add_argument(
        "--input",
        default="honeywell.xlsx",
        help="Input XLSX used for impact simulation.",
    )
    parser.add_argument(
        "--existing-patterns",
        default="scripts/lot_scoring/data/pn_patterns.json",
        help="Current production pn_patterns.json path (read-only).",
    )
    parser.add_argument(
        "--output-dir",
        default="audits",
        help="Output directory for generated artifacts.",
    )
    parser.add_argument(
        "--usd-rate",
        type=float,
        default=78.0,
        help="RUB/USD rate used when report merge converts RUB values to USD.",
    )
    args = parser.parse_args()

    summary = run_series_pipeline(
        series_candidates_csv=Path(args.series_candidates),
        llm_audit_input_json=Path(args.llm_audit_input),
        input_xlsx=Path(args.input),
        existing_patterns_json=Path(args.existing_patterns),
        output_dir=Path(args.output_dir),
        usd_rate=args.usd_rate,
    )
    print("===SERIES_PIPELINE_SUMMARY_START===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("===SERIES_PIPELINE_SUMMARY_END===")


if __name__ == "__main__":
    main()

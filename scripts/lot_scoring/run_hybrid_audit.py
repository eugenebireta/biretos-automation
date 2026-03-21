from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

from scripts.lot_scoring.capital_map import compute_capital_map
from scripts.lot_scoring.category_engine import BRAND_CATEGORY_MAP, CATEGORY_KEYWORDS
from scripts.lot_scoring.cdm import LotRecord
from scripts.lot_scoring.cqr import compute_cqr
from scripts.lot_scoring.etl import ETLInvariantError, EtlConfig, run_etl_pipeline
from scripts.lot_scoring.llm_auditor import _read_value_slice_rows, run_llm_audit
from scripts.lot_scoring.pipeline.helpers import to_float, to_str
from scripts.lot_scoring.pipeline.score import apply_base_score, apply_final_score
from scripts.lot_scoring.run_config import RunConfig
from scripts.lot_scoring.run_full_ranking_v341 import _load_reference_maps, _lot_sort_key, run_full_ranking
from scripts.lot_scoring.run_lot_analysis import _build_value_based_slice, _line_effective_usd, _load_lots_for_analysis


def _to_pct(value: float) -> float:
    return max(0.0, value) * 100.0


def _format_top3(top3: list[tuple[str, float]]) -> str:
    return "; ".join(f"{cat}:{share * 100.0:.1f}%" for cat, share in top3)


def _sorted_slice(top_core_skus: list[dict]) -> list[dict]:
    return sorted(
        top_core_skus,
        key=lambda sku: (
            -max(0.0, to_float(sku.get("effective_line_usd"), 0.0)),
            to_str(sku.get("sku_code_normalized")),
            to_str(sku.get("row_index")),
        ),
    )


def _compute_all_lots(
    input_path: Path,
    *,
    value_pct: float,
    max_rows: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, float]]:
    (
        category_obsolescence,
        brand_score,
        category_liquidity,
        category_volume_proxy,
    ) = _load_reference_maps()
    run_config = RunConfig()
    etl_config = EtlConfig()
    lots, merge_stats = _load_lots_for_analysis(input_path)

    lot_rows: list[dict[str, Any]] = []
    value_slice_rows: list[dict[str, Any]] = []

    for lot_id in sorted(lots.keys(), key=_lot_sort_key):
        raw_skus = lots[lot_id]
        try:
            assembled = run_etl_pipeline(raw_skus, etl_config)
        except ETLInvariantError as exc:
            raise ETLInvariantError(f"Lot {lot_id} failed ETL invariants: {exc}") from exc

        lot = LotRecord(lot_id=str(lot_id))
        lot.flags.extend(assembled.soft_flags)
        apply_base_score(
            lot,
            core_skus=assembled.core_skus,
            all_skus=assembled.all_skus,
            category_obsolescence=category_obsolescence,
            brand_score=brand_score,
            category_liquidity=category_liquidity,
            category_volume_proxy=category_volume_proxy,
            config=run_config,
        )
        apply_final_score(
            lot,
            core_skus=assembled.core_skus,
            all_skus=assembled.all_skus,
            config=run_config,
        )

        total_core_value_usd = to_float(assembled.metadata.get("core_effective_usd"), 0.0)
        if total_core_value_usd <= 0.0:
            total_core_value_usd = sum(_line_effective_usd(sku) for sku in assembled.core_skus)

        top_core_skus = _build_value_based_slice(
            assembled.core_skus,
            total_core_value_usd,
            value_pct=value_pct,
            max_rows=max_rows,
        )
        cqr = compute_cqr(top_core_skus, total_core_value_usd, list(lot.flags))
        capital_map = compute_capital_map(top_core_skus, total_core_value_usd, top_k=5)

        distribution = dict(capital_map.distribution)
        fire_pct = distribution.get("fire_safety", 0.0)
        gas_pct = distribution.get("gas_safety", 0.0)
        construction_pct = distribution.get("construction_supplies", 0.0)
        unknown_pct = distribution.get("unknown", 0.0)
        other_pct = max(0.0, 1.0 - (fire_pct + gas_pct + construction_pct + unknown_pct))

        top3_capital = sorted(distribution.items(), key=lambda pair: (-pair[1], pair[0]))[:3]

        lot_rows.append(
            {
                "lot_id": str(lot_id),
                "score_10": float(lot.score_10),
                "cqr": float(cqr.cqr_score),
                "core_ratio": float(to_float(assembled.metadata.get("core_ratio"), 0.0)),
                "total_effective_usd": float(to_float(assembled.metadata.get("total_effective_usd"), 0.0)),
                "toxic_anchor": bool(cqr.toxic_anchor_flag),
                "top3_capital_map": top3_capital,
                "fire_safety_pct": float(fire_pct),
                "gas_safety_pct": float(gas_pct),
                "construction_supplies_pct": float(construction_pct),
                "unknown_pct": float(unknown_pct),
                "other_pct": float(other_pct),
            }
        )

        ranked_slice = _sorted_slice(top_core_skus)
        for index, sku in enumerate(ranked_slice, start=1):
            raw_text = to_str(sku.get("raw_text"))
            full_row_text = to_str(sku.get("full_row_text"), raw_text) or raw_text
            value_slice_rows.append(
                {
                    "lot_id": str(lot_id),
                    "slice_rank": index,
                    "sku_code": to_str(sku.get("sku_code_normalized")),
                    "qty": max(0.0, to_float(sku.get("qty", sku.get("raw_qty", 0.0)), 0.0)),
                    "effective_usd": max(0.0, to_float(sku.get("effective_line_usd"), 0.0)),
                    "category_engine": to_str(sku.get("category"), "unknown"),
                    "brand_engine": to_str(sku.get("brand"), "unknown"),
                    "raw_text": raw_text,
                    "full_row_text": full_row_text,
                }
            )

    ranked_rows = sorted(
        lot_rows,
        key=lambda row: (
            -row["score_10"],
            -row["cqr"],
            -row["total_effective_usd"],
            _lot_sort_key(row["lot_id"]),
        ),
    )
    for rank, row in enumerate(ranked_rows, start=1):
        row["rank"] = rank

    category_rows = [
        {
            "lot_id": row["lot_id"],
            "fire_safety_pct": row["fire_safety_pct"],
            "gas_safety_pct": row["gas_safety_pct"],
            "construction_supplies_pct": row["construction_supplies_pct"],
            "unknown_pct": row["unknown_pct"],
            "other_pct": row["other_pct"],
        }
        for row in ranked_rows
    ]
    return ranked_rows, category_rows, value_slice_rows, merge_stats


def _write_csv(path: Path, *, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _parse_percent_to_ratio(value: Any) -> float:
    numeric = max(0.0, to_float(value, 0.0))
    if numeric > 1.0:
        return numeric / 100.0
    return numeric


def _load_ranked_rows_from_audits_csv(
    *,
    ranking_summary_path: Path,
    category_audit_path: Path,
) -> list[dict[str, Any]]:
    if not ranking_summary_path.exists():
        raise FileNotFoundError(f"Missing ranking summary artifact: {ranking_summary_path}")
    if not category_audit_path.exists():
        raise FileNotFoundError(f"Missing category audit artifact: {category_audit_path}")

    category_by_lot: dict[str, dict[str, Any]] = {}
    with category_audit_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            lot_id = to_str(row.get("lot_id"))
            if not lot_id:
                continue
            category_by_lot[lot_id] = {
                "fire_safety_pct": _parse_percent_to_ratio(row.get("fire_safety_pct")),
                "gas_safety_pct": _parse_percent_to_ratio(row.get("gas_safety_pct")),
                "construction_supplies_pct": _parse_percent_to_ratio(row.get("construction_supplies_pct")),
                "unknown_pct": _parse_percent_to_ratio(row.get("unknown_pct")),
                "other_pct": _parse_percent_to_ratio(row.get("other_pct")),
            }

    ranked_rows: list[dict[str, Any]] = []
    with ranking_summary_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            lot_id = to_str(row.get("lot_id"))
            if not lot_id:
                continue
            category = category_by_lot.get(lot_id, {})
            ranked_rows.append(
                {
                    "rank": int(to_float(row.get("rank"), 0.0)),
                    "lot_id": lot_id,
                    "score_10": float(to_float(row.get("score_10"), 0.0)),
                    "cqr": float(to_float(row.get("cqr"), 0.0)),
                    "core_ratio": float(to_float(row.get("core_ratio"), 0.0)),
                    "total_effective_usd": float(to_float(row.get("total_effective_usd"), 0.0)),
                    "toxic_anchor": to_str(row.get("toxic_anchor")).strip().upper() in {"YES", "TRUE", "1"},
                    "top3_capital_map": to_str(row.get("top3_capital_map")),
                    "fire_safety_pct": float(category.get("fire_safety_pct", 0.0)),
                    "gas_safety_pct": float(category.get("gas_safety_pct", 0.0)),
                    "construction_supplies_pct": float(category.get("construction_supplies_pct", 0.0)),
                    "unknown_pct": float(category.get("unknown_pct", 0.0)),
                    "other_pct": float(category.get("other_pct", 0.0)),
                }
            )

    ranked_rows = sorted(
        ranked_rows,
        key=lambda row: (
            int(row["rank"]) if int(row["rank"]) > 0 else 10**9,
            _lot_sort_key(row["lot_id"]),
        ),
    )
    for rank, row in enumerate(ranked_rows, start=1):
        if int(row["rank"]) <= 0:
            row["rank"] = rank
    return ranked_rows


def _select_lots_for_llm(ranked_rows: list[dict[str, Any]]) -> list[str]:
    top10 = {row["lot_id"] for row in ranked_rows[:10]}
    unknown_high = {row["lot_id"] for row in ranked_rows if row["unknown_pct"] >= 0.20}
    selected = top10 | unknown_high
    return [row["lot_id"] for row in ranked_rows if row["lot_id"] in selected]


def _build_delta_report(
    *,
    output_path: Path,
    ranked_rows: list[dict[str, Any]],
    value_slice_rows: list[dict[str, Any]],
    llm_result: dict[str, Any],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# Hybrid Audit Mode - Delta Report")
    lines.append("")
    lines.append("## Lots by Unknown Exposure")
    lines.append("")
    lines.append("| lot_id | unknown_pct | score_10 | cqr | total_effective_usd |")
    lines.append("|---:|---:|---:|---:|---:|")

    unknown_sorted = sorted(
        ranked_rows,
        key=lambda row: (-row["unknown_pct"], -row["total_effective_usd"], _lot_sort_key(row["lot_id"])),
    )
    for row in unknown_sorted:
        lines.append(
            f"| {row['lot_id']} | {_to_pct(row['unknown_pct']):.1f}% | {row['score_10']:.2f} | "
            f"{row['cqr']:.3f} | {row['total_effective_usd']:.2f} |"
        )

    lines.append("")
    lines.append("## LLM Audit Status")
    lines.append("")
    lines.append(f"- status: {to_str(llm_result.get('status'))}")
    reason = to_str(llm_result.get("reason"))
    if reason:
        lines.append(f"- reason: {reason}")
    lines.append("")

    selected_lots = [to_str(item) for item in llm_result.get("selected_lots", [])]
    lines.append("## Audited Lots")
    lines.append("")
    lines.append("- " + (", ".join(selected_lots) if selected_lots else "(none)"))
    lines.append("")

    slice_by_lot: dict[str, list[dict[str, Any]]] = {}
    for row in value_slice_rows:
        slice_by_lot.setdefault(to_str(row["lot_id"]), []).append(row)
    for lot_id in slice_by_lot:
        slice_by_lot[lot_id] = sorted(slice_by_lot[lot_id], key=lambda row: int(row["slice_rank"]))

    if to_str(llm_result.get("status")) != "completed":
        lines.append("## LLM Comparison")
        lines.append("")
        lines.append("LLM audit skipped. Engine-only artifacts are available.")
        lines.append("")
        lines.append("## Patch Pack Proposal")
        lines.append("")
        lines.append("- SKU_LOOKUP: not generated (LLM skipped)")
        lines.append("- BRAND_CATEGORY_MAP additions: not generated (LLM skipped)")
        lines.append("- Keyword additions: not generated (LLM skipped)")
        lines.append("")
        lines.append("## Risk Flags")
        lines.append("")
        lines.append("- LLM disagreements with confidence < 0.7: not available (LLM skipped)")
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return

    llm_rows: list[dict[str, Any]] = [
        row for row in llm_result.get("results", []) if isinstance(row, dict)
    ]
    llm_index = {
        (to_str(row.get("lot_id")), int(to_float(row.get("slice_rank"), 0.0))): row for row in llm_rows
    }

    lines.append("## Lot-level Engine vs LLM (Top 10 rows per audited lot)")
    lines.append("")

    affected_by_lot: dict[str, float] = {}
    for lot_id in selected_lots:
        lot_rows = slice_by_lot.get(lot_id, [])
        if not lot_rows:
            continue
        affected_usd = 0.0
        for row in lot_rows:
            llm_row = llm_index.get((lot_id, int(row["slice_rank"])))
            if not llm_row:
                continue
            if to_str(llm_row.get("llm_category"), "unknown") != to_str(row["category_engine"], "unknown"):
                affected_usd += to_float(row["effective_usd"], 0.0)
        affected_by_lot[lot_id] = affected_usd

        lines.append(f"### Lot {lot_id}")
        lines.append("")
        lines.append(f"- value impacted by category changes: {affected_usd:.2f} USD")
        lines.append("")
        lines.append("| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |")
        lines.append("|---:|---|---:|---|---|---:|---|")
        for row in lot_rows[:10]:
            llm_row = llm_index.get((lot_id, int(row["slice_rank"])), {})
            lines.append(
                f"| {int(row['slice_rank'])} | {to_str(row['sku_code'])} | {to_float(row['effective_usd']):.2f} | "
                f"{to_str(row['category_engine'], 'unknown')} | {to_str(llm_row.get('llm_category'), 'unknown')} | "
                f"{to_float(llm_row.get('confidence'), 0.0):.2f} | {to_str(llm_row.get('reason'))} |"
            )
        lines.append("")

    high_conf_rows = [
        row
        for row in llm_rows
        if to_float(row.get("confidence"), 0.0) >= 0.8
        and to_str(row.get("llm_category"), "unknown") in CATEGORY_KEYWORDS
        and to_str(row.get("llm_category"), "unknown") != to_str(row.get("category_engine"), "unknown")
    ]

    sku_votes: dict[tuple[str, str], dict[str, float]] = {}
    for row in high_conf_rows:
        if to_str(row.get("category_engine"), "unknown") != "unknown":
            continue
        sku = to_str(row.get("sku_code"))
        category = to_str(row.get("llm_category"), "unknown")
        key = (sku, category)
        entry = sku_votes.setdefault(key, {"usd": 0.0, "count": 0.0})
        entry["usd"] += to_float(row.get("effective_usd"), 0.0)
        entry["count"] += 1.0

    best_sku_map: dict[str, tuple[str, float, float]] = {}
    for (sku, category), stats in sku_votes.items():
        current = best_sku_map.get(sku)
        if current is None or stats["usd"] > current[1]:
            best_sku_map[sku] = (category, stats["usd"], stats["count"])

    sku_proposals = sorted(
        [
            {"sku_code": sku, "category": value[0], "usd": value[1], "count": value[2]}
            for sku, value in best_sku_map.items()
        ],
        key=lambda row: (-row["usd"], row["sku_code"]),
    )

    brand_votes: dict[str, dict[str, float]] = {}
    for row in llm_rows:
        confidence = to_float(row.get("confidence"), 0.0)
        llm_brand = to_str(row.get("llm_brand"), "unknown").lower()
        llm_category = to_str(row.get("llm_category"), "unknown")
        if confidence < 0.85 or llm_brand in {"", "unknown"} or llm_category == "unknown":
            continue
        brand_votes.setdefault(llm_brand, {})
        brand_votes[llm_brand][llm_category] = brand_votes[llm_brand].get(llm_category, 0.0) + to_float(
            row.get("effective_usd"), 0.0
        )

    brand_proposals: list[dict[str, Any]] = []
    for brand, categories in brand_votes.items():
        if brand in BRAND_CATEGORY_MAP:
            continue
        if len(categories) != 1:
            continue
        category, usd = next(iter(categories.items()))
        brand_proposals.append({"brand": brand, "category": category, "usd": usd})
    brand_proposals = sorted(brand_proposals, key=lambda row: (-row["usd"], row["brand"]))

    existing_markers = {marker.lower() for markers in CATEGORY_KEYWORDS.values() for marker in markers}
    token_pattern = re.compile(r"[A-Za-zА-Яа-я0-9]{4,}")

    covered_skus = {row["sku_code"] for row in sku_proposals}
    covered_brands = {row["brand"] for row in brand_proposals}
    keyword_votes: dict[tuple[str, str], dict[str, float]] = {}
    for row in llm_rows:
        confidence = to_float(row.get("confidence"), 0.0)
        if confidence < 0.85:
            continue
        if to_str(row.get("category_engine"), "unknown") != "unknown":
            continue
        llm_category = to_str(row.get("llm_category"), "unknown")
        if llm_category in {"unknown", "toxic_fake"}:
            continue
        sku_code = to_str(row.get("sku_code"))
        llm_brand = to_str(row.get("llm_brand"), "unknown").lower()
        if sku_code in covered_skus or llm_brand in covered_brands:
            continue
        text = to_str(row.get("full_row_text")).lower()
        tokens = token_pattern.findall(text)
        for token in tokens:
            if token.isdigit() or token in existing_markers:
                continue
            key = (llm_category, token)
            entry = keyword_votes.setdefault(key, {"usd": 0.0, "count": 0.0})
            entry["usd"] += to_float(row.get("effective_usd"), 0.0)
            entry["count"] += 1.0

    keyword_proposals = sorted(
        [
            {"category": category, "token": token, "usd": stats["usd"], "count": stats["count"]}
            for (category, token), stats in keyword_votes.items()
            if stats["count"] >= 2.0
        ],
        key=lambda row: (-row["usd"], row["category"], row["token"]),
    )

    risk_flags = sorted(
        [
            row
            for row in llm_rows
            if to_str(row.get("llm_category"), "unknown") != to_str(row.get("category_engine"), "unknown")
            and to_float(row.get("confidence"), 0.0) < 0.7
        ],
        key=lambda row: (-to_float(row.get("effective_usd"), 0.0), to_str(row.get("lot_id")), int(to_float(row.get("slice_rank"), 0.0))),
    )

    lines.append("## Patch Pack Proposal")
    lines.append("")
    lines.append("### a) SKU_LOOKUP candidates (sku_code -> category)")
    lines.append("")
    if sku_proposals:
        for proposal in sku_proposals[:25]:
            lines.append(
                f"- `{proposal['sku_code']}` -> `{proposal['category']}` "
                f"(affected_usd={proposal['usd']:.2f}, rows={int(proposal['count'])})"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("### b) BRAND_CATEGORY_MAP additions (high-confidence single-category)")
    lines.append("")
    if brand_proposals:
        for proposal in brand_proposals:
            lines.append(
                f"- `{proposal['brand']}` -> `{proposal['category']}` (affected_usd={proposal['usd']:.2f})"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("### c) Keyword additions (only where needed)")
    lines.append("")
    if keyword_proposals:
        for proposal in keyword_proposals[:20]:
            lines.append(
                f"- `{proposal['token']}` -> `{proposal['category']}` "
                f"(affected_usd={proposal['usd']:.2f}, rows={int(proposal['count'])})"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Risk Flags")
    lines.append("")
    lines.append("Rows where LLM disagrees with confidence < 0.7 (excluded from proposals):")
    lines.append("")
    if risk_flags:
        lines.append("| lot_id | slice_rank | sku_code | engine_category | llm_category | confidence | effective_usd |")
        lines.append("|---:|---:|---|---|---|---:|---:|")
        for row in risk_flags[:50]:
            lines.append(
                f"| {to_str(row.get('lot_id'))} | {int(to_float(row.get('slice_rank'), 0.0))} | "
                f"{to_str(row.get('sku_code'))} | {to_str(row.get('category_engine'), 'unknown')} | "
                f"{to_str(row.get('llm_category'), 'unknown')} | {to_float(row.get('confidence'), 0.0):.2f} | "
                f"{to_float(row.get('effective_usd'), 0.0):.2f} |"
            )
    else:
        lines.append("- none")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid Audit Mode for Category Engine v2.")
    parser.add_argument("--input", default="honeywell.xlsx", help="Path to source xlsx file.")
    parser.add_argument(
        "--audits-dir",
        default="scripts/lot_scoring/audits",
        help="Output directory for audit artifacts.",
    )
    parser.add_argument(
        "--value-pct",
        type=float,
        default=80.0,
        help="Target value percentage for value-slice (default: 80).",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=50,
        help="Maximum rows in value-slice per lot (default: 50).",
    )
    parser.add_argument(
        "--llm-only",
        action="store_true",
        help="Skip ranking; run LLM audit using existing CSV artifacts in audits_dir.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    audits_dir = Path(args.audits_dir)
    audits_dir.mkdir(parents=True, exist_ok=True)

    ranking_summary_path = audits_dir / "ranking_summary.csv"
    category_audit_path = audits_dir / "category_audit.csv"
    value_slice_rows_path = audits_dir / "value_slice_rows.csv"
    llm_results_path = audits_dir / "llm_audit_results.json"
    delta_report_path = audits_dir / "delta_report.md"
    llm_raw_dir = audits_dir / "llm_raw_responses"

    merge_stats: dict[str, float] = {}
    if args.llm_only:
        ranked_rows = _load_ranked_rows_from_audits_csv(
            ranking_summary_path=ranking_summary_path,
            category_audit_path=category_audit_path,
        )
        value_slice_rows = _read_value_slice_rows(value_slice_rows_path)
    else:
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        run_full_ranking(input_path, audits_dir)
        ranked_rows, category_rows, value_slice_rows, merge_stats = _compute_all_lots(
            input_path,
            value_pct=args.value_pct,
            max_rows=args.max_rows,
        )

        ranking_export_rows = [
            {
                "rank": row["rank"],
                "lot_id": row["lot_id"],
                "score_10": f"{row['score_10']:.2f}",
                "cqr": f"{row['cqr']:.6f}",
                "core_ratio": f"{row['core_ratio']:.6f}",
                "total_effective_usd": f"{row['total_effective_usd']:.2f}",
                "toxic_anchor": "YES" if row["toxic_anchor"] else "NO",
                "top3_capital_map": _format_top3(row["top3_capital_map"]),
            }
            for row in ranked_rows
        ]
        _write_csv(
            ranking_summary_path,
            fieldnames=[
                "rank",
                "lot_id",
                "score_10",
                "cqr",
                "core_ratio",
                "total_effective_usd",
                "toxic_anchor",
                "top3_capital_map",
            ],
            rows=ranking_export_rows,
        )

        category_export_rows = [
            {
                "lot_id": row["lot_id"],
                "fire_safety_pct": f"{_to_pct(row['fire_safety_pct']):.4f}",
                "gas_safety_pct": f"{_to_pct(row['gas_safety_pct']):.4f}",
                "construction_supplies_pct": f"{_to_pct(row['construction_supplies_pct']):.4f}",
                "unknown_pct": f"{_to_pct(row['unknown_pct']):.4f}",
                "other_pct": f"{_to_pct(row['other_pct']):.4f}",
            }
            for row in category_rows
        ]
        _write_csv(
            category_audit_path,
            fieldnames=[
                "lot_id",
                "fire_safety_pct",
                "gas_safety_pct",
                "construction_supplies_pct",
                "unknown_pct",
                "other_pct",
            ],
            rows=category_export_rows,
        )

        value_slice_export_rows = [
            {
                "lot_id": row["lot_id"],
                "slice_rank": row["slice_rank"],
                "sku_code": row["sku_code"],
                "qty": f"{to_float(row['qty']):.6f}",
                "effective_usd": f"{to_float(row['effective_usd']):.6f}",
                "category_engine": row["category_engine"],
                "brand_engine": row["brand_engine"],
                "raw_text": row["raw_text"],
                "full_row_text": row["full_row_text"],
            }
            for row in value_slice_rows
        ]
        _write_csv(
            value_slice_rows_path,
            fieldnames=[
                "lot_id",
                "slice_rank",
                "sku_code",
                "qty",
                "effective_usd",
                "category_engine",
                "brand_engine",
                "raw_text",
                "full_row_text",
            ],
            rows=value_slice_export_rows,
        )

    selected_lots = _select_lots_for_llm(ranked_rows)
    print(
        f"[DEBUG] About to call run_llm_audit: lots={len(selected_lots)}, "
        f"value_slice_csv={value_slice_rows_path}",
        flush=True,
    )
    llm_result = run_llm_audit(
        value_slice_csv_path=value_slice_rows_path,
        selected_lots=selected_lots,
        output_json_path=llm_results_path,
        raw_output_dir=llm_raw_dir,
    )

    _build_delta_report(
        output_path=delta_report_path,
        ranked_rows=ranked_rows,
        value_slice_rows=value_slice_rows,
        llm_result=llm_result,
    )

    summary_payload = {
        "input": str(input_path),
        "audits_dir": str(audits_dir),
        "lots_count": len(ranked_rows),
        "merge_stats": merge_stats,
        "selected_lots_for_llm": selected_lots,
        "llm_status": to_str(llm_result.get("status")),
        "artifacts": {
            "ranking_summary_csv": str(ranking_summary_path),
            "category_audit_csv": str(category_audit_path),
            "value_slice_rows_csv": str(value_slice_rows_path),
            "llm_audit_results_json": str(llm_results_path),
            "delta_report_md": str(delta_report_path),
        },
        "top5_by_score_10": [
            {
                "rank": row["rank"],
                "lot_id": row["lot_id"],
                "score_10": row["score_10"],
                "cqr": row["cqr"],
            }
            for row in ranked_rows[:5]
        ],
        "top5_by_unknown_pct": [
            {
                "lot_id": row["lot_id"],
                "unknown_pct": row["unknown_pct"],
                "score_10": row["score_10"],
            }
            for row in sorted(ranked_rows, key=lambda row: (-row["unknown_pct"], -row["total_effective_usd"]))[:5]
        ],
    }
    print("===HYBRID_AUDIT_SUMMARY_START===")
    print(json.dumps(summary_payload, ensure_ascii=False, indent=2))
    print("===HYBRID_AUDIT_SUMMARY_END===")


if __name__ == "__main__":
    main()


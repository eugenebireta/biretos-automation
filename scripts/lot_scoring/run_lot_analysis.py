from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

from scripts.lot_scoring.cdm import LotRecord
from scripts.lot_scoring.cqr import CQRResult, compute_cqr
from scripts.lot_scoring.etl import ETLInvariantError, EtlConfig, run_etl_pipeline
from scripts.lot_scoring.pipeline.helpers import to_float
from scripts.lot_scoring.pipeline.score import apply_base_score, apply_final_score
from scripts.lot_scoring.run_config import RunConfig
from scripts.lot_scoring.run_full_ranking_v341 import (
    REPORT_FILENAMES,
    _column_map,
    _compute_confidence,
    _load_reference_maps,
    _load_rows_by_lot,
    _load_rows_by_lot_with_report_merge,
    _lot_sort_key,
    _resolve_enriched_source_path,
)
from scripts.lot_scoring.capital_map import CapitalMapResult, compute_capital_map
from scripts.lot_scoring.volume_profile import VolumeProfileResult, compute_volume_profile


def _parse_lots(raw_lots: str) -> list[str]:
    parsed: list[str] = []
    for chunk in raw_lots.split(","):
        lot = chunk.strip()
        if lot and lot not in parsed:
            parsed.append(lot)
    return parsed


def _line_effective_usd(sku: dict) -> float:
    q_has_qty = sku.get("q_has_qty")
    has_qty = q_has_qty is not False
    has_line = sku.get("effective_line_usd") is not None
    if not (has_qty and has_line):
        return 0.0
    return max(0.0, to_float(sku.get("effective_line_usd"), 0.0))


def _core_sort_key(sku: dict) -> tuple:
    return (
        -_line_effective_usd(sku),
        str(sku.get("sku_code_normalized", "")),
        str(sku.get("row_index", "")),
    )


def _build_top_core_slice(
    core_skus: list[dict],
    top_pct: float,
    max_rows: int,
) -> tuple[list[dict], float]:
    ranked_core = sorted(core_skus, key=_core_sort_key)
    if not ranked_core:
        return [], 0.0

    target_count = max(1, int(math.ceil(len(ranked_core) * top_pct / 100.0)))
    slice_count = min(max_rows, target_count)
    top_core_skus = ranked_core[:slice_count]
    top_core_value = sum(_line_effective_usd(sku) for sku in top_core_skus)
    return top_core_skus, top_core_value


def _build_value_based_slice(
    core_skus: list[dict],
    total_core_value_usd: float,
    value_pct: float,
    max_rows: int,
) -> list[dict]:
    ranked_core = sorted(core_skus, key=_core_sort_key)
    if not ranked_core:
        return []
    target_value = total_core_value_usd * value_pct / 100.0
    result: list[dict] = []
    cumulative = 0.0
    for sku in ranked_core:
        if len(result) >= max_rows:
            break
        result.append(sku)
        cumulative += _line_effective_usd(sku)
        if cumulative >= target_value:
            break
    return result


def _format_distribution(distribution: dict[str, float], ordered_keys: list[str]) -> str:
    return ", ".join(f"{key}={distribution.get(key, 0.0) * 100.0:.1f}%" for key in ordered_keys)


def _load_lots_for_analysis(input_path: Path) -> tuple[dict[str, list[dict]], dict[str, float]]:
    report_paths = [input_path.parent / name for name in REPORT_FILENAMES]
    enriched_path = _resolve_enriched_source_path(input_path.parent)
    merge_stats: dict[str, float] = {}

    use_report_merge = False
    if (enriched_path is not None and enriched_path.exists()) or any(path.exists() for path in report_paths):
        workbook = pd.ExcelFile(input_path)
        if len(workbook.sheet_names) > 1:
            sample_df = pd.read_excel(input_path, sheet_name=workbook.sheet_names[0], nrows=2)
            use_report_merge = "lot_id" not in _column_map(sample_df)

    if use_report_merge:
        lots, merge_stats_raw = _load_rows_by_lot_with_report_merge(
            input_path,
            report_paths,
            usd_rate=78.0,
            enriched_path=enriched_path,
        )
        merge_stats = {key: to_float(value, 0.0) for key, value in merge_stats_raw.items()}
        return lots, merge_stats
    return _load_rows_by_lot(input_path), merge_stats


def run_lot_analysis(
    input_path: Path,
    lot_ids: list[str] | None,
    top_pct: float,
    max_rows: int,
    *,
    use_value_slice: bool = True,
    value_pct: float = 80.0,
) -> None:
    (
        category_obsolescence,
        brand_score,
        category_liquidity,
        category_volume_proxy,
    ) = _load_reference_maps()

    run_config = RunConfig()
    etl_config = EtlConfig()
    lots, merge_stats = _load_lots_for_analysis(input_path)
    if not lots:
        raise ValueError("No lots detected for analysis.")

    requested = lot_ids or sorted(lots.keys(), key=_lot_sort_key)
    selected_lots = [lot_id for lot_id in requested if lot_id in lots]
    if not selected_lots:
        raise ValueError("No selected lots found in input data.")

    print(f"Detected lots: {len(lots)} | Selected: {len(selected_lots)}")
    if merge_stats:
        coverage = merge_stats.get("match_coverage", 0.0) * 100.0
        print(
            "Valuation merge: "
            f"total_rows={int(merge_stats.get('total_rows', 0.0))}, "
            f"matched={int(merge_stats.get('total_matched', 0.0))}, "
            f"coverage={coverage:.2f}%"
        )

    results: list[
        tuple[LotRecord, dict[str, float | int], float, CQRResult, VolumeProfileResult, CapitalMapResult, int, int]
    ] = []
    for lot_id in sorted(selected_lots, key=_lot_sort_key):
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

        core_ratio = to_float(assembled.metadata.get("core_ratio"), 0.0)
        confidence_score = _compute_confidence(
            lot,
            core_skus=assembled.core_skus,
            core_ratio=core_ratio,
            brand_score=brand_score,
        )

        total_core_value_usd = to_float(assembled.metadata.get("core_effective_usd"), 0.0)
        if total_core_value_usd <= 0.0:
            total_core_value_usd = sum(_line_effective_usd(sku) for sku in assembled.core_skus)

        if use_value_slice:
            top_core_skus = _build_value_based_slice(
                assembled.core_skus, total_core_value_usd, value_pct=value_pct, max_rows=max_rows,
            )
        else:
            top_core_skus, _ = _build_top_core_slice(
                assembled.core_skus, top_pct=top_pct, max_rows=max_rows,
            )

        slice_cardinality = len(top_core_skus)
        total_core_cardinality = len(assembled.core_skus)

        cqr = compute_cqr(top_core_skus, total_core_value_usd, list(lot.flags))
        volume = compute_volume_profile(assembled.core_skus)
        capital_map = compute_capital_map(top_core_skus, total_core_value_usd, top_k=5)
        results.append((
            lot, assembled.metadata, confidence_score, cqr, volume,
            capital_map, slice_cardinality, total_core_cardinality,
        ))

    for lot, metadata, confidence_score, cqr, volume, capital_map, slice_card, total_card in results:
        print("\n======================================================")
        print(f"LOT ANALYSIS: {lot.lot_id}")
        print("======================================================")

        print("\n[1] STRUCTURAL GEOMETRY (score.py + heuristics)")
        print("------------------------------------------------------")
        print(f"Score 10: {lot.score_10:.2f} / 10")
        print(f"HHI: {lot.hhi_index:.4f}")
        print(f"Core Ratio: {to_float(metadata.get('core_ratio'), 0.0) * 100.0:.2f}%")
        print(f"M_Tail: {lot.m_tail:.4f}")
        print(f"Confidence Layer: {confidence_score:.2f} / 1.00")
        print(f"ETL Flags: {', '.join(lot.flags) if lot.flags else '-'}")
        print(
            f"Volume Profile: VCI={volume.vci:.3f}, confidence={volume.confidence}, "
            f"classified={volume.classified_count}/{volume.total_count}"
        )
        print(
            "Volume Distribution: "
            + _format_distribution(volume.distribution, ["SMALL", "MEDIUM", "LARGE", "UNKNOWN"])
        )
        print(f"Volume Flags: {', '.join(volume.flags) if volume.flags else '-'}")

        print("\n[2] CAPITAL PURITY / CQR")
        print("------------------------------------------------------")
        print(f"CQR Score: {cqr.cqr_score:.3f}")
        print(f"CQR Confidence: {cqr.cqr_confidence}")
        print(f"Representativeness: {cqr.representativeness_ratio * 100.0:.2f}%")
        print(f"Toxic Anchor: {'YES' if cqr.toxic_anchor_flag else 'NO'}")
        print(
            "Demand Distribution: "
            + _format_distribution(
                cqr.demand_type_distribution,
                [
                    "REGULATED_PROJECT",
                    "COMPATIBILITY_LOCK",
                    "COMMODITY",
                    "CONSUMABLE",
                    "OBSOLESCENCE_RISK",
                    "UNKNOWN",
                ],
            )
        )
        print(f"CQR Flags: {', '.join(cqr.flags) if cqr.flags else '-'}")

        print("\n[3] CAPITAL MAP (Category Distribution)")
        print("------------------------------------------------------")
        slice_flags: list[str] = list(capital_map.flags)
        if slice_card < 10 and total_card > 0 and (slice_card / total_card) < 0.10:
            slice_flags.append("SLICE:LOW_CARDINALITY")
        print(
            f"Analyzed Slice: {slice_card} of {total_card} SKUs "
            f"(${capital_map.analyzed_value_usd:,.2f} = "
            f"{capital_map.analyzed_share_of_core * 100.0:.2f}% of Core)"
        )
        print("Top Categories (by value):")
        for cat_name, cat_share in capital_map.top_categories:
            print(f"  {cat_name.upper()}={cat_share * 100.0:.1f}%")
        print(f"Capital Map Flags: {', '.join(slice_flags) if slice_flags else '-'}")

        print("\n[4] MARKET PULSE (Placeholder)")
        print("------------------------------------------------------")
        print("Market Pulse is a separate informational layer and is not included in score_10.")
        print("Planned fields: liquidity snapshots, RFQ velocity, channel fit, and macro trend notes.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified Lot Analysis v3.5 (Structural + CQR + Volume + Capital Map)."
    )
    parser.add_argument("--input", required=True, help="Path to input Excel file.")
    parser.add_argument(
        "--lots",
        default="",
        help='Optional comma-separated list of lot IDs (example: "10,3,16,14").',
    )
    parser.add_argument(
        "--top-pct",
        type=float,
        default=None,
        help="(Legacy) Top percentage of core SKU count for CQR slice. If set, forces count-based mode.",
    )
    parser.add_argument(
        "--value-pct",
        type=float,
        default=80.0,
        help="Target value percentage for Pareto slice (default: 80.0). Used in value-slice mode.",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=50,
        help="Hard cap for top core slice row count (default: 50).",
    )
    args = parser.parse_args()

    use_value_slice = args.top_pct is None
    top_pct = args.top_pct if args.top_pct is not None else 20.0

    if use_value_slice:
        if args.value_pct <= 0.0 or args.value_pct > 100.0:
            raise ValueError("--value-pct must be within (0, 100].")
    else:
        if top_pct <= 0.0 or top_pct > 100.0:
            raise ValueError("--top-pct must be within (0, 100].")
    if args.max_rows <= 0:
        raise ValueError("--max-rows must be > 0.")

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    lot_ids = _parse_lots(args.lots) if args.lots else None
    run_lot_analysis(
        input_path=input_path,
        lot_ids=lot_ids,
        top_pct=top_pct,
        max_rows=args.max_rows,
        use_value_slice=use_value_slice,
        value_pct=args.value_pct,
    )


if __name__ == "__main__":
    main()

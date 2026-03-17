from __future__ import annotations

import argparse
import re
import sys
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.lot_scoring.pipeline.helpers import to_float, to_str
from scripts.lot_scoring.run_full_ranking_v341 import _detect_enriched_columns, _match_columns_by_tokens

LOT_COLUMN_TOKENS = ("sheetname", "lot_id", "lotid", "lot", "лот")
PARETO_THRESHOLDS = (0.50, 0.80, 0.90, 0.95)
BALLAST_LINE_VALUE_RUB = 5_000.0
DEFAULT_USD_RATE = 78.0


def _first_non_empty_text(values: list[Any]) -> str:
    for value in values:
        text = to_str(value)
        if text:
            return text
    return ""


def _normalize_lot_id(value: object) -> str:
    text = to_str(value)
    if not text:
        return ""
    match = re.search(r"\d+", text)
    if match:
        return str(int(match.group(0)))
    return text


def _normalize_pn(value: object) -> str:
    text = to_str(value).upper()
    text = text.replace(" ", "").replace("\u00a0", "")
    return re.sub(r"[^A-Z0-9]", "", text)


def _truncate(text: str, max_len: int = 120) -> str:
    clean = _safe_terminal_text(to_str(text).replace("|", "/"))
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3] + "..."


def _safe_terminal_text(text: str) -> str:
    encoding = sys.stdout.encoding or "utf-8"
    return to_str(text).encode(encoding, errors="replace").decode(encoding, errors="replace")


def _fmt_int(value: int) -> str:
    return f"{value:,}"


def _fmt_float(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}"


def _parse_lots(raw: str) -> list[str]:
    parsed: list[str] = []
    for chunk in raw.split(","):
        lot = _normalize_lot_id(chunk)
        if lot and lot not in parsed:
            parsed.append(lot)
    return parsed


def _lot_sort_key(lot_id: str) -> tuple[int, str]:
    if lot_id.isdigit():
        return (int(lot_id), lot_id)
    return (10**9, lot_id)


def _extract_rows_by_lot(input_path: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, str | None]]]:
    workbook = pd.ExcelFile(input_path)
    rows_by_lot: dict[str, list[dict[str, Any]]] = {}
    detected_by_sheet: dict[str, dict[str, str | None]] = {}

    for sheet_name in workbook.sheet_names:
        sheet_df = pd.read_excel(input_path, sheet_name=sheet_name).dropna(how="all")
        if sheet_df.empty:
            continue

        mapping = _detect_enriched_columns(sheet_df)
        lot_candidates = _match_columns_by_tokens(sheet_df, LOT_COLUMN_TOKENS)
        lot_col = lot_candidates[0] if lot_candidates else None
        detected_by_sheet[to_str(sheet_name)] = {
            "lot_col": lot_col,
            "pn_col": mapping.get("pn_col"),
            "qty_col": mapping.get("qty_col"),
            "unit_price_col": mapping.get("unit_price_col"),
            "line_value_col": mapping.get("line_value_col"),
            "raw_text_col": mapping.get("raw_text_col"),
        }

        pn_col = mapping.get("pn_col")
        qty_col = mapping.get("qty_col")
        unit_price_col = mapping.get("unit_price_col")
        line_value_col = mapping.get("line_value_col")
        raw_text_col = mapping.get("raw_text_col")
        if pn_col is None:
            continue

        for _, row in sheet_df.iterrows():
            lot_source = row.get(lot_col) if lot_col else sheet_name
            lot_id = _normalize_lot_id(lot_source) or _normalize_lot_id(sheet_name)
            if not lot_id:
                continue

            pn_raw = row.get(pn_col)
            pn_text = to_str(pn_raw)
            pn_key = _normalize_pn(pn_raw)
            if not pn_key:
                continue

            qty = max(0.0, to_float(row.get(qty_col), 0.0)) if qty_col else 0.0
            unit_price_rub = max(0.0, to_float(row.get(unit_price_col), 0.0)) if unit_price_col else 0.0
            line_value_rub = max(0.0, to_float(row.get(line_value_col), 0.0)) if line_value_col else 0.0

            if line_value_rub <= 0.0 and unit_price_rub > 0.0 and qty > 0.0:
                line_value_rub = unit_price_rub * qty
            if unit_price_rub <= 0.0 and line_value_rub > 0.0 and qty > 0.0:
                unit_price_rub = line_value_rub / qty
            if line_value_rub <= 0.0:
                continue

            raw_text = to_str(row.get(raw_text_col), "") if raw_text_col else ""
            if not raw_text:
                raw_text = _first_non_empty_text(list(row.values))

            rows_by_lot.setdefault(lot_id, []).append(
                {
                    "lot_id": lot_id,
                    "pn_raw": pn_text or pn_key,
                    "pn_key": pn_key,
                    "raw_text": raw_text,
                    "qty": qty,
                    "unit_price_rub": unit_price_rub,
                    "line_value_rub": line_value_rub,
                }
            )

    return rows_by_lot, detected_by_sheet


def _pareto_curve(sorted_rows: list[dict[str, Any]], total_value_rub: float) -> dict[float, tuple[int, float]]:
    curve: dict[float, tuple[int, float]] = {}
    if total_value_rub <= 0.0:
        for threshold in PARETO_THRESHOLDS:
            curve[threshold] = (0, 0.0)
        return curve

    cumulative = 0.0
    threshold_idx = 0
    targets = list(PARETO_THRESHOLDS)
    for idx, row in enumerate(sorted_rows, start=1):
        cumulative += to_float(row.get("line_value_rub"), 0.0)
        share = cumulative / total_value_rub
        while threshold_idx < len(targets) and share >= targets[threshold_idx]:
            curve[targets[threshold_idx]] = (idx, cumulative)
            threshold_idx += 1

    for threshold in PARETO_THRESHOLDS:
        if threshold not in curve:
            curve[threshold] = (len(sorted_rows), cumulative)
    return curve


def _ticket_band(unit_price_usd: float) -> str:
    if unit_price_usd > 500.0:
        return "Premium"
    if unit_price_usd >= 50.0:
        return "Mid-range"
    return "Mass"


def _print_lot_report(
    lot_id: str,
    lot_rows: list[dict[str, Any]],
    *,
    top_pct: float,
    max_rows: int,
    usd_rate: float,
) -> tuple[set[str], list[str]]:
    sorted_rows = sorted(lot_rows, key=lambda row: to_float(row.get("line_value_rub"), 0.0), reverse=True)
    total_rows = len(sorted_rows)
    total_value_rub = sum(to_float(row.get("line_value_rub"), 0.0) for row in sorted_rows)
    top_n = min(max(1, int(total_rows * (top_pct / 100.0))), max_rows)
    top_rows = sorted_rows[:top_n]
    top_value_rub = sum(to_float(row.get("line_value_rub"), 0.0) for row in top_rows)
    top_share_pct = (top_value_rub / total_value_rub * 100.0) if total_value_rub > 0 else 0.0
    curve = _pareto_curve(sorted_rows, total_value_rub)

    ballast_rows = [row for row in sorted_rows if to_float(row.get("line_value_rub"), 0.0) < BALLAST_LINE_VALUE_RUB]
    ballast_sku_count = len(ballast_rows)
    ballast_value_rub = sum(to_float(row.get("line_value_rub"), 0.0) for row in ballast_rows)
    ballast_pct = (ballast_value_rub / total_value_rub * 100.0) if total_value_rub > 0 else 0.0

    band_stats: dict[str, dict[str, float]] = {
        "Premium": {"count": 0.0, "value_rub": 0.0},
        "Mid-range": {"count": 0.0, "value_rub": 0.0},
        "Mass": {"count": 0.0, "value_rub": 0.0},
    }

    print(f"\n## LOT {lot_id} | {_fmt_int(total_rows)} SKU | Total: {_fmt_float(total_value_rub, 2)} RUB")
    print("\n### Pareto Curve")
    print("| Threshold | SKU Count | Cumulative Value |")
    print("|-----------|-----------|------------------|")
    for threshold in PARETO_THRESHOLDS:
        count, cumulative = curve[threshold]
        print(f"| {int(threshold * 100)}% | {_fmt_int(count)} | {_fmt_float(cumulative, 2)} RUB |")

    print("\n### Ballast")
    print(
        "ballast_sku_count="
        f"{_fmt_int(ballast_sku_count)}, ballast_value={_fmt_float(ballast_value_rub, 2)} RUB ({ballast_pct:.2f}%)"
    )

    for row in top_rows:
        qty = to_float(row.get("qty"), 0.0)
        unit_price_rub = to_float(row.get("unit_price_rub"), 0.0)
        if unit_price_rub <= 0.0 and qty > 0.0:
            unit_price_rub = to_float(row.get("line_value_rub"), 0.0) / qty
        unit_price_usd = unit_price_rub / usd_rate if usd_rate > 0 else 0.0
        band = _ticket_band(unit_price_usd)
        band_stats[band]["count"] += 1.0
        band_stats[band]["value_rub"] += to_float(row.get("line_value_rub"), 0.0)
        row["unit_price_rub"] = unit_price_rub
        row["ticket_band"] = band

    print("\n### Unit Economics (Top Core)")
    print("| Band | SKU Count | Value (RUB) | Share |")
    print("|------|-----------|-------------|-------|")
    for band in ("Premium", "Mid-range", "Mass"):
        count = int(band_stats[band]["count"])
        value_rub = band_stats[band]["value_rub"]
        share = (value_rub / top_value_rub * 100.0) if top_value_rub > 0 else 0.0
        print(f"| {band} | {_fmt_int(count)} | {_fmt_float(value_rub, 2)} | {share:.2f}% |")

    print(f"\n### Top {top_pct:.1f}% Core ({_fmt_int(len(top_rows))} positions, {top_share_pct:.2f}% of lot value)")
    print("| # | SKU | Description (120 chars) | Qty | Unit RUB | Line RUB | Ticket |")
    print("|---|-----|--------------------------|-----|----------|----------|--------|")
    for idx, row in enumerate(top_rows, start=1):
        qty = to_float(row.get("qty"), 0.0)
        qty_text = f"{int(qty)}" if abs(qty - round(qty)) < 1e-9 else f"{qty:.2f}"
        print(
            "| "
            f"{idx} | {_safe_terminal_text(to_str(row.get('pn_raw'), row.get('pn_key')))} | "
            f"{_truncate(to_str(row.get('raw_text')))} | "
            f"{qty_text} | {_fmt_float(to_float(row.get('unit_price_rub'), 0.0), 2)} | "
            f"{_fmt_float(to_float(row.get('line_value_rub'), 0.0), 2)} | {to_str(row.get('ticket_band'))} |"
        )

    core_pn_set = {to_str(row.get("pn_key")) for row in top_rows if to_str(row.get("pn_key"))}
    top5: list[str] = []
    seen: set[str] = set()
    for row in top_rows:
        pn_key = to_str(row.get("pn_key"))
        if not pn_key or pn_key in seen:
            continue
        seen.add(pn_key)
        top5.append(pn_key)
        if len(top5) == 5:
            break
    return core_pn_set, top5


def main() -> None:
    parser = argparse.ArgumentParser(description="Universal Pareto core extractor for lot structure analysis.")
    parser.add_argument("--input", required=True, help="Path to enriched Excel file.")
    parser.add_argument("--lots", default="", help="Comma-separated lot IDs. Default: analyze all lots.")
    parser.add_argument("--top-pct", type=float, default=20.0, help="Top percentage per lot (default: 20).")
    parser.add_argument("--max-rows", type=int, default=50, help="Hard limit of rows per lot in output (default: 50).")
    parser.add_argument("--usd-rate", type=float, default=DEFAULT_USD_RATE, help="RUB/USD conversion rate (default: 78).")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if args.top_pct <= 0 or args.top_pct > 100:
        raise ValueError("--top-pct must be within (0, 100].")
    if args.max_rows <= 0:
        raise ValueError("--max-rows must be > 0.")

    rows_by_lot, detected_by_sheet = _extract_rows_by_lot(input_path)
    if not rows_by_lot:
        raise ValueError("No priced rows were extracted from input.")

    print(f"# Pareto Core Extractor | Source: {input_path.name}")
    print("\n## Detected Column Mapping")
    print("| Sheet | lot_col | pn_col | qty_col | unit_price_col | line_value_col | raw_text_col |")
    print("|-------|---------|--------|---------|----------------|----------------|--------------|")
    for sheet in sorted(detected_by_sheet.keys()):
        mapping = detected_by_sheet[sheet]
        print(
            f"| {sheet} | {to_str(mapping.get('lot_col')) or '-'} | {to_str(mapping.get('pn_col')) or '-'} | "
            f"{to_str(mapping.get('qty_col')) or '-'} | {to_str(mapping.get('unit_price_col')) or '-'} | "
            f"{to_str(mapping.get('line_value_col')) or '-'} | {to_str(mapping.get('raw_text_col')) or '-'} |"
        )

    selected_lots = _parse_lots(args.lots) if args.lots else sorted(rows_by_lot.keys(), key=_lot_sort_key)
    missing = [lot for lot in selected_lots if lot not in rows_by_lot]
    if missing:
        print(f"\nWARNING: requested lots not found: {', '.join(missing)}")
    selected_lots = [lot for lot in selected_lots if lot in rows_by_lot]
    if not selected_lots:
        raise ValueError("No lots selected for analysis.")

    print(f"\n## Selected Lots\n{', '.join(selected_lots)}")
    print(f"\n## Config\ntop_pct={args.top_pct:.1f}, max_rows={args.max_rows}, usd_rate={args.usd_rate:.2f}")

    core_sets: dict[str, set[str]] = {}
    top5_by_lot: dict[str, list[str]] = {}
    for lot_id in selected_lots:
        core_set, top5 = _print_lot_report(
            lot_id,
            rows_by_lot[lot_id],
            top_pct=args.top_pct,
            max_rows=args.max_rows,
            usd_rate=args.usd_rate,
        )
        core_sets[lot_id] = core_set
        top5_by_lot[lot_id] = top5

    if len(selected_lots) > 1:
        print("\n## CROSS-LOT OVERLAP")
        for left, right in combinations(selected_lots, 2):
            left_set = core_sets.get(left, set())
            right_set = core_sets.get(right, set())
            shared = left_set.intersection(right_set)
            base = min(len(left_set), len(right_set)) or 1
            overlap_pct = len(shared) / base * 100.0
            print(
                f"Lot {left} vs Lot {right}: {len(shared)} shared SKU ({overlap_pct:.2f}% of smaller core set)"
            )

    print("\n## TOP-5 SKU BY LOT (for web validation)")
    for lot_id in selected_lots:
        top5 = top5_by_lot.get(lot_id, [])
        print(f"Lot {lot_id}: {', '.join(top5) if top5 else '-'}")


if __name__ == "__main__":
    main()

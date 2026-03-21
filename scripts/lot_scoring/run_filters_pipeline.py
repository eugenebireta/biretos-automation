from __future__ import annotations

import argparse
from pathlib import Path

from scripts.lot_scoring.filters.engine import run_filters


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute Engine v3 protocol filters runner.")
    parser.add_argument("--input", required=True, help="Path to input workbook (honeywell.xlsx).")
    parser.add_argument("--usd-rate", required=True, type=float, help="USD/RUB rate. Required, no defaults.")
    parser.add_argument(
        "--entry-price-rub",
        required=False,
        type=float,
        default=None,
        help="EntryPrice in RUB. If omitted: F2=REVIEW NEEDS_ENTRYPRICE, F3=0.",
    )
    parser.add_argument(
        "--output-dir",
        required=False,
        default="downloads/lots",
        help="Output directory for summary/artifacts.",
    )
    parser.add_argument(
        "--filter4-top-n",
        required=False,
        type=int,
        default=5,
        help="Top-N lots by score_100 for Filter 4 candidate flag.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    result = run_filters(
        input_path=Path(args.input),
        usd_rate=float(args.usd_rate),
        entry_price_rub=float(args.entry_price_rub) if args.entry_price_rub is not None else None,
        output_dir=Path(args.output_dir),
        filter4_top_n=int(args.filter4_top_n),
    )
    print(f"Summary: {result['summary_path']}")
    print(f"Output dir: {result['output_dir']}")
    print(f"Lots processed: {result['lots_count']}")
    print(f"Filter4 candidates: {result['candidate_count']}")


if __name__ == "__main__":
    main()

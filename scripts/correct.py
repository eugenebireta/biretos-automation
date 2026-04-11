"""correct.py — CLI entrypoint for human corrections to enrichment data.

Records corrections via correction_logger.log_correction() so they flow into
the experience log for training local AI and auditing enrichment quality.

Usage:
  python scripts/correct.py --pn 153711 --field expected_category \\
      --old "Датчик" --new "Рамки PEHA" --reason "PEHA electrical item"

  python scripts/correct.py --pn 185191 --field price \\
      --old 450.0 --new 45.0 --reason "pack price not unit" \\
      --source dr_gemini --ai-model gemini-2.5-pro

All corrections are written to shadow_log/experience_YYYY-MM.jsonl with
salience_score=9 (highest priority for training).

Fields:
  --pn           Part number (required)
  --field        Field that was wrong, e.g. expected_category, price, description (required)
  --old          Original wrong value (required)
  --new          Corrected value (required)
  --reason       Why the original was wrong (required)
  --brand        Brand name (default: Honeywell)
  --source       Where the wrong value came from (e.g. dr_gemini, photo_pipeline)
  --trace-id     Pipeline run trace ID
  --ai-model     Which AI model produced the wrong value
  --ai-output    Raw AI output that was wrong (capped at 2000 chars)
  --corrected-by Who made the correction (default: owner)
  --json         Output the written record as JSON
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from correction_logger import log_correction  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Record a human correction to enrichment data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--pn", required=True, help="Part number")
    p.add_argument("--field", required=True, help="Field corrected (e.g. expected_category, price)")
    p.add_argument("--old", required=True, help="Original wrong value")
    p.add_argument("--new", required=True, help="Corrected value")
    p.add_argument("--reason", required=True, help="Why the original was wrong")
    p.add_argument("--brand", default="Honeywell", help="Brand (default: Honeywell)")
    p.add_argument("--source", default=None, help="Source of wrong value (e.g. dr_gemini)")
    p.add_argument("--trace-id", default=None, help="Pipeline trace ID")
    p.add_argument("--ai-model", default=None, help="AI model that produced wrong value")
    p.add_argument("--ai-output", default=None, help="Raw AI output (capped 2000 chars)")
    p.add_argument("--corrected-by", default="owner", help="Who corrected (default: owner)")
    p.add_argument("--json", action="store_true", help="Output written record as JSON")
    return p


def run_correction(args: argparse.Namespace) -> dict:
    """Execute correction and return the record metadata."""
    log_correction(
        pn=args.pn,
        brand=args.brand,
        field_corrected=args.field,
        original_value=args.old,
        corrected_value=args.new,
        reason=args.reason,
        corrected_by=args.corrected_by,
        trace_id=args.trace_id,
        source=args.source,
        ai_model=args.ai_model,
        ai_output_raw=args.ai_output,
    )
    return {
        "status": "ok",
        "pn": args.pn,
        "field": args.field,
        "old": args.old,
        "new": args.new,
        "reason": args.reason,
        "source": args.source,
        "corrected_by": args.corrected_by,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = run_correction(args)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"[CORRECTION] {result['pn']}: {args.field} "
            f"'{args.old}' -> '{args.new}' ({args.reason})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

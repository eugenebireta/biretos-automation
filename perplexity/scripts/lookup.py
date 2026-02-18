"""
CLI-скрипт для запуска Perplexity product lookup.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Dict

from dotenv import load_dotenv

from src.product_lookup import lookup_product


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ищет информацию о продукте через Perplexity (OpenRouter)."
    )
    parser.add_argument("--brand", required=True, help="Название бренда (например, ABB).")
    parser.add_argument("--pn", required=True, help="Part number / артикул.")
    return parser.parse_args()


async def _run_lookup(brand: str, pn: str) -> Dict[str, Any]:
    return await lookup_product(brand=brand, pn=pn)


def main() -> int:
    load_dotenv()
    args = _parse_args()

    try:
        result = asyncio.run(_run_lookup(args.brand, args.pn))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        # На всякий случай защищаемся даже от неожиданных ошибок.
        result = {
            "corrected_part_number": None,
            "model": None,
            "product_type": None,
            "image_url": None,
            "description": None,
            "raw": {"error": "cli_failure", "detail": str(exc)},
        }

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



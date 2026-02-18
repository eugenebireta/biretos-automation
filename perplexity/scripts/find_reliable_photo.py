from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any, Dict

from dotenv import load_dotenv

from src.perplexity_client import PerplexityClient
from src.reliable_photo_finder import ReliablePhotoFinder


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Находит надежное фото продукта через проверенные ZAPI-поставщики."
    )
    parser.add_argument("--brand", required=True, help="Бренд продукта (например, ZAPI).")
    parser.add_argument("--pn", required=True, help="Part number / артикул.")
    return parser.parse_args()


async def _run_lookup(brand: str, pn: str) -> Dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    client = PerplexityClient(api_key=api_key or "")

    safe_brand = (brand or "").strip()
    safe_pn = (pn or "").strip()

    perplexity_result = await client.lookup(brand=safe_brand, part_number=safe_pn)

    finder = ReliablePhotoFinder()
    reliable_image = await finder.find_image(
        brand=safe_brand,
        part_number=safe_pn,
        model=perplexity_result.get("model"),
    )

    return {
        "brand": safe_brand,
        "part_number": safe_pn,
        "perplexity_result": perplexity_result,
        "reliable_image_url": reliable_image,
        "source_site": finder.last_source,
    }


def main() -> int:
    load_dotenv()
    args = _parse_args()

    try:
        result = asyncio.run(_run_lookup(args.brand, args.pn))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        result = {
            "brand": args.brand,
            "part_number": args.pn,
            "perplexity_result": None,
            "reliable_image_url": None,
            "source_site": None,
            "error": {
                "type": "cli_failure",
                "detail": str(exc),
            },
        }

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



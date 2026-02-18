from __future__ import annotations

import argparse
import asyncio

from src.product_lookup import lookup_product
from src.excel_writer import enrich_zapi_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Обогащает ZAPI.xlsx данными из Perplexity и сохраняет ZAPI_enriched.xlsx."
    )
    parser.add_argument(
        "--input",
        default="ZAPI.xlsx",
        help="Путь к входному файлу XLSX (по умолчанию ZAPI.xlsx).",
    )
    parser.add_argument(
        "--output",
        default="ZAPI_enriched.xlsx",
        help="Путь к выходному файлу XLSX (по умолчанию ZAPI_enriched.xlsx).",
    )
    parser.add_argument(
        "--pn-column",
        default="A",
        help="Буква колонки, где лежит исходный партномер (по умолчанию A).",
    )
    parser.add_argument(
        "--start-row",
        type=int,
        default=2,
        help="Строка, с которой начинать обработку (по умолчанию 2 — пропускаем заголовки).",
    )
    return parser.parse_args()


async def _run() -> None:
    args = parse_args()

    async def _lookup(brand: str, pn: str):
        return await lookup_product(brand=brand, pn=pn)

    await enrich_zapi_file(
        input_path=args.input,
        output_path=args.output,
        lookup_fn=_lookup,
        brand="ZAPI",
        pn_column=args.pn_column,
        start_row=args.start_row,
    )


if __name__ == "__main__":
    asyncio.run(_run())



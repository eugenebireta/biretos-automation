"""
Интерактивный скрипт для генерации Excel с товарами бренда через Perplexity.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Optional

from src.brand_sampler import sample_brand_products
from src.excel_writer import write_brand_samples_to_template


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Генерирует ZAPI_enriched.xlsx, автоматически находя товары бренда через Perplexity."
    )
    parser.add_argument("--brand", help="Бренд (если не указан, будет запрошен интерактивно).")
    parser.add_argument(
        "--count",
        type=int,
        help="Количество партномеров (если не указано, будет запрошено интерактивно).",
    )
    parser.add_argument(
        "--input",
        default="ZAPI.xlsx",
        help="Путь к шаблону Excel (по умолчанию ZAPI.xlsx).",
    )
    parser.add_argument(
        "--output",
        default="ZAPI_enriched.xlsx",
        help="Путь для сохранения результата (по умолчанию ZAPI_enriched.xlsx).",
    )
    parser.add_argument(
        "--start-row",
        type=int,
        default=2,
        help="Строка, с которой начинать заполнение (по умолчанию 2).",
    )
    return parser.parse_args()


async def _run_generation(
    brand: str,
    count: int,
    input_path: str,
    output_path: str,
    start_row: int,
) -> None:
    await write_brand_samples_to_template(
        brand=brand,
        count=count,
        input_path=input_path,
        output_path=output_path,
        sampler_fn=sample_brand_products,
        start_row=start_row,
    )


def _ensure_brand(value: Optional[str]) -> str:
    current = (value or "").strip()
    while not current:
        current = input("Введите бренд: ").strip()
    return current


def _ensure_count(value: Optional[int]) -> int:
    if value is not None and value > 0:
        return value

    while True:
        raw = input("Сколько партномеров сгенерировать: ").strip()
        try:
            parsed = int(raw)
        except ValueError:
            print("Введите целое число.", file=sys.stderr)
            continue
        if parsed <= 0:
            print("Число должно быть больше нуля.", file=sys.stderr)
            continue
        return parsed


def main() -> int:
    args = _parse_args()
    brand = _ensure_brand(args.brand)
    count = _ensure_count(args.count)

    try:
        asyncio.run(
            _run_generation(
                brand=brand,
                count=count,
                input_path=args.input,
                output_path=args.output,
                start_row=args.start_row,
            )
        )
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"Не удалось сгенерировать Excel: {exc}", file=sys.stderr)
        return 1

    print(f"Файл {args.output} успешно создан на основе бренда {brand}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



"""Helpers for loading local catalog seed data from the InSales import TSV."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
DEFAULT_INPUT_FILE = DOWNLOADS / "honeywell_insales_import.csv"

PART_NUMBER_COL = "Параметр: Партномер"
NAME_COL = "Название товара или услуги"
DESCRIPTION_COL = "Описание"
SITE_PLACEMENT_COL = "Размещение на сайте"
PRODUCT_TYPE_COL = "Параметр: Тип товара"
OUR_PRICE_COL = "Цена продажи"
BRAND_COL = "Параметр: Бренд"


def _text(mapping: Mapping[str, Any], key: str) -> str:
    return str(mapping.get(key, "") or "").strip()


def build_content_seed_from_row(row: Mapping[str, Any]) -> dict[str, str]:
    """Extract content fields used by bundle/export refresh from one TSV row."""
    description = _text(row, DESCRIPTION_COL)
    return {
        "description": description,
        "description_source": "insales_import_seed" if description else "",
        "site_placement": _text(row, SITE_PLACEMENT_COL),
        "product_type": _text(row, PRODUCT_TYPE_COL),
        "seed_name": _text(row, NAME_COL),
        "our_price_raw": _text(row, OUR_PRICE_COL),
        "brand": _text(row, BRAND_COL),
    }


def load_insales_seed_index(input_file: Path = DEFAULT_INPUT_FILE) -> dict[str, dict[str, str]]:
    """Load the UTF-16 TSV import into a PN-keyed content seed index."""
    if not input_file.exists():
        return {}

    df = pd.read_csv(input_file, sep="\t", encoding="utf-16", dtype=str).fillna("")
    seeds: dict[str, dict[str, str]] = {}
    for _, row in df.iterrows():
        pn = _text(row, PART_NUMBER_COL)
        if not pn:
            continue
        seeds[pn] = build_content_seed_from_row(row)
    return seeds

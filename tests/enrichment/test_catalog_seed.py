import sys
from pathlib import Path

import pandas as pd


_scripts = Path(__file__).resolve().parents[2] / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from catalog_seed import load_insales_seed_index


def test_load_insales_seed_index_reads_utf16_tsv(tmp_path):
    input_file = tmp_path / "seed.tsv"
    df = pd.DataFrame(
        [
            {
                "Параметр: Партномер": "010130.10",
                "Название товара или услуги": "Модуль 4DG/2OP BUS-2/BUS-1 s.m.",
                "Описание": "Русское описание из импорта.",
                "Размещение на сайте": "Каталог/Системы безопасности",
                "Параметр: Тип товара": "Модуль",
                "Цена продажи": "13288,04",
                "Параметр: Бренд": "Honeywell",
            }
        ]
    )
    df.to_csv(input_file, sep="\t", index=False, encoding="utf-16")

    seeds = load_insales_seed_index(input_file)

    assert seeds["010130.10"] == {
        "description": "Русское описание из импорта.",
        "description_source": "insales_import_seed",
        "site_placement": "Каталог/Системы безопасности",
        "product_type": "Модуль",
        "seed_name": "Модуль 4DG/2OP BUS-2/BUS-1 s.m.",
        "our_price_raw": "13288,04",
        "brand": "Honeywell",
    }

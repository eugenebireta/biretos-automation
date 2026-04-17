"""Transform 229 canonical products to InSales 253-column CSV format.

Maps canonical → InSales fields based on shop_data.csv structure.
Output: ready for direct import to InSales admin panel.
"""
from __future__ import annotations

import json
import sys
import csv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
CANONICAL_FILE = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "canonical_products.json"
SHOP_DATA = Path(r"C:\Users\eugene\Downloads\shop_data.csv")
OUT_FILE = ROOT / "downloads" / "staging" / "pipeline_v2_export" / "insales_import_229sku.csv"

# Brand → InSales category default mapping (extend as needed)
BRAND_CATEGORY_HINT = {
    "PEHA": "Каталог/Электрика/Электроустановочные изделия",
    "Esser": "Каталог/Строительство и Ремонт/ОПС/Извещатели/Пожарные",
    "Notifier": "Каталог/Строительство и Ремонт/ОПС/Извещатели/Пожарные",
    "System Sensor": "Каталог/Строительство и Ремонт/ОПС/Извещатели/Пожарные",
    "Honeywell": "Каталог/Электрика/Щитовое оборудование",
    "DKC": "Каталог/Электрика/Кабеленесущие системы",
    "ABB": "Каталог/Электрика/Щитовое оборудование",
    "Weidmuller": "Каталог/Электрика/Щитовое оборудование",
    "Weidmüller": "Каталог/Электрика/Щитовое оборудование",
    "Phoenix Contact": "Каталог/Электрика/Кабеленесущие системы",
    "Howard Leight": "Каталог/Строительство и Ремонт/Спецодежда/Защита слуха",
    "Sperian": "Каталог/Строительство и Ремонт/Спецодежда/Страховочные системы",
    "Dell": "Каталог/Электроника АСУТП/Промышленные компьютеры",
    "HP": "Каталог/Электроника АСУТП/Промышленные компьютеры",
    "NEC": "Каталог/Электроника АСУТП/Промышленные компьютеры",
    "Optcom": "Каталог/Электроника АСУТП/Сетевое",
    "Hyperline": "Каталог/Электроника АСУТП/Сетевое",
    "Inter-M": "Каталог/Строительство и Ремонт/ОПС",
    "Brevini": "Каталог/Станки, ЧПУ/Мотор-редуктора",
    "Eaton": "Каталог/Электрика/Щитовое оборудование",
    "Sonlex": "Каталог/Электроника АСУТП/Сетевое",
    "Murrelektronik": "Каталог/Электрика/Щитовое оборудование",
}

# Currency conversion to RUB (rough — owner should verify)
CURRENCY_TO_RUB = {
    "RUB": 1.0,
    "EUR": 105.0,
    "USD": 95.0,
    "GBP": 120.0,
    "TWD": 3.0,
    "PLN": 24.0,
    "ARS": 0.1,  # very volatile
}


def load_insales_headers():
    """Read shop_data.csv header to get exact column names."""
    if not SHOP_DATA.exists():
        return None
    with open(SHOP_DATA, encoding="utf-16-le") as f:
        reader = csv.reader(f, delimiter="\t")
        return [h.replace("\ufeff", "").strip() for h in next(reader)]


def main():
    canonical = json.loads(CANONICAL_FILE.read_text(encoding="utf-8"))

    # Load SEO long descriptions (generated separately via AI router pipeline)
    seo_file = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "descriptions_seo.json"
    seo_descriptions = json.loads(seo_file.read_text(encoding="utf-8")) if seo_file.exists() else {}

    headers = load_insales_headers()
    if not headers:
        print("WARNING: shop_data.csv not found, using minimal headers")
        headers = [
            "Название товара или услуги", "Описание", "Размещение на сайте",
            "Изображения", "Артикул", "Штрих-код", "Цена продажи", "Вес",
            "Параметр: Тип товара", "Параметр: Бренд", "Параметр: Партномер",
            "Параметр: Серии", "Параметр: Размеры, мм", "Параметр: Вес товара, г",
            "Параметр: Материал",
        ]

    print(f"InSales columns: {len(headers)}")

    # Build column index
    col_idx = {h: i for i, h in enumerate(headers)}

    rows = []
    for p in canonical:
        identity = p.get("identity", {})
        pn = identity.get("pn", "")
        brand = identity.get("brand", "")

        # Get datasheet block
        ev_file = EV_DIR / f"evidence_{pn}.json"
        ds_block = {}
        if ev_file.exists():
            d = json.loads(ev_file.read_text(encoding="utf-8"))
            ds_block = d.get("from_datasheet", {})

        # Initialize row with empty strings
        row = [""] * len(headers)

        # Title — prefer datasheet title
        title = ds_block.get("title") or p.get("title_ru", "")
        if not title:
            title = f"{brand} {pn}"

        # Price in RUB
        price = p.get("best_price")
        currency = p.get("best_price_currency", "RUB")
        if price:
            try:
                rate = CURRENCY_TO_RUB.get(currency, 1.0)
                price_rub = round(float(price) * rate)
            except Exception:
                price_rub = ""
        else:
            price_rub = ""

        # Description — prefer SEO long form (300+ words) over canonical short form
        seo_entry = seo_descriptions.get(pn) or seo_descriptions.get(pn.replace("/", "_"), {})
        if isinstance(seo_entry, dict) and seo_entry.get("word_count", 0) >= 150:
            desc = seo_entry.get("description_seo_ru", "") or ""
        else:
            desc = p.get("best_description_ru", "") or ""
        if desc and not desc.startswith("<"):
            desc = f"<p>{desc}</p>"

        # Category
        category_path = BRAND_CATEGORY_HINT.get(brand, "Каталог")

        # Photo
        photo_url = p.get("best_photo_url", "")

        # Specs — prefer canonical.specs (normalized) over raw datasheet strings
        specs = ds_block.get("specs", {}) or {}
        canon_specs = p.get("specs") or {}
        # Weight: canonical weight_g (int, grams) wins over raw ds weight_g (free-form string)
        weight_g = canon_specs.get("weight_g")
        weight = str(weight_g) if weight_g else (ds_block.get("weight_g", "") or "")
        # Dims: canonical L/W/H (int, mm) → "LxWxH"; fallback to raw dimensions_mm string
        L, W, H = canon_specs.get("length_mm"), canon_specs.get("width_mm"), canon_specs.get("height_mm")
        if L and W and H:
            dims = f"{L}x{W}x{H}"
        elif L or W or H:
            dims = "x".join(str(x) if x else "?" for x in (L, W, H))
        else:
            dims = ds_block.get("dimensions_mm", "") or ""
        material = canon_specs.get("material") or specs.get("Material") or specs.get("material") or ""
        color = canon_specs.get("color_canonical") or specs.get("Colour") or specs.get("Color") or specs.get("colour") or ""
        ean = ds_block.get("ean", "")

        # Map to InSales columns
        def set_col(col_name, value):
            if col_name in col_idx:
                row[col_idx[col_name]] = str(value) if value not in (None, "") else ""

        set_col("Название товара или услуги", title[:150])
        set_col("Описание", desc)
        set_col("Размещение на сайте", category_path)
        set_col("Изображения", photo_url)
        set_col("Артикул", pn)
        set_col("Штрих-код", ean)
        set_col("Цена продажи", price_rub)
        set_col("Вес", weight)
        set_col("Параметр: Бренд", brand)
        set_col("Параметр: Партномер", pn)
        set_col("Параметр: Серии", ds_block.get("series", ""))
        set_col("Параметр: Размеры, мм", dims)
        set_col("Параметр: Вес товара, г", weight)
        set_col("Параметр: Материал", material)
        set_col("Параметр: Цвет товара", color)
        set_col("Видимость на витрине", "true")
        set_col("Применять скидки", "true")

        # IP rating
        ip = (canon_specs.get("ip_rating") or specs.get("Degree of protection (IP)") or
              specs.get("IP rating") or specs.get("ip_rating") or "")
        set_col("Параметр: Степень защиты IP", ip)

        rows.append(row)

    # Write CSV in InSales format (UTF-16-LE, tab-separated)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-16-le", newline="") as f:
        # BOM for UTF-16
        f.write("\ufeff")
        writer = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(headers)
        writer.writerows(rows)

    # Also save UTF-8 version for easier viewing
    out_utf8 = OUT_FILE.with_suffix(".utf8.csv")
    with open(out_utf8, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(headers)
        writer.writerows(rows)

    print(f"\nInSales CSV: {OUT_FILE}")
    print(f"UTF-8 view:  {out_utf8}")
    print(f"Rows: {len(rows)}")
    print(f"Columns: {len(headers)}")


if __name__ == "__main__":
    main()

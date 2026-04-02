"""
honeywell_to_insales.py — Конвертер Excel Honeywell → InSales TSV

Что делает:
  1. Читает honeywell new.xlsx (последний лист)
  2. Дедуплицирует по партномеру (суммирует qty, берёт лучшее имя)
  3. Для каждого товара вызывает GPT-4o: получает русское название,
     описание, категорию, тип товара
  4. Выдаёт готовый TSV (UTF-16) для импорта в InSales

Запуск:
  python scripts/honeywell_to_insales.py

Требования:
  pip install openai pandas openpyxl python-dotenv
"""

from __future__ import annotations

import json
import os
import sys
import time

# Windows cp1251 terminal fix
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("cp1251", "cp1252", "ascii"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

# ── Пути ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
INPUT_FILE = DOWNLOADS / "honeywell new.xlsx"
OUTPUT_FILE = DOWNLOADS / "honeywell_insales_import.csv"
CACHE_FILE = DOWNLOADS / "_gpt_cache.json"   # кэш чтобы не тратить API дважды

load_dotenv(DOWNLOADS / ".env")

# ── OpenAI ────────────────────────────────────────────────────────────────────
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
GPT_MODEL = "gpt-4o"
BATCH_SIZE = 20        # товаров за один запрос
RETRY_DELAY = 5        # сек при ошибке

# ── InSales колонки ───────────────────────────────────────────────────────────
INSALES_COLUMNS = [
    "ID товара",
    "Название товара или услуги",
    "Описание",
    "Изображения",
    "Размещение на сайте",
    "Видимость на витрине",
    "Применять скидки",
    "Артикул",
    "Цена продажи",
    "Старая цена",
    "Остаток",
    "Вес",
    "Параметр: Бренд",
    "Параметр: Партномер",
    "Параметр: Тип товара",
    "Параметр: Страна производства",
]

BRAND = "Honeywell"

# ── Системный промпт для GPT ───────────────────────────────────────────────────
SYSTEM_PROMPT = """Ты специалист по промышленному оборудованию и системам автоматизации.
Тебе дают список товаров бренда Honeywell (включая суббренды: Esser, Intermec, Galaxy, Honeywell Safety).
Для каждого товара нужно вернуть JSON-объект со следующими полями:

{
  "ru_name": "Полное русское название товара (конкретное, с моделью)",
  "description": "Описание товара 2-4 предложения на русском. Что это, где применяется, ключевые характеристики.",
  "category": "Категория в формате InSales: Каталог/[Раздел]/[Подраздел]",
  "product_type": "Тип товара одним словом или коротко (напр: Датчик, Сканер, Транспондер, Усилитель)"
}

Правила:
- ru_name: конкретный, с моделью. Пример: "Транспондер шины Esserbus IQ8FCT XS" а не просто "Транспондер"
- Если партномер известен — используй официальное русское название из документации
- Категории: выбирай из: Каталог/Пожарная сигнализация, Каталог/Системы безопасности,
  Каталог/Промышленные сканеры, Каталог/Средства индивидуальной защиты,
  Каталог/Промышленная автоматизация, Каталог/Видеонаблюдение
- Отвечай ТОЛЬКО валидным JSON-массивом. Без лишнего текста. Без markdown.
- Количество объектов в ответе = количеству товаров во входном массиве.
"""


def load_excel() -> pd.DataFrame:
    """Читает Excel, извлекает нужные колонки, дедуплицирует по PN."""
    xl = pd.ExcelFile(INPUT_FILE)
    df = pd.read_excel(INPUT_FILE, sheet_name=xl.sheet_names[-1], dtype=str)

    # Чистые колонки
    clean = pd.DataFrame({
        "name_raw": df["Unnamed: 1"].fillna("").str.strip(),
        "part_number": df["Партномер"].fillna("").str.strip(),
        "qty": pd.to_numeric(df["Количество"], errors="coerce").fillna(0),
        "price": pd.to_numeric(df["Цена за шт"].str.replace(",", "."), errors="coerce").fillna(0),
        "condition": df["Состояние"].fillna("новый").str.strip().str.lower(),
    })

    # Убираем строки без партномера
    clean = clean[clean["part_number"] != ""].copy()

    # Дедуплицируем по PN: суммируем qty, берём строку с самым длинным именем
    def agg_group(g: pd.DataFrame) -> pd.Series:
        best_name = g.loc[g["name_raw"].str.len().idxmax(), "name_raw"]
        return pd.Series({
            "name_raw": best_name,
            "qty": int(g["qty"].sum()),
            "price": g["price"].max(),   # берём максимальную цену
            "condition": g["condition"].iloc[0],
        })

    deduped = clean.groupby("part_number", as_index=False).apply(agg_group).reset_index(drop=True)
    print(f"Загружено строк: {len(clean)}. После дедупликации: {len(deduped)} уникальных PN.")
    return deduped


def load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def enrich_batch(items: list[dict], cache: dict) -> list[dict]:
    """Обогащает батч товаров через GPT. Использует кэш."""
    # Отделяем что уже в кэше
    to_call = [it for it in items if it["part_number"] not in cache]
    from_cache = [it for it in items if it["part_number"] in cache]

    results = []

    if to_call:
        user_msg = json.dumps([
            {"part_number": it["part_number"], "name_raw": it["name_raw"]}
            for it in to_call
        ], ensure_ascii=False)

        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model=GPT_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Верни JSON-массив для этих товаров:\n{user_msg}"},
                    ],
                    temperature=0.2,
                )
                content = resp.choices[0].message.content.strip()
                # Убираем markdown ```json ... ``` если есть
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()

                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    enriched = next(v for v in parsed.values() if isinstance(v, list))
                else:
                    enriched = parsed

                if len(enriched) != len(to_call):
                    print(f"  WARN: ожидали {len(to_call)} ответов, получили {len(enriched)}")

                for item, gpt in zip(to_call, enriched):
                    cache[item["part_number"]] = gpt
                save_cache(cache)
                break

            except Exception as e:
                import traceback
                print(f"  Ошибка GPT (попытка {attempt+1}): {type(e).__name__}: {e}")
                traceback.print_exc()
                if attempt < 2:
                    time.sleep(RETRY_DELAY)
                else:
                    # Заполняем fallback
                    for item in to_call:
                        if item["part_number"] not in cache:
                            cache[item["part_number"]] = {
                                "ru_name": item["name_raw"],
                                "description": f"Honeywell {item['part_number']}",
                                "category": "Каталог/Прочее",
                                "product_type": "Оборудование",
                            }
                    save_cache(cache)

    for it in to_call:
        results.append({**it, **cache[it["part_number"]]})
    for it in from_cache:
        results.append({**it, **cache[it["part_number"]]})

    return results


def format_price(price: float) -> str:
    return f"{price:.2f}".replace(".", ",")


def build_insales_row(row: dict) -> dict:
    pn = row["part_number"]
    name = row.get("ru_name") or row["name_raw"]
    desc = row.get("description", "")
    category = row.get("category", "Каталог/Прочее")
    product_type = row.get("product_type", "Оборудование")

    # Размещение: основная категория + подкатегория через ##
    parts = category.split("/")
    placements = [category]
    if len(parts) > 1:
        placements.insert(0, "/".join(parts[:2]))  # родитель
    placement_str = " ## ".join(dict.fromkeys(placements))  # без дублей

    return {
        "ID товара": "",
        "Название товара или услуги": name,
        "Описание": desc,
        "Изображения": "",
        "Размещение на сайте": placement_str,
        "Видимость на витрине": "выставлен",
        "Применять скидки": "да",
        "Артикул": pn,
        "Цена продажи": format_price(row["price"]),
        "Старая цена": "",
        "Остаток": str(int(row["qty"])),
        "Вес": "",
        "Параметр: Бренд": BRAND,
        "Параметр: Партномер": pn,
        "Параметр: Тип товара": product_type,
        "Параметр: Страна производства": "",
    }


def main() -> None:
    print("=== Honeywell -> InSales конвертер ===\n")

    df = load_excel()
    cache = load_cache()
    cached_count = sum(1 for pn in df["part_number"] if pn in cache)
    print(f"В кэше: {cached_count}/{len(df)} товаров. GPT-запросов нужно: {len(df) - cached_count}\n")

    records = df.to_dict(orient="records")
    all_enriched: list[dict] = []

    # Батчами
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        batch_need = sum(1 for it in batch if it["part_number"] not in cache)
        print(f"Батч {i//BATCH_SIZE + 1}/{(len(records)-1)//BATCH_SIZE + 1} "
              f"({len(batch)} товаров, {batch_need} новых в GPT)...", end=" ", flush=True)
        enriched = enrich_batch(batch, cache)
        all_enriched.extend(enriched)
        print("ok")
        if batch_need > 0:
            time.sleep(1)  # мягкий rate-limit

    # Строим InSales-строки
    out_rows = [build_insales_row(r) for r in all_enriched]
    out_df = pd.DataFrame(out_rows, columns=INSALES_COLUMNS)

    # Сохраняем как TSV UTF-16 (формат InSales)
    out_df.to_csv(OUTPUT_FILE, sep="\t", encoding="utf-16", index=False)
    print(f"\nГотово! Файл: {OUTPUT_FILE}")
    print(f"   Строк: {len(out_df)}")
    print(f"   Открой в InSales: Товары → Импорт → выбери файл")


if __name__ == "__main__":
    main()

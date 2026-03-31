"""
add_photos_serpapi.py — Ищет и скачивает фото для товаров Honeywell.

Что делает:
  1. Читает honeywell_insales_import.csv
  2. Для каждого товара ищет фото через SerpAPI Google Images
  3. Скачивает фото локально в downloads/photos/{part_number}.jpg
     - Если сайт блокирует hotlink — берёт Google thumbnail
  4. Сохраняет honeywell_insales_with_photos.csv с локальными путями
     (для ручной загрузки в InSales) и отдельный report.txt

Запуск:
  python scripts/add_photos_serpapi.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from serpapi import GoogleSearch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Пути ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
PHOTOS_DIR = DOWNLOADS / "photos"
INPUT_FILE  = DOWNLOADS / "honeywell_insales_import.csv"
OUTPUT_FILE = DOWNLOADS / "honeywell_insales_with_photos.csv"
PHOTO_CACHE = DOWNLOADS / "_photo_cache.json"
REPORT_FILE = DOWNLOADS / "photos_report.txt"

PHOTOS_DIR.mkdir(exist_ok=True)
load_dotenv(DOWNLOADS / ".env")
SERPAPI_KEY = os.environ["SERPAPI_KEY"]

BRAND = "Honeywell"
DELAY = 0.4

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.google.com/",
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

SKIP_EXTENSIONS = {".svg", ".gif"}


def safe_filename(part_number: str) -> str:
    """Превращает артикул в безопасное имя файла."""
    return re.sub(r'[\\/:*?"<>|]', "_", part_number)


def load_cache() -> dict:
    if PHOTO_CACHE.exists():
        return json.loads(PHOTO_CACHE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    PHOTO_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def try_download(url: str, dest: Path) -> bool:
    """Скачивает изображение. Возвращает True если успешно."""
    if not url or url.startswith("x-raw-image"):
        return False
    low = url.lower().split("?")[0]
    for ext in SKIP_EXTENSIONS:
        if low.endswith(ext):
            return False
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=10, stream=True)
        if resp.status_code != 200:
            return False
        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type and "octet" not in content_type:
            return False
        data = resp.content
        if len(data) < 2000:   # слишком маленький — наверное ошибка
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def search_and_download(part_number: str, ru_name: str, cache: dict) -> dict:
    """
    Ищет фото, скачивает локально.
    Возвращает: {local_path, source_url, method}
    """
    cache_key = f"dl:{part_number}"
    if cache_key in cache:
        return cache[cache_key]

    fname = safe_filename(part_number)
    dest = PHOTOS_DIR / f"{fname}.jpg"

    # Если файл уже скачан
    if dest.exists() and dest.stat().st_size > 2000:
        result = {"local_path": str(dest), "source_url": "", "method": "already_exists"}
        cache[cache_key] = result
        save_cache(cache)
        return result

    queries = [
        f"{part_number} {BRAND}",
        f"{part_number}",
        f"{BRAND} {ru_name[:50]}",
    ]

    for query in queries:
        try:
            params = {
                "engine": "google_images",
                "q": query,
                "num": 10,
                "safe": "active",
                "api_key": SERPAPI_KEY,
            }
            r = GoogleSearch(params).get_dict()
            imgs = r.get("images_results", [])
            time.sleep(DELAY)

            for img in imgs:
                original = img.get("original", "")
                thumbnail = img.get("thumbnail", "")

                # Пробуем оригинал
                if try_download(original, dest):
                    result = {"local_path": str(dest), "source_url": original, "method": "original"}
                    cache[cache_key] = result
                    save_cache(cache)
                    return result

                # Пробуем thumbnail (Google CDN, всегда доступен)
                if try_download(thumbnail, dest):
                    result = {"local_path": str(dest), "source_url": thumbnail, "method": "thumbnail"}
                    cache[cache_key] = result
                    save_cache(cache)
                    return result

        except Exception as e:
            print(f"  WARN [{part_number}]: {e}")
            break

    # Не нашли
    result = {"local_path": "", "source_url": "", "method": "not_found"}
    cache[cache_key] = result
    save_cache(cache)
    return result


def main() -> None:
    print("=== Поиск и скачивание фото (SerpAPI) ===\n")

    if not INPUT_FILE.exists():
        print(f"Нет файла: {INPUT_FILE}")
        print("Сначала запусти: python scripts/honeywell_to_insales.py")
        sys.exit(1)

    df = pd.read_csv(INPUT_FILE, sep="\t", encoding="utf-16", dtype=str).fillna("")
    cache = load_cache()

    already_dl = sum(
        1 for pn in df["Параметр: Партномер"]
        if cache.get(f"dl:{pn}", {}).get("local_path")
        and Path(cache[f"dl:{pn}"]["local_path"]).exists()
    )
    print(f"Всего товаров: {len(df)} | Уже скачано: {already_dl} | Осталось: {len(df)-already_dl}\n")

    results = []
    found = not_found = 0

    for i, (_, row) in enumerate(df.iterrows()):
        pn  = str(row["Параметр: Партномер"]).strip()
        name = str(row["Название товара или услуги"]).strip()

        cache_key = f"dl:{pn}"
        in_cache = cache_key in cache and Path(cache.get(cache_key, {}).get("local_path", "x")).exists()

        result = search_and_download(pn, name, cache)

        if not in_cache:
            method = result["method"]
            if result["local_path"]:
                size_kb = Path(result["local_path"]).stat().st_size // 1024
                print(f"  [{i+1:3d}/{len(df)}] + {pn:<22} [{method}] {size_kb}KB")
                found += 1
            else:
                print(f"  [{i+1:3d}/{len(df)}] - {pn:<22} [not found]")
                not_found += 1
        else:
            if result["local_path"]:
                found += 1
            else:
                not_found += 1

        results.append(result)

    # Обновляем CSV — колонка "Изображения" = локальный путь
    df["Изображения"] = [r["local_path"] for r in results]
    df["Источник фото"] = [r["source_url"][:80] if r["source_url"] else "" for r in results]
    df.to_csv(OUTPUT_FILE, sep="\t", encoding="utf-16", index=False)

    # Отчёт
    no_photo_rows = [(df.iloc[i]["Параметр: Партномер"], df.iloc[i]["Название товара или услуги"])
                     for i, r in enumerate(results) if not r["local_path"]]
    report_lines = [
        f"Всего товаров: {len(df)}",
        f"С фото:        {found}",
        f"Без фото:      {not_found}",
        f"Папка с фото:  {PHOTOS_DIR}",
        "",
        "Товары БЕЗ фото:",
    ] + [f"  {pn}: {name[:60]}" for pn, name in no_photo_rows]
    REPORT_FILE.write_text("\n".join(report_lines), encoding="utf-8")

    print(f"\n--- Итог ---")
    print(f"С фото:   {found}/{len(df)}")
    print(f"Без фото: {not_found}/{len(df)}")
    print(f"\nФото скачаны в: {PHOTOS_DIR}")
    print(f"CSV с путями:   {OUTPUT_FILE}")
    print(f"Отчёт:          {REPORT_FILE}")
    print(f"\nДалее: загрузи фото из папки photos/ в InSales через Товары -> Импорт.")


if __name__ == "__main__":
    main()

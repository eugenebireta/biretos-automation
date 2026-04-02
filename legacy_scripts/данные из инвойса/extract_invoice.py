import os
import glob
import re
import pdfplumber
import pandas as pd


# Пути к папкам
INPUT_DIR = "input/new"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "invoice_report.xlsx")

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Итоговые колонки
COLUMNS = ["Наименование", "Количество", "Цена"]
all_data = []


def clean_text(value: str) -> str:
    """
    Очистка текста:
    - переносы строк после дефиса слипаются ("-\n21" -> "-21")
    - обычные переносы заменяются на пробел
    - убираем множественные пробелы
    """
    if not value:
        return ""

    # дефис + перенос строки + пробелы → дефис
    text = re.sub(r"-\s*\n\s*", "-", value)

    # остальные переносы → пробел
    text = text.replace("\n", " ")

    # убираем дубликаты пробелов
    text = " ".join(text.split())

    return text


def to_number(value):
    """Преобразует строку в число (если возможно)."""
    if not value:
        return None
    try:
        value = value.replace(" ", "").replace(",", ".")
        return float(value) if "." in value else int(value)
    except:
        return None


pdf_files = glob.glob(os.path.join(INPUT_DIR, "*.pdf"))

if not pdf_files:
    print("❌ В папке input/new нет PDF-файлов.")
else:
    print(f"Найдено файлов: {len(pdf_files)}")

    for pdf_path in pdf_files:
        print(f"Обработка: {pdf_path}")
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()

                    for table in tables:
                        for row in table:
                            # проверяем, что строка похожа на таблицу товаров (≥ 11 колонок)
                            if not row or len(row) < 11:
                                continue

                            # Берём только нужные колонки
                            name = clean_text(row[1]) if row[1] else ""
                            qty = clean_text(row[6]) if row[6] else ""
                            price = clean_text(row[10]) if row[10] else ""

                            # ----- фильтрация -----
                            if not (name and qty and price):
                                continue

                            lower_name = name.lower()

                            # исключаем явные заголовки/итоги
                            if lower_name.startswith(("товар", "наименование", "итого", "код", "номер")):
                                continue

                            # убираем "сумма"/ "ндс"/ и т.п. из ценовой графы
                            if price.lower().startswith(("сумма", "без", "ндс")):
                                continue

                            # исключаем "2 7 11" — это часть шапки таблицы
                            if qty.strip() == "7" and price.strip() == "11":
                                continue

                            # исключаем строки, где встречается слово "доставка"
                            if "доставка" in lower_name:
                                continue

                            qty_num = to_number(qty)
                            price_num = to_number(price)

                            # количество и цена должны быть числами
                            if qty_num is None or price_num is None:
                                continue

                            all_data.append([name, qty_num, price_num])

        except Exception as e:
            print(f"⚠️ Ошибка при чтении {pdf_path}: {e}")


# Сохраняем Excel
if all_data:
    df = pd.DataFrame(all_data, columns=COLUMNS)
    df.to_excel(OUTPUT_FILE, index=False, engine="openpyxl")
    print(f"✅ Готово! Файл сохранён: {OUTPUT_FILE}")
else:
    print("❌ Данные не найдены.")
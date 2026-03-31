import argparse
import re
from io import StringIO
from pathlib import Path
from typing import Optional, Tuple, List

import pandas as pd

HEADER_DATE_TOKENS = ["дата", "месяц", "month", "период", "period", "неделя", "week"]
HEADER_VALUE_TOKENS = ["показ", "shows", "count", "value", "количество", "всего", "число запросов", "частот", "спрос"]

RUS_MONTHS = {
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12
}

def read_text(path: Path) -> Tuple[str, str]:
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return path.read_text(encoding=enc), enc
        except Exception:
            continue
    return path.read_text(encoding="cp1251", errors="ignore"), "cp1251"

def detect_header_and_sep(lines: List[str]) -> Tuple[int, str]:
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        has_date = any(tok in low for tok in HEADER_DATE_TOKENS)
        has_val = any(tok in low for tok in HEADER_VALUE_TOKENS)
        if has_date and has_val and ("," in line or ";" in line or "\t" in line):
            sep = ";" if ";" in line else ("\t" if "\t" in line else ",")
            return i, sep
    for i, raw in enumerate(lines):
        if raw.count(";") >= 1: return i, ";"
        if raw.count(",") >= 1: return i, ","
        if raw.count("\t") >= 1: return i, "\t"
    return 0, ","

def clean_number_series(s: pd.Series) -> pd.Series:
    s = s.astype(str)
    s = (s.str.replace("\u00a0", "", regex=False)
           .str.replace("\u2009", "", regex=False)
           .str.replace("\u202f", "", regex=False)
           .str.replace(" ", "", regex=False)
           .str.replace("\t", "", regex=False)
           .str.replace(",", "", regex=False))
    return pd.to_numeric(s, errors="coerce").fillna(0).astype("int64")

def guess_cols(df: pd.DataFrame) -> Tuple[Optional[str], Optional[str]]:
    cols = [str(c).strip().lower() for c in df.columns]
    date_candidates, val_candidates = [], []
    for i, c in enumerate(cols):
        if any(x in c for x in HEADER_DATE_TOKENS):
            date_candidates.append(df.columns[i])
        if any(x in c for x in HEADER_VALUE_TOKENS):
            val_candidates.append(df.columns[i])
    if df.shape[1] == 2:
        if not date_candidates: date_candidates = [df.columns[0]]
        if not val_candidates: val_candidates = [c for c in df.columns if c not in date_candidates]
    return (date_candidates[0] if date_candidates else None,
            val_candidates[0] if val_candidates else None)

def parse_ru_month(val) -> pd.Timestamp:
    if pd.isna(val): return pd.NaT
    s = str(val).strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*г\.?$", "", s)  # убрать "г." или "г"
    m = re.match(r"^([а-яё]+)\s+(\d{4})$", s)
    if m:
        mon_name, year = m.group(1), int(m.group(2))
        if mon_name in RUS_MONTHS:
            return pd.Timestamp(year=year, month=RUS_MONTHS[mon_name], day=1)
    return pd.NaT

def extract_keyword(df_raw: pd.DataFrame) -> Optional[str]:
    # 1) Из колонок таблицы (если есть)
    for col in df_raw.columns:
        col_l = str(col).lower()
        if any(x in col_l for x in ["запрос", "keyword", "ключ", "фраза", "phrase"]):
            vals = df_raw[col].dropna().astype(str).str.strip().unique()
            if len(vals) == 1:
                return vals[0]
    # 2) Из названий колонок (заголовок Wordstat часто содержит «ключ»)
    for col in df_raw.columns:
        m = re.search(r"«([^»]+)»", str(col))
        if not m:
            m = re.search(r"\"([^\"]+)\"", str(col))
        if m:
            return m.group(1).strip()
    return None

def keyword_from_filename(path: Path) -> str:
    return re.sub(r"\s+", " ", path.stem).strip()

def parse_wordstat_csv(path: Path) -> pd.DataFrame:
    txt, _ = read_text(path)
    lines = txt.splitlines()
    header_idx, sep = detect_header_and_sep(lines)
    table_text = "\n".join(lines[header_idx:])
    df_raw = pd.read_csv(StringIO(table_text), sep=sep, engine="python")

    if df_raw.shape[1] < 2:
        print(f"Skip (no table found): {path.name}")
        return pd.DataFrame(columns=["keyword", "date", "count"])

    date_col, val_col = guess_cols(df_raw)

    if date_col is None:
        for col in df_raw.columns:
            dt = pd.to_datetime(df_raw[col], errors="coerce", dayfirst=True)
            if dt.notna().sum() >= max(2, int(0.3 * len(df_raw))):
                date_col = col
                break
    if val_col is None:
        numeric_candidates = []
        for col in df_raw.columns:
            if col == date_col:
                continue
            numeric = pd.to_numeric(
                df_raw[col].astype(str).str.replace("\u00a0", "", regex=False).str.replace(" ", "", regex=False),
                errors="coerce"
            )
            if numeric.notna().sum() >= max(2, int(0.3 * len(df_raw))):
                numeric_candidates.append(col)
        if numeric_candidates:
            val_col = numeric_candidates[0]

    if date_col is None or val_col is None:
        print(f"Skip (couldn't detect date/value): {path.name}")
        return pd.DataFrame(columns=["keyword", "date", "count"])

    df = df_raw[[date_col, val_col]].copy()
    df.columns = ["date", "count"]

    # Сначала пробуем стандартный парсер, затем — вручную для русских месяцев
    dt = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)
    if dt.notna().sum() == 0:
        dt = df["date"].map(parse_ru_month)
    df["date"] = dt
    df = df[df["date"].notna()]
    if df.empty:
        print(f"Skip (no parseable dates): {path.name}")
        return pd.DataFrame(columns=["keyword", "date", "count"])

    df["count"] = clean_number_series(df["count"])

    kw = extract_keyword(df_raw) or keyword_from_filename(path)
    df["keyword"] = kw

    return df[["keyword", "date", "count"]].sort_values(["keyword", "date"])

def combine_folder(input_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    all_rows: List[pd.DataFrame] = []
    for p in sorted(input_dir.glob("*.csv")):
        try:
            df = parse_wordstat_csv(p)
            if not df.empty:
                all_rows.append(df)
                print(f"OK: {p.name} -> {len(df)} rows")
            else:
                print(f"EMPTY: {p.name}")
        except Exception as e:
            print(f"ERROR: {p.name}: {e}")

    if not all_rows:
        return pd.DataFrame(columns=["keyword", "date", "count"]), pd.DataFrame()

    monthly = pd.concat(all_rows, ignore_index=True)

    # Аггрегируем до месяцев (если вдруг попались недели)
    monthly["month"] = monthly["date"].dt.to_period("M").dt.to_timestamp()
    monthly_agg = (
        monthly.groupby(["keyword", "month"], as_index=False)["count"]
        .sum()
        .rename(columns={"month": "date"})
        .sort_values(["keyword", "date"])
    )

    yearly = (
        monthly_agg.assign(year=monthly_agg["date"].dt.year)
        .groupby(["keyword", "year"], as_index=False)["count"].sum()
        .pivot(index="keyword", columns="year", values="count")
        .fillna(0)
        .astype(int)
        .reset_index()
        .sort_values("keyword")
    )

    return monthly_agg, yearly

def main():
    ap = argparse.ArgumentParser(description="Combine Yandex Wordstat CSVs into monthly and yearly tables.")
    ap.add_argument("input_dir", type=str, help="Folder with Wordstat CSV files (one keyword per file).")
    ap.add_argument("--out-monthly", type=str, default="wordstat_monthly.csv")
    ap.add_argument("--out-yearly", type=str, default="wordstat_yearly.xlsx")
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        raise SystemExit(f"Folder not found: {input_dir}")

    monthly, yearly = combine_folder(input_dir)
    if monthly.empty:
        print("No monthly data produced. Check your CSV files and folder path.")
        return

    monthly.to_csv(args.out_monthly, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(args.out_yearly, engine="xlsxwriter") as xw:
        yearly.to_excel(xw, index=False, sheet_name="yearly")

    print(f"Saved: {args.out_monthly} and {args.out_yearly}")

if __name__ == "__main__":
    main()
import argparse
import os
import re
from pathlib import Path
from typing import Optional, Tuple, List

import pandas as pd


def smart_read_csv(path: Path) -> pd.DataFrame:
    """
    Reads a Wordstat CSV robustly:
    - tries UTF-8 with BOM, then cp1251
    - lets pandas sniff the delimiter (comma/semicolon/tab)
    - returns a DataFrame, may include extra non-table rows which we'll filter later
    """
    # Try utf-8-sig with sep=None (sniff)
    for enc in ("utf-8-sig", "cp1251"):
        try:
            df = pd.read_csv(path, sep=None, engine="python", encoding=enc)
            return df
        except Exception:
            continue
    # Last resort: semicolon, cp1251
    return pd.read_csv(path, sep=";", encoding="cp1251")


def guess_cols(df: pd.DataFrame) -> Tuple[Optional[str], Optional[str]]:
    """
    Try to find date and count columns by header names.
    """
    cols = [str(c).strip().lower() for c in df.columns]
    date_candidates = []
    val_candidates = []

    for i, c in enumerate(cols):
        if any(x in c for x in ["дата", "date", "месяц", "month"]):
            date_candidates.append(df.columns[i])
        if any(x in c for x in ["показ", "запрос", "count", "shows", "value", "количество"]):
            val_candidates.append(df.columns[i])

    # If exactly 2 columns and one looks like date — treat the other as value
    if df.shape[1] == 2 and (date_candidates or any("date" in str(c).lower() for c in df.columns)):
        if not date_candidates:
            # pick the first column as date if it looks like a date later
            date_candidates = [df.columns[0]]
        if not val_candidates:
            val_candidates = [col for col in df.columns if col not in date_candidates]

    date_col = date_candidates[0] if date_candidates else None
    val_col = val_candidates[0] if val_candidates else None
    return date_col, val_col


def extract_constant_keyword(df: pd.DataFrame) -> Optional[str]:
    """
    Some exports may contain a column with the query/keyword. Try to detect it.
    If not, return None (we'll fall back to filename).
    """
    for col in df.columns:
        col_l = str(col).lower()
        if any(x in col_l for x in ["запрос", "keyword", "ключ", "ключевое", "phrase", "фраза"]):
            vals = df[col].dropna().astype(str).str.strip().unique()
            if len(vals) == 1:
                return vals[0]
    return None


def sanitize_keyword_from_filename(filename: str) -> str:
    # Remove extension and common prefixes, trim spaces
    stem = Path(filename).stem
    # Often Wordstat filenames include query and maybe region — keep it simple:
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem


def normalize_wordstat_file(path: Path) -> pd.DataFrame:
    df_raw = smart_read_csv(path)

    # Keep only rows that can be a date in first 1-2 columns
    # We'll detect after we pick date/value columns
    date_col, val_col = guess_cols(df_raw)

    # If we still can't guess, try heuristics: try to parse any column as date, pick that one
    if date_col is None:
        for col in df_raw.columns:
            try_dt = pd.to_datetime(df_raw[col], errors="coerce", dayfirst=True, format=None)
            if try_dt.notna().sum() >= max(3, int(0.3 * len(df_raw))):
                date_col = col
                break

    # Value column heuristic if missing: pick a numeric-like column
    if val_col is None:
        numeric_counts = []
        for col in df_raw.columns:
            if col == date_col:
                continue
            s = pd.to_numeric(df_raw[col], errors="coerce")
            if s.notna().sum() >= max(3, int(0.3 * len(df_raw))):
                numeric_counts.append(col)
        if numeric_counts:
            val_col = numeric_counts[0]

    if date_col is None or val_col is None:
        # Give up on this file gracefully
        print(f"Skip (couldn't detect columns): {path.name}")
        return pd.DataFrame(columns=["keyword", "date", "count"])

    df = df_raw[[date_col, val_col]].copy()
    df.columns = ["date", "count"]

    # Parse dates; Wordstat monthly typically like "2023-05" or "Май 2023" or "01.05.2023"
    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)
    df = df[df["date"].notna()]

    # Coerce count to integer
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype("int64")

    # Get keyword
    kw = extract_constant_keyword(df_raw)
    if not kw:
        kw = sanitize_keyword_from_filename(path.name)
    df["keyword"] = kw

    # Keep only needed columns
    df = df[["keyword", "date", "count"]].sort_values(["keyword", "date"])
    return df


def combine_folder(input_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    all_rows: List[pd.DataFrame] = []
    for p in sorted(input_dir.glob("*.csv")):
        try:
            df = normalize_wordstat_file(p)
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

    # Sometimes CSVs may be weekly — aggregate to months to be safe
    monthly["year"] = monthly["date"].dt.year
    monthly["month"] = monthly["date"].dt.to_period("M").dt.to_timestamp()
    monthly_agg = (
        monthly.groupby(["keyword", "month"], as_index=False)["count"]
        .sum()
        .rename(columns={"month": "date"})
        .sort_values(["keyword", "date"])
    )

    # Yearly pivot
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
    parser = argparse.ArgumentParser(description="Combine Yandex Wordstat CSVs into monthly and yearly tables.")
    parser.add_argument("input_dir", type=str, help="Folder with downloaded CSV files from Wordstat")
    parser.add_argument("--out-monthly", type=str, default="wordstat_monthly.csv", help="Output CSV for monthly series")
    parser.add_argument("--out-yearly", type=str, default="wordstat_yearly.xlsx", help="Output Excel for yearly totals")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        raise SystemExit(f"Folder not found: {input_dir}")

    monthly, yearly = combine_folder(input_dir)

    if monthly.empty:
        print("No monthly data produced. Check your CSV files and folder path.")
        return

    monthly.to_csv(args.out_monthly, index=False, encoding="utf-8-sig")
    print(f"Saved monthly CSV: {args.out_monthly} ({len(monthly)} rows)")

    # Save yearly to Excel with a nice sheet name
    with pd.ExcelWriter(args.out_yearly, engine="xlsxwriter") as xw:
        yearly.to_excel(xw, index=False, sheet_name="yearly")
    print(f"Saved yearly Excel: {args.out_yearly} ({yearly.shape[0]} keys, {yearly.shape[1]-1} years)")


if __name__ == "__main__":
    main()
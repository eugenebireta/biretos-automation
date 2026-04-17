"""
InSales lot-variant audit — Stage 1 of the variants -> bundles migration.

READ-ONLY. Reads InSales shop_data.csv export and classifies multi-variant
products into migration-ready buckets. No API calls, no writes to InSales,
no mutation of input file.

Why this exists:
  Owner has ~181 products encoded as "1 product with N lot-size variants"
  (e.g. 1 pc / 5 pc / 10 pc). InSales does not sum stock across variants,
  which breaks RFQ automation. Target state: "1 base product (real stock)
  + N bundle products (consume from base)" via InSales Комплекты товаров.

Output (downloads/insales_audit/<date>/):
  - audit_report.csv        — every multi-variant product with classification
  - audit_summary.json      — counts by category
  - clean_lots_whitelist.json — pids ready for automatic migration
  - manual_triage.json      — pids needing human review

Usage:
  python scripts/insales_lot_audit.py [--csv PATH]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# Force UTF-8 stdout on Windows (per memory: feedback_windows_encoding)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_CSV = r"C:\Users\eugene\Downloads\shop_data.csv"

# Column indices in InSales shop_data.csv (253-column standard export, UTF-16-LE)
COL_PRODUCT_ID = 0
COL_PRODUCT_NAME = 1
COL_LOT_SIZE = 24          # "Свойство: Единиц в одном товаре"
COL_VARIANT_ID = 30
COL_ARTICLE = 31
COL_BARCODE = 32
COL_EXTERNAL_ID = 33
COL_PRICE = 35              # "Цена продажи"
COL_STOCK = 38              # "Остаток"
COL_STOCK_MAIN = 39         # "Остаток: Основной склад"
COL_MP_PRICE = 43           # "Тип цен: маркетплейс" — owner's Ozon price column


def parse_decimal(s: str) -> float | None:
    """InSales uses comma as decimal separator: '882,0' -> 882.0."""
    if not s or not s.strip():
        return None
    try:
        return float(s.replace(",", ".").strip())
    except ValueError:
        return None


def parse_int(s: str) -> int | None:
    if not s or not s.strip():
        return None
    try:
        return int(float(s.replace(",", ".").strip()))
    except ValueError:
        return None


def load_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open("r", encoding="utf-16-le", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        rows = list(reader)
    return header, rows


def group_by_product(rows: list[list[str]]) -> dict[str, list[list[str]]]:
    out: dict[str, list[list[str]]] = defaultdict(list)
    for row in rows:
        if len(row) <= COL_STOCK_MAIN:
            continue
        pid = row[COL_PRODUCT_ID].strip()
        if not pid:
            continue
        out[pid].append(row)
    return out


def classify_product(variants: list[list[str]]) -> tuple[str, dict]:
    """
    Classify a multi-variant product into a migration bucket.

    Returns (classification, details).

    Buckets (priority order, first match wins):
      - no_lot_size: at least one variant missing "Единиц в одном товаре".
                     Cannot infer lot structure automatically.
      - duplicate_lot_sizes: two+ variants share the same lot_size.
                             Not a pure lot encoding.
      - truly_mixed_prices: prices differ AND per-unit price spread >10%.
                            Variants likely encode different physical SKUs.
      - uniform_price_lots: all variants share the same price (Цена продажи)
                            but lot_sizes differ. Owner's bulk-template pattern.
                            Needs price decision before migration.
      - scaled_price_lots: prices scale linearly with lot_size (per-unit price
                           constant within 10%). Cleanest case for migration.
      - other_mixed: anything else (mostly stale variants).
    """
    parsed = []
    for v in variants:
        lot = parse_int(v[COL_LOT_SIZE])
        price = parse_decimal(v[COL_PRICE])
        stock = parse_int(v[COL_STOCK]) or 0
        mp_price = parse_decimal(v[COL_MP_PRICE]) if len(v) > COL_MP_PRICE else None
        parsed.append({
            "variant_id": v[COL_VARIANT_ID],
            "article": v[COL_ARTICLE],
            "barcode": v[COL_BARCODE],
            "external_id": v[COL_EXTERNAL_ID],
            "lot_size": lot,
            "price": price,
            "mp_price": mp_price,
            "stock": stock,
        })

    details = {"variants": parsed}

    # Total units across all variants (only meaningful if all have lot_size)
    if all(p["lot_size"] is not None for p in parsed):
        details["total_units"] = sum(p["lot_size"] * p["stock"] for p in parsed)
    else:
        details["total_units"] = None

    # Lot sizes seen (for the report, regardless of bucket)
    details["lot_sizes_seen"] = sorted(
        [p["lot_size"] for p in parsed if p["lot_size"] is not None]
    )
    details["has_stock"] = (details["total_units"] or 0) > 0

    # Bucket: missing lot_size on any variant
    if any(p["lot_size"] is None for p in parsed):
        return "no_lot_size", details

    # Bucket: duplicate lot sizes
    lot_counts = Counter(p["lot_size"] for p in parsed)
    if any(c > 1 for c in lot_counts.values()):
        details["duplicate_lots"] = {k: c for k, c in lot_counts.items() if c > 1}
        return "duplicate_lot_sizes", details

    prices = [p["price"] for p in parsed if p["price"] is not None]
    if not prices:
        return "no_lot_size", details

    # Per-unit price spread (only on variants with both price and lot_size > 0)
    per_unit_prices = [
        p["price"] / p["lot_size"]
        for p in parsed
        if p["price"] is not None and p["lot_size"] and p["lot_size"] > 0
    ]
    pu_min, pu_max = min(per_unit_prices), max(per_unit_prices)
    pu_spread = (pu_max - pu_min) / pu_min if pu_min > 0 else float("inf")
    details["per_unit_price_min"] = round(pu_min, 4)
    details["per_unit_price_max"] = round(pu_max, 4)
    details["per_unit_price_spread"] = round(pu_spread, 4)

    # All variants share the same total price (typical owner bulk-template pattern)
    if len(set(prices)) == 1:
        details["uniform_price"] = prices[0]
        return "uniform_price_lots", details

    # Per-unit price stable within 10% across variants — cleanest migration target
    if pu_spread <= 0.10:
        return "scaled_price_lots", details

    # Per-unit price varies wildly — variants likely encode different physical SKUs
    if pu_spread > 0.10:
        return "truly_mixed_prices", details

    return "other_mixed", details


def classify_mp_linearity(variants: list[dict]) -> tuple[str, dict]:
    """
    Second-axis classification: is the marketplace price (col 43) a sane
    monotone-or-flat function of lot_size?

    Returns (label, details).

    Labels:
      - linear_discount: per-unit mp_price decreases or stays flat as lot grows
                         (normal bulk-discount). MIGRATION-READY for Ozon.
      - flat:            mp_price proportional to lot_size (no discount, but valid).
      - irregular:       per-unit mp_price increases somewhere or has >5x outlier.
                         Likely typo (e.g. lot=10 mp=21177 instead of ~2120).
                         NEEDS REVIEW before automated migration.
      - missing_mp:      one or more variants lack mp_price.
    """
    info: dict = {}
    pairs = [
        (v["lot_size"], v["mp_price"])
        for v in variants
        if v.get("lot_size") and v.get("mp_price") is not None
    ]
    if len(pairs) < 2 or len(pairs) != len(variants):
        return "missing_mp", info

    pairs.sort(key=lambda x: x[0])
    per_unit = [(lot, mp / lot) for lot, mp in pairs]
    info["mp_per_unit"] = [(lot, round(p, 2)) for lot, p in per_unit]
    info["mp_lot1"] = pairs[0][1] if pairs[0][0] == 1 else None

    # Outlier ratio is informational only — real bulk discounts on cheap
    # consumables can exceed 10x (e.g. 1 шт = 275р, 100 шт = 28р/шт = 9.8x).
    # The actual TYPO signature is non-monotone per-unit price.
    pu_values = [p for _, p in per_unit]
    pu_min, pu_max = min(pu_values), max(pu_values)
    outlier_ratio = pu_max / pu_min if pu_min > 0 else float("inf")
    info["mp_per_unit_ratio"] = round(outlier_ratio, 2)

    # Per-unit must be non-increasing as lot_size grows (allow 10% noise).
    # A single rising step is what catches owner's data-entry typos like
    # OMFB72 (lot=10 mp=21177 instead of ~2120).
    monotone_decreasing = all(
        per_unit[i + 1][1] <= per_unit[i][1] * 1.10
        for i in range(len(per_unit) - 1)
    )
    if not monotone_decreasing:
        return "irregular", info

    # Flat = first and last per_unit are within 5% (no real bulk discount).
    if pu_max / pu_min < 1.05:
        return "flat", info
    return "linear_discount", info


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default=DEFAULT_CSV, help=f"Path to shop_data.csv (default: {DEFAULT_CSV})")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
        return 2

    print(f"Reading {csv_path}...")
    header, rows = load_csv(csv_path)
    print(f"  {len(rows)} rows, {len(header)} columns")

    # Sanity-check columns we depend on
    expected = {
        COL_PRODUCT_ID: "ID",
        COL_LOT_SIZE: "Единиц в одном товаре",
        COL_VARIANT_ID: "ID варианта",
        COL_PRICE: "Цена продажи",
        COL_STOCK: "Остаток",
    }
    for idx, expected_substr in expected.items():
        actual = header[idx] if idx < len(header) else ""
        if expected_substr.lower() not in actual.lower():
            print(
                f"WARN: column [{idx}] header is '{actual}', "
                f"expected to contain '{expected_substr}'. CSV schema may have shifted.",
                file=sys.stderr,
            )

    products = group_by_product(rows)
    multi = {pid: vs for pid, vs in products.items() if len(vs) > 1}
    print(f"  {len(products)} unique product IDs, {len(multi)} multi-variant")

    # Classify each multi-variant product on two independent axes:
    #   (1) price-uniformity bucket (Цена column shape)
    #   (2) mp_linearity (Тип цен: маркетплейс sanity / Ozon-readiness)
    classified: dict[str, dict] = {}
    for pid, variants in multi.items():
        bucket, details = classify_product(variants)
        mp_label, mp_info = classify_mp_linearity(details["variants"])
        details["mp_linearity"] = mp_label
        details.update(mp_info)
        classified[pid] = {
            "pid": pid,
            "name": variants[0][COL_PRODUCT_NAME],
            "variant_count": len(variants),
            "classification": bucket,
            **details,
        }

    bucket_counts = Counter(c["classification"] for c in classified.values())
    print("\nClassification (price-uniformity axis):")
    for bucket, n in bucket_counts.most_common():
        print(f"  {bucket:25s} {n:4d}")

    mp_counts = Counter(c["mp_linearity"] for c in classified.values())
    print("\nClassification (mp_price linearity axis — Ozon-readiness):")
    for label, n in mp_counts.most_common():
        print(f"  {label:25s} {n:4d}")

    # Cross-tab: how many products are migration-ready on BOTH axes?
    print("\nCross-tab (price-uniformity x mp_linearity):")
    cross = Counter((c["classification"], c["mp_linearity"]) for c in classified.values())
    for (b, m), n in sorted(cross.items()):
        print(f"  {b:25s} x {m:18s} {n:4d}")

    # Write output
    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = Path("downloads/insales_audit") / today
    out_dir.mkdir(parents=True, exist_ok=True)

    # CSV report (one row per product, sortable in Excel)
    report_csv = out_dir / "audit_report.csv"
    with report_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "pid", "name", "classification", "mp_linearity", "has_stock",
            "variant_count", "lot_sizes_seen", "total_units_if_slots",
            "uniform_price", "mp_lot1", "mp_per_unit_ratio",
            "per_unit_price_min", "per_unit_price_max", "per_unit_price_spread",
        ])
        # Sort: action-needed first, then by has_stock desc, then variant_count desc
        order = {
            "truly_mixed_prices": 0,
            "uniform_price_lots": 1,
            "scaled_price_lots": 2,
            "duplicate_lot_sizes": 3,
            "no_lot_size": 4,
            "other_mixed": 5,
        }
        for c in sorted(
            classified.values(),
            key=lambda x: (
                order.get(x["classification"], 9),
                not x.get("has_stock", False),
                -x["variant_count"],
            ),
        ):
            w.writerow([
                c["pid"],
                c["name"],
                c["classification"],
                c.get("mp_linearity", ""),
                "yes" if c.get("has_stock") else "no",
                c["variant_count"],
                ",".join(str(s) for s in c.get("lot_sizes_seen", [])),
                c.get("total_units", ""),
                c.get("uniform_price", ""),
                c.get("mp_lot1", ""),
                c.get("mp_per_unit_ratio", ""),
                c.get("per_unit_price_min", ""),
                c.get("per_unit_price_max", ""),
                c.get("per_unit_price_spread", ""),
            ])
    print(f"\n  CSV report:    {report_csv}")

    # Full JSON with per-variant detail (everything, sorted by classification)
    full_path = out_dir / "audit_full.json"
    full_path.write_text(
        json.dumps(list(classified.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  Full detail:   {full_path}")

    summary_path = out_dir / "audit_summary.json"
    summary = {
        "generated_at": datetime.now().isoformat(),
        "csv_path": str(csv_path),
        "csv_rows": len(rows),
        "unique_products": len(products),
        "multi_variant_products": len(multi),
        "classification_counts": dict(bucket_counts),
        "variant_count_distribution": dict(
            Counter(len(vs) for vs in multi.values())
        ),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  Summary:       {summary_path}")

    # Show top-10 samples per bucket (write to file too — Windows console eats Cyrillic)
    samples_path = out_dir / "samples_per_bucket.json"
    samples = {}
    for bucket in bucket_counts:
        items = [c for c in classified.values() if c["classification"] == bucket]
        items.sort(key=lambda x: -x["variant_count"])
        samples[bucket] = items[:10]
    samples_path.write_text(
        json.dumps(samples, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  Samples:       {samples_path}")

    print(f"\nDone. Output dir: {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

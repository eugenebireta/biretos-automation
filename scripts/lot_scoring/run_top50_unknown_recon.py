import csv
import json
from pathlib import Path

from scripts.lot_scoring.etl import ETLInvariantError, EtlConfig, run_etl_pipeline
from scripts.lot_scoring.pipeline.helpers import normalize_category_key, to_float
from scripts.lot_scoring.run_full_ranking_v341 import _lot_sort_key
from scripts.lot_scoring.run_series_pipeline import _load_lots_from_input, _normalize_code


def main():
    input_path = Path("honeywell.xlsx")
    out_csv = Path("audits/top_50_unknown_by_usd.csv")
    out_json = Path("audits/top_50_unknown_summary.json")

    # Инициализируем ETL для сборки строк, не вызываем score.py
    etl_config = EtlConfig()
    lots = _load_lots_from_input(input_path)

    pn_stats = {}
    total_unknown_usd_global = 0.0

    # Проходим по всем лотам и собираем unknown строки
    for lot_id in sorted(lots.keys(), key=_lot_sort_key):
        try:
            assembled = run_etl_pipeline(lots[lot_id], etl_config)
        except ETLInvariantError:
            continue

        for sku in assembled.all_skus:
            # Интересуют только unknown
            if normalize_category_key(sku.get("category")) != "unknown":
                continue

            # Исключаем строки без эффективной стоимости или количества
            if sku.get("effective_line_usd") is None or sku.get("q_has_qty") is False:
                continue

            sku_code = _normalize_code(sku.get("sku_code_normalized") or sku.get("sku_code"))
            if not sku_code:
                continue

            usd = max(0.0, to_float(sku.get("effective_line_usd"), 0.0))
            qty = max(0.0, to_float(sku.get("qty"), 0.0))

            total_unknown_usd_global += usd

            rec = pn_stats.setdefault(
                sku_code,
                {
                    "pn": sku_code,
                    "total_unknown_usd_per_pn": 0.0,
                    "total_unknown_qty": 0.0,
                    "lot_ids": set(),
                },
            )
            rec["total_unknown_usd_per_pn"] += usd
            rec["total_unknown_qty"] += qty
            rec["lot_ids"].add(str(lot_id))

    # Формируем итоговый список
    results = []
    for pn, stat in pn_stats.items():
        results.append(
            {
                "pn": pn,
                "total_unknown_usd_per_pn": stat["total_unknown_usd_per_pn"],
                "total_unknown_qty": stat["total_unknown_qty"],
                "lot_count": len(stat["lot_ids"]),
            }
        )

    # Сортировка: USD DESC, затем PN ASC (для детерминизма)
    results.sort(key=lambda x: (-x["total_unknown_usd_per_pn"], x["pn"]))

    top_50 = results[:50]
    total_usd_top50 = sum(item["total_unknown_usd_per_pn"] for item in top_50)
    share_top50 = (total_usd_top50 / total_unknown_usd_global) if total_unknown_usd_global > 0 else 0.0

    # Сохраняем CSV
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["pn", "total_unknown_usd_per_pn", "total_unknown_qty", "lot_count"])
        writer.writeheader()
        for item in top_50:
            writer.writerow(
                {
                    "pn": item["pn"],
                    "total_unknown_usd_per_pn": f"{item['total_unknown_usd_per_pn']:.6f}",
                    "total_unknown_qty": f"{item['total_unknown_qty']:.2f}",
                    "lot_count": item["lot_count"],
                }
            )

    # Сохраняем JSON Summary
    summary = {
        "total_unknown_pn_count": len(results),
        "total_unknown_usd": round(total_unknown_usd_global, 6),
        "total_usd_top50": round(total_usd_top50, 6),
        "top50_usd_share": round(share_top50, 6),
        "top50_usd_share_pct": round(share_top50 * 100.0, 4),
    }

    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== TOP-50 UNKNOWN RECON SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"Saved CSV: {out_csv}")
    print(f"Saved JSON: {out_json}")


if __name__ == "__main__":
    main()

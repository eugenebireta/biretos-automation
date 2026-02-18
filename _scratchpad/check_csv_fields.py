"""Проверка полей в сгенерированном CSV"""
import csv
from pathlib import Path

csv_path = Path(__file__).parent.parent / "insales_to_shopware_migration" / "output" / "products_import.csv"

with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print("=" * 60)
print("ПРОВЕРКА CSV")
print("=" * 60)
print(f"Всего товаров: {len(rows)}")
print(f"\nПоля CSV:")
for field in reader.fieldnames:
    print(f"  - {field}")

print(f"\nСтатистика:")
with_main = sum(1 for r in rows if r.get('mainCategoryId'))
with_cats = sum(1 for r in rows if r.get('categoryIds'))
print(f"  С mainCategoryId: {with_main} ({with_main/len(rows)*100:.1f}%)")
print(f"  С categoryIds: {with_cats} ({with_cats/len(rows)*100:.1f}%)")

print(f"\nПример товара:")
if rows:
    row = rows[0]
    print(f"  productNumber: {row.get('productNumber', 'N/A')}")
    print(f"  categoryIds: {row.get('categoryIds', 'N/A')[:100]}...")
    print(f"  mainCategoryId: {row.get('mainCategoryId', 'N/A')}")

print("=" * 60)









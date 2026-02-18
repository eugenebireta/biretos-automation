import csv
import json
from pathlib import Path

snapshot_dir = Path(__file__).parent / "insales_snapshot"
cat_map = json.load(open(snapshot_dir / "category_id_to_path.json", encoding="utf-8"))
products = list(csv.DictReader(open(snapshot_dir / "products.csv", encoding="utf-8")))

# Проверяем пересечение category_id
csv_cats = set(p['category_id'].strip() for p in products)
json_cats = set(cat_map.keys())
intersection = csv_cats & json_cats

print(f'Всего category_id в CSV: {len(csv_cats)}')
print(f'Всего category_id в JSON: {len(json_cats)}')
print(f'Пересечение: {len(intersection)}')
print(f'Первые 10 category_id из CSV: {list(csv_cats)[:10]}')
print(f'Первые 10 category_id из JSON: {list(json_cats)[:10]}')

if intersection:
    test_cat = list(intersection)[0]
    found = [p for p in products if p['category_id'].strip() == test_cat]
    if found:
        p = found[0]
        print(f'\nПервый товар с известным category_id:')
        print(f'  SKU: {p["sku"]}')
        print(f'  Name: {p["name"]}')
        print(f'  category_id: {p["category_id"]}')
        print(f'  full_path: {cat_map[p["category_id"].strip()]}')
else:
    print('\nНЕТ пересечений! Проверяем первые товары:')
    for p in products[:5]:
        print(f'  category_id: {p["category_id"]} (в JSON: {p["category_id"] in json_cats})')


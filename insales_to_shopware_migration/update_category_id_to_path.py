"""
Обновляет category_id_to_path.json, добавляя недостающие category_id из CSV
"""
import csv
import json
from pathlib import Path

snapshot_dir = Path(__file__).parent / "insales_snapshot"

# Загружаем существующий category_id_to_path.json
cat_id_to_path = json.load(open(snapshot_dir / "category_id_to_path.json", encoding="utf-8"))

# Загружаем categories_with_paths.json для построения путей
categories_with_paths = json.load(open(snapshot_dir / "categories_with_paths.json", encoding="utf-8"))

# Создаём индекс категорий по ID
cat_by_id = {str(cat["id"]): cat for cat in categories_with_paths}

# Загружаем товары из CSV
products = list(csv.DictReader(open(snapshot_dir / "products.csv", encoding="utf-8")))

# Находим уникальные category_id из CSV
csv_cat_ids = set(p["category_id"].strip() for p in products)

# Добавляем недостающие category_id
added = 0
for cat_id in csv_cat_ids:
    if cat_id not in cat_id_to_path:
        # Пытаемся найти категорию в categories_with_paths.json
        if cat_id in cat_by_id:
            cat = cat_by_id[cat_id]
            full_path = cat.get("full_path")
            if full_path:
                cat_id_to_path[cat_id] = full_path
                added += 1
                print(f"Добавлено: {cat_id} -> {full_path}")
        else:
            # Если категории нет в categories_with_paths.json, используем заглушку
            # Но лучше не добавлять, так как путь неизвестен
            print(f"Пропущено (нет в categories_with_paths.json): {cat_id}")

print(f"\nВсего добавлено: {added}")
print(f"Всего category_id в файле: {len(cat_id_to_path)}")

# Сохраняем обновлённый файл
json.dump(cat_id_to_path, open(snapshot_dir / "category_id_to_path.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\nФайл обновлён: {snapshot_dir / 'category_id_to_path.json'}")








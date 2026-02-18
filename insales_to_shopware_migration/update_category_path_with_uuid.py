"""
Обновляет category_id_to_path.json, добавляя UUID для category_id 23682913
"""
import json
from pathlib import Path

snapshot_dir = Path(__file__).parent / "insales_snapshot"
migration_map_path = Path(__file__).parent / "migration_map.json"

# Загружаем существующий category_id_to_path.json
cat_id_to_path = json.load(open(snapshot_dir / "category_id_to_path.json", encoding="utf-8"))

# Загружаем migration_map.json для получения UUID категории "Авиазапчасти"
migration_map = json.load(open(migration_map_path, encoding="utf-8"))
aviacat_uuid = migration_map.get("categories", {}).get("20769913")  # Авиазапчасти

if aviacat_uuid:
    # Обновляем category_id_to_path.json, используя UUID вместо пути
    cat_id_to_path["23682913"] = aviacat_uuid
    print(f"Обновлено: 23682913 -> {aviacat_uuid} (UUID категории 'Авиазапчасти')")
    
    # Сохраняем обновлённый файл
    json.dump(cat_id_to_path, open(snapshot_dir / "category_id_to_path.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Файл обновлён: {snapshot_dir / 'category_id_to_path.json'}")
else:
    print("Ошибка: UUID категории 'Авиазапчасти' не найден в migration_map.json")








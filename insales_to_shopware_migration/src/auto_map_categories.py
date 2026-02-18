#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматическое заполнение migration_map.json для категорий.

Читает snapshot CSV, извлекает уникальные category_id,
находит соответствующие категории в Shopware и обновляет migration_map.json.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json, save_json, ROOT

DEFAULT_CONFIG = ROOT / "config.json"
DEFAULT_MAP = ROOT / "migration_map.json"
DEFAULT_SNAPSHOT_CSV = ROOT / "insales_snapshot" / "products.csv"


def extract_unique_categories(csv_path: Path) -> Dict[str, Set[str]]:
    """
    Извлекает уникальные пары (category_id, category_path) из CSV.
    
    Returns:
        dict: {category_id: set(category_paths)}
    """
    categories: Dict[str, Set[str]] = defaultdict(set)
    
    print(f"[INFO] Чтение CSV: {csv_path}")
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            category_id = row.get("category_id", "").strip()
            category_path = row.get("category_path", "").strip()
            
            if category_id:
                if category_path:
                    categories[category_id].add(category_path)
                else:
                    categories[category_id].add(category_id)  # Fallback на ID
    
    print(f"[INFO] Найдено уникальных категорий InSales: {len(categories)}")
    return categories


def find_category_by_id_in_shopware(client: ShopwareClient, category_id: str) -> str | None:
    """
    Пытается найти категорию в Shopware по ID (если ID совпадает).
    
    Args:
        client: ShopwareClient
        category_id: ID категории (может быть UUID или InSales ID)
        
    Returns:
        Shopware UUID категории или None
    """
    # Попробуем использовать category_id как UUID
    try:
        category = client.get_category(category_id)
        if category:
            return category_id  # Это уже UUID
    except Exception:
        pass
    
    return None


def search_category_by_name(client: ShopwareClient, name: str) -> List[Dict[str, Any]]:
    """
    Ищет категории в Shopware по названию.
    
    Args:
        client: ShopwareClient
        name: Название категории
        
    Returns:
        Список найденных категорий
    """
    try:
        response = client._request(
            "POST",
            "/api/search/category",
            json={
                "filter": [
                    {"field": "name", "type": "equals", "value": name},
                ],
                "limit": 10,
                "includes": {"category": ["id", "name", "path"]},
            },
        )
        if isinstance(response, dict) and "data" in response:
            return response.get("data", [])
    except Exception:
        pass
    return []


def find_all_categories(client: ShopwareClient) -> List[Dict[str, Any]]:
    """
    Получает все категории из Shopware для локального поиска.
    
    Returns:
        Список всех категорий
    """
    try:
        all_categories = []
        page = 1
        per_page = 100
        
        while True:
            response = client._request(
                "POST",
                "/api/search/category",
                json={
                    "limit": per_page,
                    "page": page,
                    "includes": {"category": ["id", "name", "path", "parentId"]},
                },
            )
            if isinstance(response, dict) and "data" in response:
                data = response.get("data", [])
                if not data:
                    break
                all_categories.extend(data)
                if len(data) < per_page:
                    break
                page += 1
            else:
                break
        
        print(f"[INFO] Загружено категорий из Shopware: {len(all_categories)}")
        return all_categories
    except Exception as e:
        print(f"[WARN] Ошибка загрузки категорий: {e}")
        return []


def is_uuid_like(value: str) -> bool:
    """Проверяет, похоже ли значение на UUID (32 hex символа)."""
    if not value:
        return False
    # UUID в Shopware - это 32 hex символа
    cleaned = value.replace("-", "").lower()
    return len(cleaned) == 32 and all(c in "0123456789abcdef" for c in cleaned)


def map_categories(
    insales_categories: Dict[str, Set[str]],
    shopware_categories: List[Dict[str, Any]],
    existing_map: Dict[str, str],
    client: ShopwareClient,
    insales_structure: Dict[int, Dict[str, Any]] = None,
) -> Tuple[Dict[str, str], List[str]]:
    """
    Сопоставляет категории InSales с категориями Shopware.
    
    Стратегия поиска:
    1. Если category_path похож на UUID (32 hex) - проверяем напрямую через API
    2. Иначе ищем в списке всех категорий Shopware
    
    Args:
        insales_categories: {insales_category_id: set(category_paths)}
        shopware_categories: Список категорий Shopware
        existing_map: Существующий mapping из migration_map.json
        client: ShopwareClient для проверки категорий
        
    Returns:
        tuple: (новый mapping, список не найденных категорий)
    """
    mapping = existing_map.copy()
    not_found = []
    
    # Создаём индекс Shopware категорий по ID для быстрого поиска
    sw_cat_by_id = {cat.get("id", ""): cat for cat in shopware_categories}
    
    for insales_id, paths in insales_categories.items():
        # Пропускаем, если уже есть в mapping
        if insales_id in mapping:
            print(f"[SKIP] Уже в mapping: InSales {insales_id} -> Shopware {mapping[insales_id]}")
            continue
        
        found_uuid = None
        
        for path in paths:
            if not path:
                continue
            
            # Стратегия 1: Если path похож на UUID, проверяем напрямую
            if is_uuid_like(path):
                # Проверяем, существует ли категория с таким UUID
                if path in sw_cat_by_id:
                    found_uuid = path
                    print(f"[OK] Сопоставлено по UUID: InSales {insales_id} -> Shopware {found_uuid}")
                    break
                # Пытаемся получить через API (на случай, если не в списке)
                try:
                    category = client.get_category(path)
                    if category:
                        found_uuid = path
                        print(f"[OK] Сопоставлено по UUID (API): InSales {insales_id} -> Shopware {found_uuid}")
                        break
                except Exception:
                    pass
            else:
                # Стратегия 2: Если path это число (InSales ID), ищем в migration_map
                # для этого ID (если это ссылка на другую категорию)
                if path.isdigit():
                    path_id = path
                    if path_id in existing_map:
                        # Если path указывает на другую категорию, которая уже в mapping
                        found_uuid = existing_map[path_id]
                        print(f"[OK] Сопоставлено через path mapping: InSales {insales_id} -> Shopware {found_uuid} (через path {path_id})")
                        break
                
                # Стратегия 3: Если path это число и совпадает с insales_id,
                # значит это просто ID категории (не путь), и мы уже проверили выше
                # В этом случае категория не найдена в Shopware
            
            # Стратегия 4: Поиск по названию категории из InSales структуры
            if insales_structure and insales_id.isdigit():
                insales_cat = insales_structure.get(int(insales_id))
                if insales_cat:
                    cat_title = insales_cat.get("title", "").strip()
                    if cat_title:
                        # Ищем категорию в Shopware по названию
                        for sw_cat in shopware_categories:
                            sw_name = sw_cat.get("name", "").strip()
                            if sw_name and sw_name.lower() == cat_title.lower():
                                found_uuid = sw_cat.get("id")
                                print(f"[OK] Сопоставлено по названию: InSales {insales_id} ({cat_title}) -> Shopware {found_uuid}")
                                break
                        if found_uuid:
                            break
        
        if found_uuid:
            mapping[insales_id] = found_uuid
        else:
            not_found.append(insales_id)
            print(f"[SKIP] Не найдено в Shopware: InSales {insales_id} (paths: {list(paths)})")
    
    return mapping, not_found


def load_insales_structure() -> Dict[int, Dict[str, Any]]:
    """Загружает структуру категорий InSales из logs/insales_structure.json"""
    structure_path = ROOT / "logs" / "insales_structure.json"
    if not structure_path.exists():
        return {}
    
    try:
        with structure_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            collections = data.get("collections", [])
            return {cat["id"]: cat for cat in collections}
    except Exception:
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Автоматическое заполнение migration_map.json для категорий"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--map", dest="map_path", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--csv", type=Path, default=DEFAULT_SNAPSHOT_CSV)
    parser.add_argument("--structure", type=Path, default=ROOT / "logs" / "insales_structure.json")
    parser.add_argument("--dry-run", action="store_true", help="Показать что будет сделано без сохранения")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("АВТОМАТИЧЕСКОЕ СОПОСТАВЛЕНИЕ КАТЕГОРИЙ")
    print("=" * 60)
    
    # Загружаем конфигурацию
    if not args.config.exists():
        print(f"[ERROR] Конфигурация не найдена: {args.config}")
        return 1
    
    config = load_json(args.config)
    migration_map = load_json(args.map_path, default={"categories": {}, "properties": {}, "products": {}})
    existing_categories = migration_map.get("categories", {})
    
    print(f"[INFO] Существующих маппингов категорий: {len(existing_categories)}")
    
    # Извлекаем категории из CSV
    if not args.csv.exists():
        print(f"[ERROR] CSV файл не найден: {args.csv}")
        return 1
    
    insales_categories = extract_unique_categories(args.csv)
    
    # Загружаем структуру InSales для получения названий категорий
    print("[INFO] Загрузка структуры категорий InSales...")
    insales_structure = load_insales_structure()
    if insales_structure:
        print(f"[INFO] Загружено категорий из структуры InSales: {len(insales_structure)}")
    
    # Подключаемся к Shopware
    shop_cfg = ShopwareConfig(
        url=config["shopware"]["url"],
        access_key_id=config["shopware"]["access_key_id"],
        secret_access_key=config["shopware"]["secret_access_key"],
    )
    client = ShopwareClient(shop_cfg, timeout=10)
    
    # Получаем все категории из Shopware
    print("[INFO] Загрузка категорий из Shopware...")
    shopware_categories = find_all_categories(client)
    
    # Сопоставляем категории
    print("\n[INFO] Сопоставление категорий...")
    new_mapping, not_found = map_categories(
        insales_categories, 
        shopware_categories, 
        existing_categories, 
        client,
        insales_structure=insales_structure,
    )
    
    # Обновляем migration_map
    added_count = len(new_mapping) - len(existing_categories)
    
    print("\n" + "=" * 60)
    print("РЕЗУЛЬТАТЫ")
    print("=" * 60)
    print(f"Всего категорий в CSV: {len(insales_categories)}")
    print(f"Уже было в migration_map: {len(existing_categories)}")
    print(f"Добавлено новых: {added_count}")
    print(f"Не найдено в Shopware: {len(not_found)}")
    
    if not_found:
        print(f"\nКатегории, не найденные в Shopware (первые 10):")
        for cat_id in not_found[:10]:
            paths = insales_categories.get(cat_id, set())
            print(f"  - InSales {cat_id}: paths={paths}")
        if len(not_found) > 10:
            print(f"  ... и ещё {len(not_found) - 10} категорий")
    
    if args.dry_run:
        print("\n[DRY-RUN] Изменения не сохранены. Используйте без --dry-run для сохранения.")
        return 0
    
    # Сохраняем обновлённый migration_map
    if added_count > 0:
        migration_map["categories"] = new_mapping
        save_json(args.map_path, migration_map)
        print(f"\n[OK] migration_map.json обновлён: добавлено {added_count} категорий")
    else:
        print("\n[INFO] Нет новых категорий для добавления")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


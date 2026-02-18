from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from clients import ShopwareClient, ShopwareConfig


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
STRUCTURE_PATH = ROOT / "logs" / "insales_structure.json"
MAP_PATH = ROOT / "migration_map.json"

# Гарантируем UTF-8 вывод даже в консоли Windows
if hasattr(sys.stdout, "reconfigure"):  # Python 3.7+
    sys.stdout.reconfigure(encoding="utf-8")


def load_json(path: Path, *, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as handler:
        return json.load(handler)


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handler:
        json.dump(payload, handler, ensure_ascii=False, indent=2)


def build_shopware_client(cfg: Dict[str, Any]) -> ShopwareClient:
    shopware_cfg = ShopwareConfig(
        url=cfg["shopware"]["url"],
        access_key_id=cfg["shopware"]["access_key_id"],
        secret_access_key=cfg["shopware"]["secret_access_key"],
    )
    return ShopwareClient(shopware_cfg)


def normalize_category_title(title: Optional[str]) -> str:
    """Нормализует название категории для сравнения (регистр, пробелы)."""
    if not title:
        return ""
    return title.strip()


def is_catalog_category(category: Dict[str, Any]) -> bool:
    """Проверяет, является ли категория служебной 'Каталог'."""
    title = normalize_category_title(category.get("title"))
    # Точное совпадение с учетом регистра и пробелов
    return title == "Каталог"


def should_be_under_root_nav(
    category: Dict[str, Any],
    catalog_insales_id: Optional[int],
    collections_by_id: Dict[int, Dict[str, Any]],
) -> bool:
    """
    Определяет, должна ли категория быть прямым ребенком ROOT_NAV.
    
    Условия:
    - У категории нет parent_id (верхнеуровневая)
    - ИЛИ parent_id = ID категории "Каталог"
    - ИЛИ родитель категории - это "Каталог" (рекурсивная проверка)
    """
    parent_insales_id = category.get("parent_id")
    
    # Верхнеуровневая категория
    if not parent_insales_id:
        return True
    
    # Прямой ребенок "Каталога"
    if catalog_insales_id and parent_insales_id == catalog_insales_id:
        return True
    
    # Рекурсивная проверка: если родитель - это "Каталог"
    parent_cat = collections_by_id.get(parent_insales_id)
    if parent_cat and is_catalog_category(parent_cat):
        return True
    
    return False


def resolve_parent_id(
    category: Dict[str, Any],
    mapping: Dict[str, Any],
    collections_by_id: Dict[int, Dict[str, Any]],
    ensure_category_fn,
    root_nav_id: Optional[str],
    catalog_insales_id: Optional[int],
) -> Optional[str]:
    """
    Определяет parentId для категории в Shopware.
    
    Логика:
    - Если у категории нет parent_id в InSales (верхний уровень) → ROOT_NAV_ID
    - Если parent_id = ID категории "Каталог" → ROOT_NAV_ID (усыновление)
    - Иначе → используем существующую логику (рекурсивно создаем родителя)
    """
    parent_insales_id = category.get("parent_id")
    
    # Верхнеуровневая категория (без родителя)
    if not parent_insales_id:
        return root_nav_id
    
    # Если родитель - это "Каталог", то усыновляем к ROOT_NAV
    if catalog_insales_id and parent_insales_id == catalog_insales_id:
        return root_nav_id
    
    # Обычная логика: ищем родителя в маппинге или создаем его
    parent_key = str(parent_insales_id)
    if parent_key in mapping["categories"]:
        return mapping["categories"][parent_key]
    
    # Рекурсивно создаем родителя
    return ensure_category_fn(parent_insales_id)


def build_category_tree(
    collections: List[Dict[str, Any]],
    collections_by_id: Dict[int, Dict[str, Any]],
    mapping: Dict[str, Any],
    root_nav_id: Optional[str],
    catalog_insales_id: Optional[int],
    shopware_client: Optional[ShopwareClient] = None,
    reparent_existing: bool = False,
) -> Dict[str, Any]:
    """
    Строит дерево категорий для dry-run вывода.
    Возвращает структуру: {parent_id: [children]}
    """
    tree: Dict[str, List[Dict[str, Any]]] = {}
    moves: List[Dict[str, Any]] = []  # Список категорий для перемещения
    
    for category in collections:
        # Пропускаем "Каталог"
        if is_catalog_category(category):
            continue
        
        insales_id = category.get("id")
        if not insales_id:
            continue
        
        # Определяем ожидаемого родителя
        parent_insales_id = category.get("parent_id")
        if not parent_insales_id:
            expected_parent = "ROOT_NAV"
        elif catalog_insales_id and parent_insales_id == catalog_insales_id:
            expected_parent = "ROOT_NAV"
        else:
            parent_cat = collections_by_id.get(parent_insales_id)
            if parent_cat and is_catalog_category(parent_cat):
                expected_parent = "ROOT_NAV"
            else:
                expected_parent = str(parent_insales_id)
        
        if expected_parent not in tree:
            tree[expected_parent] = []
        
        key = str(insales_id)
        exists = key in mapping.get("categories", {})
        shopware_id = mapping.get("categories", {}).get(key)
        
        # Проверяем, нужно ли переместить существующую категорию
        needs_move = False
        current_parent = None
        if reparent_existing and exists and shopware_id and shopware_client:
            # Получаем текущую категорию из Shopware
            current_cat = shopware_client.get_category(shopware_id)
            if current_cat:
                current_parent = current_cat.get("parentId")
                # Определяем ожидаемый parentId в Shopware
                if expected_parent == "ROOT_NAV":
                    expected_shopware_parent = root_nav_id
                else:
                    # Ожидаемый родитель - это другая категория из маппинга
                    expected_shopware_parent = mapping.get("categories", {}).get(expected_parent)
                
                # Проверяем, нужно ли перемещение
                # Перемещаем только если категория должна быть под ROOT_NAV
                if expected_parent == "ROOT_NAV" and expected_shopware_parent:
                    if current_parent != expected_shopware_parent:
                        needs_move = True
                        moves.append({
                            "insales_id": insales_id,
                            "shopware_id": shopware_id,
                            "title": category.get("title", ""),
                            "current_parent": current_parent or "ROOT",
                            "expected_parent": expected_shopware_parent,
                        })
        
        tree[expected_parent].append({
            "id": insales_id,
            "title": category.get("title", ""),
            "is_hidden": category.get("is_hidden", False),
            "exists": exists,
            "needs_move": needs_move,
            "current_parent": current_parent,
            "expected_parent": expected_parent,
        })
    
    return {"tree": tree, "moves": moves}


def print_category_tree(
    tree: Dict[str, List[Dict[str, Any]]],
    collections_by_id: Dict[int, Dict[str, Any]],
    indent: int = 0,
    parent_key: str = "ROOT_NAV",
    moves: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Рекурсивно выводит дерево категорий."""
    children = tree.get(parent_key, [])
    if not children:
        return
    
    prefix = "  " * indent
    for child in sorted(children, key=lambda x: x["title"]):
        status = "[EXISTS]" if child["exists"] else "[NEW]"
        
        # Проверяем, нужно ли перемещение
        if child.get("needs_move") and moves:
            move_info = next(
                (m for m in moves if m["insales_id"] == child["id"]),
                None
            )
            if move_info:
                current = move_info["current_parent"][:8] if move_info["current_parent"] != "ROOT" else "ROOT"
                expected = move_info["expected_parent"][:8] if move_info["expected_parent"] else "ROOT_NAV"
                status = f"[MOVE] {current} → {expected}"
        
        hidden = " (hidden)" if child["is_hidden"] else ""
        print(f"{prefix}{status} {child['title']}{hidden}")
        
        # Рекурсивно выводим детей
        child_key = str(child["id"])
        if child_key in tree:
            print_category_tree(tree, collections_by_id, indent + 1, child_key, moves)


def migrate_categories(
    config: Dict[str, Any],
    structure: Dict[str, Any],
    mapping: Dict[str, Any],
    dry_run: bool = False,
    reparent_existing: bool = False,
) -> Dict[str, Any]:
    """
    Мигрирует категории из InSales в Shopware.
    
    Логика:
    1. Категория "Каталог" не импортируется
    2. Верхнеуровневые категории (без parent_id) → прямые дети ROOT_NAV
    3. Дети "Каталога" → прямые дети ROOT_NAV
    4. Остальные категории сохраняют иерархию
    5. Если reparent_existing=True, перемещает существующие категории под ROOT_NAV при необходимости
    """
    root_nav_id = config["shopware"].get("root_nav_id")
    if not root_nav_id:
        raise ValueError(
            "root_nav_id is not defined in config.json shopware section. "
            "Укажите ID технической категории ROOT_NAV."
        )
    
    shopware_client = build_shopware_client(config) if (not dry_run or reparent_existing) else None
    collections: List[Dict[str, Any]] = structure.get("collections", [])
    collections_by_id = {item["id"]: item for item in collections}
    
    # Находим ID категории "Каталог" в InSales
    catalog_insales_id: Optional[int] = None
    for cat in collections:
        if is_catalog_category(cat):
            catalog_insales_id = cat.get("id")
            break
    
    if catalog_insales_id:
        print(f"[INFO] Найдена категория 'Каталог' в InSales (ID: {catalog_insales_id}). Она будет пропущена при импорте.")
    
    # Строим дерево для анализа
    tree_data = build_category_tree(
        collections,
        collections_by_id,
        mapping,
        root_nav_id,
        catalog_insales_id,
        shopware_client=shopware_client,
        reparent_existing=reparent_existing,
    )
    tree = tree_data["tree"]
    moves = tree_data["moves"]
    
    # Dry run: только вывод дерева
    if dry_run:
        print("\n=== DRY RUN: Планируемая структура категорий ===\n")
        print(f"ROOT_NAV ({root_nav_id})")
        print_category_tree(tree, collections_by_id, moves=moves if reparent_existing else None)
        
        # Статистика
        total = sum(len(children) for children in tree.values())
        existing = sum(
            1
            for children in tree.values()
            for child in children
            if child.get("exists")
        )
        new_count = total - existing
        skipped = len([c for c in collections if is_catalog_category(c)])
        move_count = len(moves) if reparent_existing else 0
        
        print(f"\n=== Статистика ===")
        print(f"Всего категорий для импорта: {total}")
        print(f"  - Уже существуют в Shopware: {existing}")
        print(f"  - Будет создано новых: {new_count}")
        print(f"  - Пропущено (Каталог): {skipped}")
        if reparent_existing:
            print(f"  - Будет перемещено под ROOT_NAV: {move_count}")
        print(f"\nРежим: DRY RUN (изменения не применены)")
        return mapping
    
    # Реальный импорт
    total = len(collections)
    created = 0
    skipped = 0
    updated = 0
    moved = 0
    
    def ensure_category(insales_id: int) -> str:
        nonlocal created, updated, skipped
        
        key = str(insales_id)
        
        # Проверяем, существует ли уже в маппинге
        if key in mapping["categories"]:
            return mapping["categories"][key]
        
        category = collections_by_id.get(insales_id)
        if not category:
            raise KeyError(f"Collection {insales_id} not found in structure")
        
        # Пропускаем категорию "Каталог"
        if is_catalog_category(category):
            skipped += 1
            print(f"[SKIP] Категория 'Каталог' ({insales_id}) пропущена")
            raise ValueError("Catalog category should be skipped")
        
        # Определяем родителя
        parent_id = resolve_parent_id(
            category,
            mapping,
            collections_by_id,
            ensure_category,
            root_nav_id,
            catalog_insales_id,
        )
        
        # Создаем payload
        new_id = uuid4().hex
        is_hidden = category.get("is_hidden", False)
        
        payload: Dict[str, Any] = {
            "id": new_id,
            "name": category["title"],
            "active": not is_hidden,  # active = not is_hidden
        }
        
        if parent_id:
            payload["parentId"] = parent_id
        
        def _trim(value: Optional[str], limit: int) -> Optional[str]:
            if not value:
                return None
            value = value.strip()
            if not value:
                return None
            if len(value) > limit:
                return value[: limit - 1] + "…"
            return value
        
        description = category.get("description")
        if description:
            payload["description"] = description
        
        meta_title = _trim(category.get("html_title"), 255)
        if meta_title:
            payload["metaTitle"] = meta_title
        meta_description = _trim(category.get("meta_description"), 255)
        if meta_description:
            payload["metaDescription"] = meta_description
        
        payload["translations"] = {
            "ru-RU": {
                "name": category["title"],
                "description": description or "",
                "metaTitle": meta_title or "",
                "metaDescription": meta_description or "",
            }
        }
        
        # Создаем категорию в Shopware
        try:
            shopware_client.create_category(payload)
            mapping["categories"][key] = new_id
            created += 1
            print(f"[OK] Category {category['title']} ({insales_id}) -> {new_id}")
        except Exception as e:
            print(f"[ERROR] Failed to create category {category['title']} ({insales_id}): {e}")
            raise
        
        return new_id
    
    # Импортируем все категории (кроме "Каталог")
    for category in collections:
        try:
            ensure_category(category["id"])
        except ValueError:
            # Это была категория "Каталог", уже обработана
            continue
        except Exception as e:
            print(f"[WARN] Пропущена категория {category.get('id')}: {e}")
            continue
    
    # Репарентинг существующих категорий
    if reparent_existing:
        print(f"\n=== Репарентинг существующих категорий ===")
        for move_info in moves:
            shopware_id = move_info["shopware_id"]
            expected_parent = move_info["expected_parent"]
            category_title = move_info["title"]
            
            try:
                # Обновляем только parentId
                shopware_client.update_category(shopware_id, {"parentId": expected_parent})
                moved += 1
                current = move_info["current_parent"][:8] if move_info["current_parent"] != "ROOT" else "ROOT"
                expected = expected_parent[:8] if expected_parent else "ROOT_NAV"
                print(f"[MOVE] {category_title}: {current} → {expected}")
            except Exception as e:
                print(f"[ERROR] Failed to move category {category_title} ({shopware_id}): {e}")
    
    mapping["last_updated"] = datetime.now(timezone.utc).isoformat()
    print(f"\n=== Итоги импорта ===")
    print(f"Всего категорий в InSales: {total}")
    print(f"Создано новых: {created}")
    print(f"Пропущено (Каталог): {skipped}")
    if reparent_existing:
        print(f"Перемещено под ROOT_NAV: {moved}")
    print(f"Обработано всего: {created + skipped + (moved if reparent_existing else 0)}")
    
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Миграция категорий Insales -> Shopware.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  # Dry run (проверка без изменений)
  python migrate_categories.py --dry-run
  
  # Dry run с проверкой репарентинга
  python migrate_categories.py --dry-run --reparent-existing
  
  # Реальный импорт
  python migrate_categories.py
  
  # Реальный импорт с репарентингом существующих категорий
  python migrate_categories.py --reparent-existing
  
  # Указать другой конфиг
  python migrate_categories.py --config custom_config.json
        """,
    )
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--structure", type=Path, default=STRUCTURE_PATH)
    parser.add_argument("--map", type=Path, default=MAP_PATH)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Режим проверки без реальных изменений в Shopware",
    )
    parser.add_argument(
        "--reparent-existing",
        action="store_true",
        help="Перемещать существующие категории под ROOT_NAV при необходимости",
    )
    args = parser.parse_args()
    
    config = load_json(args.config)
    structure = load_json(args.structure)
    mapping = load_json(
        args.map,
        default={"categories": {}, "properties": {}, "products": {}, "last_updated": None},
    )
    
    updated_map = migrate_categories(
        config,
        structure,
        mapping,
        dry_run=args.dry_run,
        reparent_existing=args.reparent_existing,
    )
    
    if not args.dry_run:
        save_json(args.map, updated_map)
        print(f"\n[OK] Migration map сохранен: {args.map}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

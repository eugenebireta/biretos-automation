"""
Отбор 10 товаров из snapshot для пробного импорта.
Условия:
- active = true
- quantity > 0
- разные категории (минимум 3 ветки)
- исключить SKU 500944222
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

from import_utils import ROOT

SNAPSHOT_NDJSON = ROOT / "insales_snapshot" / "products.ndjson"
EXCLUDED_SKU = "500944222"


def load_products_from_snapshot() -> List[Dict[str, Any]]:
    """Загружает все товары из snapshot."""
    if not SNAPSHOT_NDJSON.exists():
        print(f"[ERROR] Snapshot не найден: {SNAPSHOT_NDJSON}")
        return []
    
    products = []
    with SNAPSHOT_NDJSON.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                product = json.loads(line)
                products.append(product)
            except json.JSONDecodeError:
                continue
    
    return products


def get_product_sku(product: Dict[str, Any]) -> str:
    """Извлекает SKU из товара (из первого variant)."""
    variants = product.get("variants", [])
    if variants:
        return str(variants[0].get("sku", ""))
    return ""


def get_product_category_id(product: Dict[str, Any]) -> str:
    """Извлекает category_id из товара (для группировки по категориям)."""
    # Используем canonical_url_collection_id или category_id
    canonical_id = product.get("canonical_url_collection_id")
    if canonical_id:
        return str(canonical_id)
    
    category_id = product.get("category_id")
    if category_id:
        return str(category_id)
    
    # Если есть collections_ids, берем первый
    collections_ids = product.get("collections_ids", [])
    if collections_ids:
        return str(collections_ids[0])
    
    return ""


def is_product_valid(product: Dict[str, Any]) -> bool:
    """Проверяет, соответствует ли товар условиям отбора."""
    # В snapshot нет поля "active", используем "available" или проверяем, что товар не archived
    if product.get("archived", False):
        return False
    
    # Проверяем quantity > 0 в variants
    variants = product.get("variants", [])
    if not variants:
        return False
    
    # Проверяем каждый variant
    has_valid_variant = False
    for variant in variants:
        sku = str(variant.get("sku", ""))
        
        # Проверяем, что SKU не исключен
        if sku == EXCLUDED_SKU:
            continue
        
        if not sku:
            continue
        
        # Проверяем quantity > 0
        quantity = variant.get("quantity")
        if quantity is None or quantity <= 0:
            continue
        
        has_valid_variant = True
        break
    
    return has_valid_variant


def select_diverse_products(products: List[Dict[str, Any]], count: int = 10) -> List[Dict[str, Any]]:
    """Отбирает товары из разных категорий."""
    # Фильтруем валидные товары
    valid_products = [p for p in products if is_product_valid(p)]
    
    if len(valid_products) < count:
        print(f"[WARNING] Найдено только {len(valid_products)} валидных товаров, требуется {count}")
        return valid_products[:count]
    
    # Группируем по категориям
    category_groups: Dict[str, List[Dict[str, Any]]] = {}
    for product in valid_products:
        cat_id = get_product_category_id(product)
        if cat_id:
            if cat_id not in category_groups:
                category_groups[cat_id] = []
            category_groups[cat_id].append(product)
    
    # Отбираем товары из разных категорий
    selected: List[Dict[str, Any]] = []
    used_categories: Set[str] = set()
    
    # Сначала берем по одному товару из каждой категории
    for cat_id, cat_products in category_groups.items():
        if len(selected) >= count:
            break
        if cat_products:
            selected.append(cat_products[0])
            used_categories.add(cat_id)
    
    # Если не хватило, добавляем из уже использованных категорий
    if len(selected) < count:
        for cat_id, cat_products in category_groups.items():
            if len(selected) >= count:
                break
            for product in cat_products:
                if len(selected) >= count:
                    break
                if product not in selected:
                    selected.append(product)
    
    return selected[:count]


def main():
    print("=" * 80)
    print("ОТБОР ТОВАРОВ ДЛЯ ПРОБНОГО ИМПОРТА")
    print("=" * 80)
    print()
    
    # Загружаем товары
    print("1) Загрузка товаров из snapshot...")
    products = load_products_from_snapshot()
    print(f"   [OK] Загружено товаров: {len(products)}")
    
    # Отбираем товары
    print("2) Отбор 10 товаров из разных категорий...")
    selected = select_diverse_products(products, count=10)
    
    if len(selected) < 10:
        print(f"[ERROR] Не удалось отобрать 10 товаров (найдено: {len(selected)})")
        return 1
    
    print(f"   [OK] Отобрано товаров: {len(selected)}")
    
    # Выводим список отобранных товаров
    print()
    print("3) Отобранные товары:")
    print("-" * 80)
    skus = []
    for i, product in enumerate(selected, 1):
        sku = get_product_sku(product)
        title = product.get("title", "N/A")
        cat_id = get_product_category_id(product)
        quantity = product.get("variants", [{}])[0].get("quantity", 0)
        skus.append(sku)
        print(f"   {i:2d}. SKU: {sku:15s} | Title: {title[:40]:40s} | Category: {cat_id[:20]:20s} | Qty: {quantity}")
    
    # Сохраняем список SKU в файл
    output_file = ROOT / "_reports" / "selected_products_10.txt"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as f:
        for sku in skus:
            f.write(f"{sku}\n")
    
    print()
    print(f"   [OK] Список SKU сохранен: {output_file}")
    print()
    print("=" * 80)
    print("ОТБОР ЗАВЕРШЕН")
    print("=" * 80)
    print()
    print("Список SKU для импорта:")
    print(", ".join(skus))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

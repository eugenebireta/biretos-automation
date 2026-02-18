from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from clients import ShopwareClient, ShopwareConfig


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config.json"
DEFAULT_MAP = ROOT / "migration_map.json"
DEFAULT_STRUCTURE = ROOT / "logs" / "insales_structure.json"
BACKUP_ROOT = ROOT / "backup_insales"
OUTPUT_DIR = ROOT / "output"


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


def resolve_products_path(explicit: Optional[Path]) -> Path:
    if explicit:
        if not explicit.exists():
            raise FileNotFoundError(f"Products backup not found: {explicit}")
        return explicit

    if not BACKUP_ROOT.exists():
        raise FileNotFoundError("Directory backup_insales does not exist")

    folders: List[Path] = sorted(
        (item for item in BACKUP_ROOT.iterdir() if item.is_dir()),
        reverse=True,
    )
    for folder in folders:
        candidate = folder / "products.json"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("products.json not found in any backup directory")


def ensure_product_uuid(mapping: Dict[str, Any], insales_id: int) -> str:
    products_map = mapping.setdefault("products", {})
    key = str(insales_id)
    if key not in products_map:
        products_map[key] = uuid4().hex
    return products_map[key]


def normalize_text(*parts: Optional[str]) -> str:
    chunks = [part.strip() for part in parts if part]
    return "\n\n".join(chunk for chunk in chunks if chunk)


def safe_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def join_tokens(tokens: Iterable[str]) -> str:
    return "|".join(token for token in tokens if token)


def build_category_path(
    collection_id: int,
    collections_by_id: Dict[int, Dict[str, Any]],
    category_map: Dict[str, str],
    visited: Optional[set] = None,
) -> List[str]:
    """
    Строит полный путь категорий от указанной коллекции до корня.
    
    Args:
        collection_id: ID коллекции InSales
        collections_by_id: Словарь всех коллекций {id: collection}
        category_map: Маппинг InSales ID -> Shopware ID
        visited: Множество посещённых ID для защиты от циклов
    
    Returns:
        Список Shopware category IDs от корня до указанной категории
    """
    if visited is None:
        visited = set()
    
    # Защита от циклов
    if collection_id in visited:
        return []
    visited.add(collection_id)
    
    collection = collections_by_id.get(collection_id)
    if not collection:
        return []
    
    path: List[str] = []
    
    # Рекурсивно получаем путь родительской категории
    parent_id = collection.get("parent_id")
    if parent_id:
        parent_path = build_category_path(parent_id, collections_by_id, category_map, visited)
        path.extend(parent_path)
    
    # Добавляем текущую категорию
    mapped_id = category_map.get(str(collection_id))
    if mapped_id:
        path.append(mapped_id)
    else:
        # Логируем, если категория не найдена в маппинге
        collection_title = collection.get("title", "Unknown")
        print(f"  [WARNING] Категория InSales не найдена в category_map: ID={collection_id}, Title='{collection_title}'")
    
    return path


def get_all_category_paths(
    collections_ids: List[int],
    collections_by_id: Dict[int, Dict[str, Any]],
    category_map: Dict[str, str],
) -> List[str]:
    """
    Получает все категории из полных путей для всех collections_ids.
    
    Args:
        collections_ids: Список ID коллекций InSales для товара
        collections_by_id: Словарь всех коллекций
        category_map: Маппинг InSales ID -> Shopware ID
    
    Returns:
        Список уникальных Shopware category IDs (все категории из всех путей)
    """
    all_category_ids: set = set()
    
    for collection_id in collections_ids:
        path = build_category_path(collection_id, collections_by_id, category_map)
        all_category_ids.update(path)
    
    return list(all_category_ids)


def find_deepest_category(
    collections_ids: List[int],
    collections_by_id: Dict[int, Dict[str, Any]],
    category_map: Dict[str, str],
) -> Optional[str]:
    """
    Находит самую глубокую категорию (leaf) для товара.
    
    Args:
        collections_ids: Список ID коллекций InSales для товара
        collections_by_id: Словарь всех коллекций
        category_map: Маппинг InSales ID -> Shopware ID
    
    Returns:
        Shopware ID самой глубокой категории или None
    """
    deepest_id: Optional[int] = None
    max_depth = -1
    
    def get_depth(collection_id: int, visited: Optional[set] = None) -> int:
        """Вычисляет глубину категории (количество уровней до корня)"""
        if visited is None:
            visited = set()
        
        if collection_id in visited:
            return 0
        visited.add(collection_id)
        
        collection = collections_by_id.get(collection_id)
        if not collection:
            return 0
        
        parent_id = collection.get("parent_id")
        if parent_id:
            return 1 + get_depth(parent_id, visited)
        return 1
    
    for collection_id in collections_ids:
        depth = get_depth(collection_id)
        if depth > max_depth:
            max_depth = depth
            deepest_id = collection_id
    
    if deepest_id:
        return category_map.get(str(deepest_id))
    return None


def extract_properties(
    product: Dict[str, Any],
    property_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for characteristic in product.get("characteristics", []) or []:
        property_id = characteristic.get("property_id")
        if property_id is None:
            continue
        group_id = property_map.get(f"prop_{property_id}") or property_map.get(
            f"opt_{property_id}"
        )
        if not group_id:
            continue
        payload.append(
            {
                "property_id": property_id,
                "group_id": group_id,
                "value": (characteristic.get("title") or "").strip(),
                "permalink": characteristic.get("permalink"),
            }
        )
    return payload


def build_row(
    product: Dict[str, Any],
    *,
    product_uuid: str,
    category_map: Dict[str, str],
    property_map: Dict[str, str],
    tax_id: str,
    currency_iso: str,
    insales_host: str,
    collections_by_id: Dict[int, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    variants = product.get("variants") or []
    if not variants:
        return None
    variant = variants[0]

    sku = (variant.get("sku") or "").strip() or str(product["id"])
    price = safe_float(
        variant.get("price_in_site_currency")
        or variant.get("price")
        or variant.get("base_price")
    )
    stock = safe_int(variant.get("quantity"))

    # Получаем все категории из полных путей
    collections_ids = product.get("collections_ids") or []
    all_category_ids = get_all_category_paths(collections_ids, collections_by_id, category_map)
    
    # ВАЛИДАЦИЯ
    if not all_category_ids:
        product_title = product.get("title", "Unknown")
        product_id = product.get("id", "Unknown")
        print(f"  [ERROR] Товар остался без категорий: ID={product_id}, Title='{product_title}'")
        # Не пропускаем товар, но логируем ошибку
    
    # Выбираем только самую глубокую категорию (будет проверена на листовость позже)
    # Используем существующую функцию find_deepest_category
    leaf_category_id = find_deepest_category(collections_ids, collections_by_id, category_map)
    
    # Если не нашли, используем первую из всех категорий
    if not leaf_category_id and all_category_ids:
        leaf_category_id = all_category_ids[0]
    
    # В CSV сохраняем только листовую категорию
    category_ids = [leaf_category_id] if leaf_category_id else []

    images = [
        img.get("original_url") or img.get("url")
        for img in product.get("images", [])
        if img.get("original_url") or img.get("url")
    ]

    properties_payload = extract_properties(product, property_map)

    description = normalize_text(
        product.get("short_description"),
        product.get("description"),
    )

    active = not product.get("is_hidden", False)
    insales_permalink = product.get("permalink") or ""
    insales_url = f"https://{insales_host}/product/{insales_permalink}".rstrip("/")

    result = {
        "shopwareId": product_uuid,
        "insalesId": product["id"],
        "productNumber": sku,
        "name": product.get("title") or "",
        "description": description,
        "price": f"{price:.2f}",
        "stock": stock,
        "currencyIso": currency_iso,
        "taxId": tax_id,
        "active": 1 if active else 0,
        "categoryIds": join_tokens(category_ids),
        "imageUrls": join_tokens(images),
        "propertiesJson": json.dumps(properties_payload, ensure_ascii=False),
        "insalesUrl": insales_url,
        "slug": insales_permalink,
    }
    
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Генерация CSV для импорта товаров в Shopware."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--map", dest="map_path", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--products", type=Path, help="Путь до products.json из бэкапа")
    parser.add_argument(
        "--structure",
        type=Path,
        default=DEFAULT_STRUCTURE,
        help="Путь к insales_structure.json (для работы с иерархией категорий)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR / "products_import.csv",
    )
    parser.add_argument(
        "--currency-iso",
        dest="currency_iso",
        default="RUB",
        help="ISO код валюты для цены (по умолчанию RUB).",
    )
    args = parser.parse_args()

    config = load_json(args.config)
    mapping = load_json(
        args.map_path,
        default={"categories": {}, "properties": {}, "products": {}},
    )
    products_path = resolve_products_path(args.products)
    products_data = load_json(products_path)
    
    # Загружаем структуру InSales для работы с иерархией категорий
    structure = load_json(
        args.structure,
        default={"collections": []},
    )
    collections = structure.get("collections", [])
    collections_by_id = {item["id"]: item for item in collections}
    
    # Проверка наличия категории "Переключатели" (для валидации)
    pereklyuchateli_found = False
    for collection in collections:
        title = collection.get("title", "").lower()
        if "переключател" in title:
            pereklyuchateli_found = True
            print(f"  [INFO] Найдена категория 'Переключатели': ID={collection.get('id')}, Title='{collection.get('title')}'")
            break
    
    if not pereklyuchateli_found:
        print("  [FATAL ERROR] Категория 'Переключатели' отсутствует в структуре InSales!")
        print("  [FATAL ERROR] Проверьте структуру данных InSales.")
        return 1

    shop_cfg = ShopwareConfig(
        url=config["shopware"]["url"],
        access_key_id=config["shopware"]["access_key_id"],
        secret_access_key=config["shopware"]["secret_access_key"],
    )
    shopware_client = ShopwareClient(shop_cfg)
    tax_id = shopware_client.get_default_tax_id()

    category_map = {str(k): v for k, v in mapping.get("categories", {}).items()}
    property_map = {str(k): v for k, v in mapping.get("properties", {}).items()}
    insales_host = config["insales"]["host"]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []

    for product in products_data:
        product_uuid = ensure_product_uuid(mapping, product["id"])
        row = build_row(
            product,
            product_uuid=product_uuid,
            category_map=category_map,
            property_map=property_map,
            tax_id=tax_id,
            currency_iso=args.currency_iso,
            insales_host=insales_host,
            collections_by_id=collections_by_id,
        )
        if not row:
            continue
        rows.append(row)

    if not rows:
        print("Нет товаров, удовлетворяющих условиям, CSV не создан.")
        return 1

    fieldnames = [
        "shopwareId",
        "insalesId",
        "productNumber",
        "name",
        "description",
        "price",
        "stock",
        "currencyIso",
        "taxId",
        "active",
        "categoryIds",
        "imageUrls",
        "propertiesJson",
        "insalesUrl",
        "slug",
    ]

    with args.output.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    save_json(args.map_path, mapping)

    print(f"CSV сохранён: {args.output} (товаров: {len(rows)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())





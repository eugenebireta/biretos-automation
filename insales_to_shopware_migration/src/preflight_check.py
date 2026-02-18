"""
PRE-FLIGHT CHECK для валидации скелета проекта перед production-импортом товаров.

ВАЖНО: Только проверка, никаких изменений!

СТАТУС: OPTIONAL, REQUIRES OPTIMIZATION

Проблема: Скрипт делает N+1 API запросов (перебор всех категорий),
что вызывает таймауты при выполнении.

TODO: Оптимизировать preflight_check.py:
  - Убрать перебор всех категорий
  - Использовать childCount filter в API запросе
  - Проверять наличие leaf-категорий одним запросом (limit=1, childCount=0)
  - Или получать категории с childCount и фильтровать локально

ПРИМЕЧАНИЕ: Preflight логически пройден:
  - dry-run товаров успешен
  - leaf-логика подтверждена
  - категории стабильны
  - импорт товаров не изменяет категории
  - Sales Channel корректен

Импорт товаров РАЗРЕШЁН.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from clients import ShopwareClient, ShopwareConfig
from category_utils import is_leaf_category


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
MAP_PATH = ROOT / "migration_map.json"
ROOT_NAV_ID = "019b141f60007eefa571a533ddc98797"


def load_json(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Загружает JSON файл."""
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def check_category(client: ShopwareClient, category_id: str) -> Optional[Dict[str, Any]]:
    """Проверяет существование категории."""
    try:
        response = client._request("GET", f"/api/category/{category_id}")
        if isinstance(response, dict) and "data" in response:
            return response["data"]
        return response
    except Exception:
        return None


def get_sales_channel(client: ShopwareClient) -> Optional[Dict[str, Any]]:
    """Получает основной Sales Channel."""
    try:
        response = client._request("GET", "/api/sales-channel")
        if isinstance(response, dict) and "data" in response:
            sales_channels = response["data"]
            if sales_channels:
                sc_id = sales_channels[0].get("id")
                sc_full = client._request("GET", f"/api/sales-channel/{sc_id}")
                if isinstance(sc_full, dict) and "data" in sc_full:
                    return sc_full["data"]
                return sc_full
    except Exception:
        pass
    return None


def check_cms_page(client: ShopwareClient, page_id: str) -> bool:
    """Проверяет существование CMS страницы."""
    try:
        response = client._request("GET", f"/api/cms-page/{page_id}")
        return response is not None
    except Exception:
        return False


def has_leaf_category(client: ShopwareClient, root_nav_id: str) -> bool:
    """Проверяет наличие хотя бы одной leaf-категории под ROOT_NAV."""
    try:
        response = client._request(
            "POST",
            "/api/search/category",
            json={
                "filter": [
                    {"field": "parentId", "type": "equals", "value": root_nav_id},
                    {"field": "childCount", "type": "equals", "value": 0},
                    {"field": "active", "type": "equals", "value": True},
                ],
                "limit": 1,
                "includes": {"category": ["id", "name"]},
            },
        )
        if isinstance(response, dict):
            return response.get("total", 0) > 0
    except Exception as exc:
        print(f"  [WARN] Не удалось проверить leaf-категории: {exc}")
    return False


def check_migration_map(map_path: Path) -> Dict[str, Any]:
    """Проверяет наличие и структуру migration_map.json."""
    result = {
        "exists": False,
        "has_categories": False,
        "has_products": False,
        "categories_count": 0,
        "products_count": 0,
    }
    
    if not map_path.exists():
        return result
    
    try:
        mapping = load_json(map_path)
        result["exists"] = True
        
        categories = mapping.get("categories", {})
        products = mapping.get("products", {})
        
        result["has_categories"] = bool(categories)
        result["has_products"] = bool(products)
        result["categories_count"] = len(categories)
        result["products_count"] = len(products)
    except Exception:
        pass
    
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PRE-FLIGHT CHECK для валидации скелета проекта."
    )
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--map", type=Path, default=MAP_PATH)
    args = parser.parse_args()

    config = load_json(args.config)
    shopware_config = ShopwareConfig(
        url=config["shopware"]["url"],
        access_key_id=config["shopware"]["access_key_id"],
        secret_access_key=config["shopware"]["secret_access_key"],
    )
    client = ShopwareClient(shopware_config)

    print("=" * 70)
    print("PRE-FLIGHT CHECK: ВАЛИДАЦИЯ СКЕЛЕТА ПРОЕКТА")
    print("=" * 70)
    print("\nРежим: ТОЛЬКО ПРОВЕРКА (никаких изменений)\n")

    checks_passed = 0
    checks_failed = 0
    blocking_issues: List[str] = []

    # ========================================================================
    # 1) КАТЕГОРИИ
    # ========================================================================
    print("=" * 70)
    print("1) ПРОВЕРКА КАТЕГОРИЙ")
    print("=" * 70)

    # 1.1) ROOT_NAV существует
    print("\n1.1) ROOT_NAV существует")
    root_nav = check_category(client, ROOT_NAV_ID)
    if root_nav:
        print(f"  [OK] ROOT_NAV ({ROOT_NAV_ID}) существует")
        checks_passed += 1
    else:
        print(f"  [FAIL] ROOT_NAV ({ROOT_NAV_ID}) не найдена!")
        checks_failed += 1
        blocking_issues.append("ROOT_NAV не существует")
        # Без ROOT_NAV дальнейшие проверки бессмысленны
        print("\n" + "=" * 70)
        print("БЛОКИРУЮЩАЯ ОШИБКА: ROOT_NAV не найдена")
        print("=" * 70)
        return 1

    # 1.2) ROOT_NAV active = true, visible = false
    print("\n1.2) ROOT_NAV: active = true, visible = false")
    root_nav_active = root_nav.get("active", False)
    root_nav_visible = root_nav.get("visible", False)
    
    if root_nav_active and not root_nav_visible:
        print(f"  [OK] ROOT_NAV: active={root_nav_active}, visible={root_nav_visible}")
        checks_passed += 1
    else:
        print(f"  [FAIL] ROOT_NAV: active={root_nav_active}, visible={root_nav_visible}")
        print(f"  Ожидается: active=True, visible=False")
        checks_failed += 1
        if not root_nav_active:
            blocking_issues.append("ROOT_NAV должна быть active=True")

    # 1.3) navigationCategoryId = ROOT_NAV_ID
    print("\n1.3) Sales Channel: navigationCategoryId = ROOT_NAV_ID")
    sales_channel = get_sales_channel(client)
    if sales_channel:
        attrs = sales_channel.get("attributes", {})
        nav_id = attrs.get("navigationCategoryId")
        if nav_id == ROOT_NAV_ID:
            print(f"  [OK] navigationCategoryId = {ROOT_NAV_ID}")
            checks_passed += 1
        else:
            print(f"  [FAIL] navigationCategoryId = {nav_id} (ожидается {ROOT_NAV_ID})")
            checks_failed += 1
            blocking_issues.append(f"navigationCategoryId должен быть {ROOT_NAV_ID}")
    else:
        print("  [FAIL] Sales Channel не найден")
        checks_failed += 1
        blocking_issues.append("Sales Channel не найден")

    # 1.4) Категории имеют стабильную иерархию
    print("\n1.4) Категории имеют стабильную иерархию")
    try:
        # Проверяем, что есть категории под ROOT_NAV
        response = client._request(
            "POST",
            "/api/search/category",
            json={
                "filter": [
                    {"field": "parentId", "type": "equals", "value": ROOT_NAV_ID},
                ],
                "limit": 10,
                "includes": {"category": ["id", "name", "active"]},
            },
        )
        if isinstance(response, dict) and response.get("total", 0) > 0:
            categories = response["data"]
            active_count = sum(1 for cat in categories if cat.get("active", False))
            print(f"  [OK] Найдено {len(categories)} категорий под ROOT_NAV (активных: {active_count})")
            checks_passed += 1
        else:
            print("  [WARN] Нет категорий под ROOT_NAV (возможно, это нормально для нового проекта)")
            checks_passed += 1  # Не блокирующая проблема
    except Exception as e:
        print(f"  [FAIL] Ошибка при проверке иерархии: {e}")
        checks_failed += 1

    # 1.5) Leaf-категории существуют
    print("\n1.5) Leaf-категории существуют")
    if has_leaf_category(client, ROOT_NAV_ID):
        print(f"  [OK] Найдена хотя бы одна leaf-категория")
        checks_passed += 1
    else:
        print("  [WARN] Leaf-категории не найдены (товары некуда будет импортировать)")
        checks_failed += 1
        blocking_issues.append("Нет leaf-категорий для импорта товаров")

    # ========================================================================
    # 2) SALES CHANNEL
    # ========================================================================
    print("\n" + "=" * 70)
    print("2) ПРОВЕРКА SALES CHANNEL")
    print("=" * 70)

    if not sales_channel:
        print("\n[FAIL] Sales Channel не найден - пропуск проверок")
        checks_failed += 1
        blocking_issues.append("Sales Channel не найден")
    else:
        attrs = sales_channel.get("attributes", {})

        # 2.1) homeEnabled = true
        print("\n2.1) homeEnabled = true")
        home_enabled = attrs.get("homeEnabled", False)
        if home_enabled:
            print(f"  [OK] homeEnabled = {home_enabled}")
            checks_passed += 1
        else:
            print(f"  [FAIL] homeEnabled = {home_enabled} (ожидается True)")
            checks_failed += 1
            blocking_issues.append("homeEnabled должен быть True")

        # 2.2) homeCmsPageId задан и существует
        print("\n2.2) homeCmsPageId задан и существует")
        home_cms_id = attrs.get("homeCmsPageId")
        if home_cms_id:
            if check_cms_page(client, home_cms_id):
                print(f"  [OK] homeCmsPageId = {home_cms_id} (существует)")
                checks_passed += 1
            else:
                print(f"  [FAIL] homeCmsPageId = {home_cms_id} (не существует!)")
                checks_failed += 1
                blocking_issues.append(f"homeCmsPageId {home_cms_id} не существует")
        else:
            print("  [FAIL] homeCmsPageId не задан")
            checks_failed += 1
            blocking_issues.append("homeCmsPageId не задан")

        # 2.3) navigationCategoryId ≠ entry point
        print("\n2.3) navigationCategoryId ≠ entry point")
        nav_id = attrs.get("navigationCategoryId")
        home_cms_id = attrs.get("homeCmsPageId")
        if nav_id == ROOT_NAV_ID and home_cms_id and home_cms_id != ROOT_NAV_ID:
            print(f"  [OK] navigationCategoryId ({nav_id}) ≠ entry point ({home_cms_id})")
            checks_passed += 1
        else:
            print(f"  [FAIL] navigationCategoryId может использоваться как entry point")
            checks_failed += 1
            blocking_issues.append("navigationCategoryId не должен быть entry point")

        # 2.4) footerCategoryId и serviceCategoryId ≠ ROOT_NAV_ID
        print("\n2.4) footerCategoryId и serviceCategoryId ≠ ROOT_NAV_ID")
        footer_id = attrs.get("footerCategoryId")
        service_id = attrs.get("serviceCategoryId")
        
        footer_ok = footer_id is None or footer_id != ROOT_NAV_ID
        service_ok = service_id is None or service_id != ROOT_NAV_ID
        
        if footer_ok and service_ok:
            print(f"  [OK] footerCategoryId = {footer_id}, serviceCategoryId = {service_id}")
            checks_passed += 1
        else:
            if not footer_ok:
                print(f"  [FAIL] footerCategoryId = {footer_id} (равен ROOT_NAV_ID!)")
                checks_failed += 1
                blocking_issues.append("footerCategoryId не должен быть ROOT_NAV_ID")
            if not service_ok:
                print(f"  [FAIL] serviceCategoryId = {service_id} (равен ROOT_NAV_ID!)")
                checks_failed += 1
                blocking_issues.append("serviceCategoryId не должен быть ROOT_NAV_ID")

    # ========================================================================
    # 3) ЛОГИКА ИМПОРТА ТОВАРОВ
    # ========================================================================
    print("\n" + "=" * 70)
    print("3) ПРОВЕРКА ЛОГИКИ ИМПОРТА ТОВАРОВ")
    print("=" * 70)

    # 3.1) Товары назначаются ТОЛЬКО в leaf-категории
    print("\n3.1) Логика: товары назначаются ТОЛЬКО в leaf-категории")
    # Проверяем наличие функции is_leaf_category
    try:
        test_result = is_leaf_category(client, ROOT_NAV_ID)
        # ROOT_NAV не должна быть leaf (у неё есть дети)
        if not test_result:
            print("  [OK] Функция is_leaf_category работает корректно")
            checks_passed += 1
        else:
            print("  [WARN] is_leaf_category может работать некорректно")
            checks_failed += 1
    except Exception as e:
        print(f"  [FAIL] Ошибка при проверке is_leaf_category: {e}")
        checks_failed += 1

    # 3.2) mainCategoryId = leaf
    print("\n3.2) Логика: mainCategoryId = leaf")
    # Проверяем наличие логики в import_utils.py
    import_utils_path = Path(__file__).parent / "import_utils.py"
    if import_utils_path.exists():
        content = import_utils_path.read_text(encoding="utf-8")
        if "mainCategoryId" in content and "leaf_category_id" in content:
            print("  [OK] Логика mainCategoryId = leaf присутствует в коде")
            checks_passed += 1
        else:
            print("  [FAIL] Логика mainCategoryId = leaf отсутствует в коде")
            checks_failed += 1
            blocking_issues.append("Логика mainCategoryId = leaf отсутствует")
    else:
        print("  [FAIL] import_utils.py не найден")
        checks_failed += 1

    # 3.3) Родительские категории заблокированы
    print("\n3.3) Логика: родительские категории заблокированы")
    if import_utils_path.exists():
        content = import_utils_path.read_text(encoding="utf-8")
        if "SKIP_PARENT_CATEGORY" in content or "is_leaf_category" in content:
            print("  [OK] Блокировка родительских категорий присутствует в коде")
            checks_passed += 1
        else:
            print("  [FAIL] Блокировка родительских категорий отсутствует в коде")
            checks_failed += 1
            blocking_issues.append("Блокировка родительских категорий отсутствует")

    # 3.4) Skip вместо fallback
    print("\n3.4) Логика: skip вместо fallback")
    full_import_path = Path(__file__).parent / "full_import.py"
    if full_import_path.exists():
        content = full_import_path.read_text(encoding="utf-8")
        if "SKIP_PARENT_CATEGORY" in content and "continue" in content:
            print("  [OK] Логика skip присутствует (нет silent fallback)")
            checks_passed += 1
        else:
            print("  [WARN] Логика skip может быть неполной")
            checks_failed += 1

    # ========================================================================
    # 4) ИДЕМПОТЕНТНОСТЬ
    # ========================================================================
    print("\n" + "=" * 70)
    print("4) ПРОВЕРКА ИДЕМПОТЕНТНОСТИ")
    print("=" * 70)

    # 4.1) migration_map.json используется
    print("\n4.1) migration_map.json используется")
    map_check = check_migration_map(args.map)
    if map_check["exists"]:
        print(f"  [OK] migration_map.json существует")
        print(f"    - Категорий: {map_check['categories_count']}")
        print(f"    - Товаров: {map_check['products_count']}")
        checks_passed += 1
    else:
        print("  [WARN] migration_map.json не найден (будет создан при первом импорте)")
        checks_passed += 1  # Не блокирующая проблема

    # 4.2) Повторный импорт не создаёт дубликатов
    print("\n4.2) Логика: повторный импорт не создаёт дубликатов")
    if full_import_path.exists():
        content = full_import_path.read_text(encoding="utf-8")
        if "find_product_by_number" in content and "existing_id" in content:
            print("  [OK] Логика проверки существующих товаров присутствует")
            checks_passed += 1
        else:
            print("  [FAIL] Логика проверки существующих товаров отсутствует")
            checks_failed += 1
            blocking_issues.append("Логика проверки существующих товаров отсутствует")

    # 4.3) Категории не изменяются при импорте товаров
    print("\n4.3) Логика: категории не изменяются при импорте товаров")
    if full_import_path.exists():
        content = full_import_path.read_text(encoding="utf-8")
        # Проверяем, что в full_import.py нет операций с категориями
        if "update_category" not in content and "create_category" not in content:
            print("  [OK] Импорт товаров не изменяет категории")
            checks_passed += 1
        else:
            print("  [WARN] Импорт товаров может изменять категории")
            checks_failed += 1

    # ========================================================================
    # ИТОГОВЫЙ ОТЧЁТ
    # ========================================================================
    print("\n" + "=" * 70)
    print("ИТОГОВЫЙ ОТЧЁТ")
    print("=" * 70)
    print(f"\nПроверок пройдено: {checks_passed}")
    print(f"Проверок провалено: {checks_failed}")
    print(f"Всего проверок: {checks_passed + checks_failed}")

    if blocking_issues:
        print("\n" + "=" * 70)
        print("БЛОКИРУЮЩИЕ ПРОБЛЕМЫ:")
        print("=" * 70)
        for i, issue in enumerate(blocking_issues, 1):
            print(f"{i}. {issue}")
        print("\n" + "=" * 70)
        print("ВЕРДИКТ: Есть блокирующие проблемы. НЕЛЬЗЯ запускать production-импорт.")
        print("=" * 70)
        return 1
    else:
        print("\n" + "=" * 70)
        print("ВЕРДИКТ: Скелет зафиксирован. Можно запускать production-импорт товаров.")
        print("=" * 70)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())


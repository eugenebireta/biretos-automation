from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from clients import ShopwareClient, ShopwareConfig


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"

# Гарантируем UTF-8 вывод даже в консоли Windows
if hasattr(sys.stdout, "reconfigure"):  # Python 3.7+
    sys.stdout.reconfigure(encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handler:
        return json.load(handler)


def build_shopware_client(cfg: Dict[str, Any]) -> ShopwareClient:
    shopware_cfg = ShopwareConfig(
        url=cfg["shopware"]["url"],
        access_key_id=cfg["shopware"]["access_key_id"],
        secret_access_key=cfg["shopware"]["secret_access_key"],
    )
    return ShopwareClient(shopware_cfg)


def get_seo_urls_for_category(
    client: ShopwareClient,
    category_id: str,
    sales_channel_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Получает все SEO URLs для категории."""
    try:
        return client.search_seo_urls(
            foreign_key=category_id,
            route_name="frontend.navigation.page",
        )
    except Exception as e:
        print(f"[WARN] Failed to get SEO URLs for category {category_id}: {e}")
        return []


def delete_seo_url(client: ShopwareClient, seo_url_id: str) -> bool:
    """Удаляет SEO URL по ID."""
    return client.delete_seo_url(seo_url_id)


def regenerate_category_seo_urls(
    client: ShopwareClient,
    category_id: str,
) -> bool:
    """Регенерирует SEO URLs для категории через Shopware API."""
    try:
        # Используем _action для регенерации SEO URLs
        response = client._request(
            "POST",
            "/api/_action/seo-url-template/validate",
            json={
                "entityName": "category",
                "salesChannelId": None,  # Для всех Sales Channels
            },
        )
        # Затем обновляем категорию, чтобы триггернуть регенерацию
        client.update_category(category_id, {})
        return True
    except Exception as e:
        print(f"[WARN] Failed to regenerate SEO URLs for category {category_id}: {e}")
        return False


def fix_category_seo_conflicts(
    client: ShopwareClient,
    category_id: str,
    category_title: str,
) -> bool:
    """
    Исправляет конфликты SEO URL для категории.
    Стратегия: удаляем все неканонические SEO URLs, затем регенерируем.
    """
    print(f"\n[INFO] Исправление SEO URL для категории: {category_title} ({category_id})")
    
    # Получаем все SEO URLs для категории
    seo_urls = get_seo_urls_for_category(client, category_id)
    
    if not seo_urls:
        print(f"[INFO] SEO URLs не найдены для категории {category_id}")
        return True
    
    print(f"[INFO] Найдено SEO URLs: {len(seo_urls)}")
    
    # Удаляем все неканонические SEO URLs
    deleted_count = 0
    for seo_url in seo_urls:
        seo_url_id = seo_url.get("id")
        is_canonical = seo_url.get("isCanonical", False)
        
        if not is_canonical and seo_url_id:
            if delete_seo_url(client, seo_url_id):
                deleted_count += 1
                print(f"[OK] Удален неканонический SEO URL: {seo_url.get('seoPathInfo', 'N/A')}")
    
    # Если есть канонические, оставляем только один
    canonical_urls = [url for url in seo_urls if url.get("isCanonical", False)]
    if len(canonical_urls) > 1:
        # Оставляем первый, удаляем остальные
        for canonical_url in canonical_urls[1:]:
            seo_url_id = canonical_url.get("id")
            if seo_url_id and delete_seo_url(client, seo_url_id):
                deleted_count += 1
                print(f"[OK] Удален дублирующий канонический SEO URL: {canonical_url.get('seoPathInfo', 'N/A')}")
    
    # Регенерируем SEO URLs через обновление категории
    print(f"[INFO] Регенерация SEO URLs...")
    try:
        # Просто обновляем категорию без изменений - это триггернет регенерацию SEO
        client.update_category(category_id, {})
        print(f"[OK] SEO URLs регенерированы для категории {category_title}")
        return True
    except Exception as e:
        print(f"[ERROR] Не удалось регенерировать SEO URLs: {e}")
        # Пробуем альтернативный способ - обновить с минимальными данными
        try:
            category = client.get_category(category_id)
            if category:
                # Обновляем только name, чтобы триггернуть регенерацию
                client.update_category(category_id, {"name": category.get("name", category_title)})
                print(f"[OK] SEO URLs регенерированы (альтернативный способ)")
                return True
        except Exception as e2:
            print(f"[ERROR] Альтернативный способ также не сработал: {e2}")
            return False


def reparent_category(
    client: ShopwareClient,
    category_id: str,
    new_parent_id: str,
    category_title: str,
) -> bool:
    """Перемещает категорию под нового родителя."""
    try:
        client.update_category(category_id, {"parentId": new_parent_id})
        print(f"[OK] Категория '{category_title}' перемещена под ROOT_NAV")
        return True
    except Exception as e:
        print(f"[ERROR] Не удалось переместить категорию '{category_title}': {e}")
        return False


def update_sales_channel_navigation(
    client: ShopwareClient,
    sales_channel_id: str,
    root_nav_id: str,
) -> bool:
    """Обновляет navigationCategoryId для Sales Channel."""
    try:
        # Обновляем только navigationCategoryId
        update_payload = {
            "navigationCategoryId": root_nav_id,
        }
        
        client.update_sales_channel(sales_channel_id, update_payload)
        print(f"[OK] Sales Channel {sales_channel_id} обновлен: navigationCategoryId = {root_nav_id}")
        return True
    except Exception as e:
        print(f"[ERROR] Не удалось обновить Sales Channel: {e}")
        return False


def get_main_sales_channel(client: ShopwareClient) -> Optional[str]:
    """Получает ID основного Sales Channel (Storefront)."""
    try:
        response = client._request("GET", "/api/sales-channel")
        if isinstance(response, dict) and "data" in response:
            sales_channels = response["data"]
            # Ищем Storefront Sales Channel
            for sc in sales_channels:
                # Обычно Storefront имеет определенный typeId, но можем взять первый активный
                if sc.get("active", False):
                    return sc.get("id")
            # Если не нашли активный, берем первый
            if sales_channels:
                return sales_channels[0].get("id")
        return None
    except Exception as e:
        print(f"[ERROR] Не удалось получить Sales Channels: {e}")
        return None


def verify_navigation_structure(
    client: ShopwareClient,
    root_nav_id: str,
) -> Dict[str, Any]:
    """Проверяет структуру навигации."""
    result = {
        "root_categories": [],
        "has_catalog": False,
        "errors": [],
    }
    
    try:
        # Получаем ROOT_NAV категорию
        root_nav = client.get_category(root_nav_id)
        if not root_nav:
            result["errors"].append(f"ROOT_NAV категория {root_nav_id} не найдена")
            return result
        
        # Получаем детей ROOT_NAV
        response = client._request(
            "POST",
            "/api/search/category",
            json={
                "filter": [
                    {"field": "parentId", "type": "equals", "value": root_nav_id},
                ],
                "limit": 100,
                "includes": {"category": ["id", "name", "active", "visible"]},
            },
        )
        
        if isinstance(response, dict) and "data" in response:
            children = response["data"]
            for cat in children:
                # Shopware может возвращать name в разных местах
                name = cat.get("name") or cat.get("translated", {}).get("name") or ""
                if not name and "attributes" in cat:
                    name = cat["attributes"].get("name", "")
                
                cat_data = {
                    "id": cat.get("id"),
                    "name": name,
                    "active": cat.get("active", False) or cat.get("attributes", {}).get("active", False),
                    "visible": cat.get("visible", False) or cat.get("attributes", {}).get("visible", False),
                }
                result["root_categories"].append(cat_data)
                
                # Проверяем, есть ли категория "Каталог"
                if cat_data["name"].strip() == "Каталог":
                    result["has_catalog"] = True
        
        return result
    except Exception as e:
        result["errors"].append(f"Ошибка при проверке структуры: {e}")
        return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Исправление SEO URL конфликтов и финальная настройка категорий Shopware."
    )
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument(
        "--skip-seo-fix",
        action="store_true",
        help="Пропустить исправление SEO URL (если уже исправлено)",
    )
    parser.add_argument(
        "--skip-sales-channel",
        action="store_true",
        help="Пропустить обновление Sales Channel",
    )
    args = parser.parse_args()
    
    config = load_json(args.config)
    root_nav_id = config["shopware"].get("root_nav_id")
    if not root_nav_id:
        print("[ERROR] root_nav_id не указан в config.json")
        return 1
    
    client = build_shopware_client(config)
    
    # Проблемные категории
    problem_categories = [
        {
            "id": "bc7f65bd98df43eb868c4eb3074fde9f",
            "title": "VK ♥ 21 марта, Челябинск♥",
        },
        {
            "id": "e3185f9ae8a34e198d71ed871bd1bd2f",
            "title": "VK ЯРИТЬ ХУ 2.0",
        },
    ]
    
    print("=== Исправление SEO URL конфликтов и финальная настройка ===\n")
    
    # Шаг 1: Исправление SEO URL
    if not args.skip_seo_fix:
        print("--- Шаг 1: Исправление SEO URL конфликтов ---")
        for cat_info in problem_categories:
            fix_category_seo_conflicts(client, cat_info["id"], cat_info["title"])
    else:
        print("[INFO] Пропущено исправление SEO URL (--skip-seo-fix)")
    
    # Шаг 2: Репарентинг категорий
    print("\n--- Шаг 2: Перемещение категорий под ROOT_NAV ---")
    moved_count = 0
    for cat_info in problem_categories:
        if reparent_category(client, cat_info["id"], root_nav_id, cat_info["title"]):
            moved_count += 1
    
    # Шаг 3: Обновление Sales Channel
    if not args.skip_sales_channel:
        print("\n--- Шаг 3: Обновление Sales Channel ---")
        sales_channel_id = get_main_sales_channel(client)
        if sales_channel_id:
            update_sales_channel_navigation(client, sales_channel_id, root_nav_id)
        else:
            print("[WARN] Не удалось найти Sales Channel для обновления")
    else:
        print("[INFO] Пропущено обновление Sales Channel (--skip-sales-channel)")
    
    # Шаг 4: Проверка результата
    print("\n--- Шаг 4: Проверка структуры навигации ---")
    verification = verify_navigation_structure(client, root_nav_id)
    
    # Вывод итогов
    print("\n=== Итоги ===")
    print(f"Категорий перемещено: {moved_count}/{len(problem_categories)}")
    print(f"Категорий в корне навигации: {len(verification['root_categories'])}")
    
    if verification["has_catalog"]:
        print("[WARN] В корне навигации найдена категория 'Каталог'")
    else:
        print("[OK] Категория 'Каталог' отсутствует в корне навигации")
    
    if verification["errors"]:
        print(f"[ERROR] Ошибки при проверке: {len(verification['errors'])}")
        for error in verification["errors"]:
            print(f"  - {error}")
    else:
        print("[OK] Ошибок при проверке не обнаружено")
    
    # Список верхнеуровневых категорий
    print("\nВерхнеуровневые категории в меню:")
    if verification["root_categories"]:
        # Сортируем по имени
        sorted_cats = sorted(verification["root_categories"], key=lambda x: x.get("name", ""))
        for cat in sorted_cats:
            name = cat.get("name", "Unknown")
            active = cat.get("active", False)
            visible = cat.get("visible", False)
            status = []
            if not active:
                status.append("inactive")
            if not visible:
                status.append("hidden")
            status_str = f" ({', '.join(status)})" if status else ""
            print(f"  - {name}{status_str}")
    else:
        print("  (нет категорий)")
    
    # Финальный статус
    print("\n=== Статус готовности ===")
    if moved_count == len(problem_categories) and not verification["errors"] and not verification["has_catalog"]:
        print("[OK] Каталог готов к импорту товаров")
        print("  - Все категории перемещены под ROOT_NAV")
        print("  - Категория 'Каталог' отсутствует в меню")
        print("  - Структура навигации корректна")
    else:
        print("[WARN] Требуется дополнительная проверка")
        if moved_count < len(problem_categories):
            print(f"  - Не все категории перемещены ({moved_count}/{len(problem_categories)})")
        if verification["has_catalog"]:
            print("  - Категория 'Каталог' присутствует в меню")
        if verification["errors"]:
            print(f"  - Обнаружены ошибки: {len(verification['errors'])}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


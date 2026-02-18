"""
Исправление entry point для Sales Channel.

ВАЖНО: ROOT_NAV - техническая категория навигации.
Она НЕ должна быть entry point (homepage).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from clients import ShopwareClient, ShopwareConfig


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
ROOT_NAV_ID = "019b141f60007eefa571a533ddc98797"
ROOT_CATEGORY_ID = "01994d23acb670fa926de3796d173b74"


def load_json(path: Path) -> Dict[str, Any]:
    """Загружает JSON файл."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_sales_channels(client: ShopwareClient) -> list[Dict[str, Any]]:
    """Получает список всех Sales Channels."""
    response = client._request("GET", "/api/sales-channel")
    if isinstance(response, dict) and "data" in response:
        return response["data"]
    return []


def get_category(client: ShopwareClient, category_id: str) -> Optional[Dict[str, Any]]:
    """Получает категорию по ID."""
    try:
        response = client._request("GET", f"/api/category/{category_id}")
        if isinstance(response, dict) and "data" in response:
            return response["data"]
        return response
    except Exception:
        return None


def find_home_category(client: ShopwareClient) -> Optional[str]:
    """
    Ищет категорию "Home" или другую активную категорию для entry point.
    
    Возвращает ID категории, которая может быть использована как homepage.
    """
    # Сначала ищем категорию с именем "Home"
    try:
        response = client._request(
            "POST",
            "/api/search/category",
            json={
                "filter": [
                    {"field": "name", "type": "equals", "value": "Home"},
                    {"field": "active", "type": "equals", "value": True},
                ],
                "limit": 1,
                "includes": {"category": ["id", "name", "active", "visible"]},
            },
        )
        
        if isinstance(response, dict) and response.get("total", 0) > 0:
            category = response["data"][0]
            print(f"Найдена категория 'Home': {category.get('name')} ({category.get('id')})")
            return category.get("id")
    except Exception as e:
        print(f"[WARN] Ошибка при поиске 'Home': {e}")
    
    # Если "Home" не найдена, ищем любую активную категорию верхнего уровня
    # (не ROOT_NAV и не root_category)
    try:
        response = client._request(
            "POST",
            "/api/search/category",
            json={
                "filter": [
                    {"field": "active", "type": "equals", "value": True},
                    {"field": "parentId", "type": "equals", "value": ROOT_NAV_ID},
                ],
                "limit": 10,
                "includes": {"category": ["id", "name", "active", "visible"]},
            },
        )
        
        if isinstance(response, dict) and response.get("total", 0) > 0:
            categories = response["data"]
            print(f"\nНайдено {len(categories)} активных категорий под ROOT_NAV:")
            for cat in categories:
                print(f"  - {cat.get('name')} ({cat.get('id')})")
            
            # Берем первую активную категорию
            category = categories[0]
            return category.get("id")
    except Exception as e:
        print(f"[WARN] Ошибка при поиске категорий под ROOT_NAV: {e}")
    
    # Если ничего не найдено, используем root_category_id как fallback
    print(f"[WARN] Используем root_category_id как fallback: {ROOT_CATEGORY_ID}")
    return ROOT_CATEGORY_ID


def ensure_named_category(
    client: ShopwareClient,
    *,
    name: str,
    parent_id: str = ROOT_NAV_ID,
    visible: bool = False,
) -> Optional[str]:
    """Ищет или создает категорию по имени."""
    try:
        response = client._request(
            "POST",
            "/api/search/category",
            json={
                "filter": [
                    {"field": "name", "type": "equals", "value": name},
                ],
                "limit": 1,
                "includes": {"category": ["id", "name", "active", "visible"]},
            },
        )
        if isinstance(response, dict) and response.get("total", 0) > 0:
            category = response["data"][0]
            if not category.get("active"):
                # активируем категорию
                client._request(
                    "PATCH",
                    f"/api/category/{category['id']}",
                    json={"active": True, "visible": visible},
                )
            return category.get("id")
    except Exception as e:
        print(f"[WARN] Ошибка при поиске категории '{name}': {e}")
    
    new_id = uuid4().hex
    payload = {
        "id": new_id,
        "name": name,
        "parentId": parent_id,
        "active": True,
        "visible": visible,
    }
    try:
        client._request("POST", "/api/category", json=payload)
        print(f"[OK] Создана категория '{name}' ({new_id})")
        return new_id
    except Exception as e:
        print(f"[ERROR] Не удалось создать категорию '{name}': {e}")
        return None


def find_home_cms_page(client: ShopwareClient) -> Optional[str]:
    """
    Ищет CMS страницу, подходящую для домашней страницы.
    Приоритет: страницы типа landingpage или с названием, содержащим 'home'.
    """
    try:
        response = client._request(
            "POST",
            "/api/search/cms-page",
            json={
                "filter": [
                    {"field": "type", "type": "equals", "value": "landingpage"},
                ],
                "limit": 10,
                "includes": {"cms_page": ["id", "name", "type"]},
            },
        )
        if isinstance(response, dict) and response.get("total", 0) > 0:
            page = response["data"][0]
            print(f"Найдена CMS страница типа landingpage: {page.get('name')} ({page.get('id')})")
            return page.get("id")
    except Exception as e:
        print(f"[WARN] Ошибка при поиске CMS страницы (landingpage): {e}")
    
    try:
        response = client._request(
            "POST",
            "/api/search/cms-page",
            json={
                "filter": [
                    {"field": "name", "type": "contains", "value": "home"},
                ],
                "limit": 10,
                "includes": {"cms_page": ["id", "name", "type"]},
            },
        )
        if isinstance(response, dict) and response.get("total", 0) > 0:
            page = response["data"][0]
            print(f"Найдена CMS страница по названию: {page.get('name')} ({page.get('id')})")
            return page.get("id")
    except Exception as e:
        print(f"[WARN] Ошибка при поиске CMS страницы (name contains home): {e}")
    
    return None


def create_home_cms_page(client: ShopwareClient) -> Optional[str]:
    """Создает простую CMS страницу для главной страницы."""
    new_id = uuid4().hex
    payload = {
        "id": new_id,
        "name": "Auto Home Page",
        "type": "landingpage",
        "sections": [
            {
                "type": "default",
                "position": 0,
                "sizingMode": "boxed",
                "blocks": [
                    {
                        "type": "text",
                        "position": 0,
                        "slots": [
                            {
                                "slot": "content",
                                "type": "text",
                                "config": {
                                    "content": {
                                        "source": "static",
                                        "value": "<h2>Добро пожаловать</h2><p>Эта страница создана автоматически.</p>",
                                    }
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    }
    try:
        client._request("POST", "/api/cms-page", json=payload)
        print(f"[OK] Создана CMS страница 'Auto Home Page' ({new_id})")
        return new_id
    except Exception as e:
        print(f"[ERROR] Не удалось создать CMS страницу: {e}")
        return None


def clear_cache(client: ShopwareClient) -> bool:
    """Очищает кеш Shopware."""
    try:
        client._request("DELETE", "/api/_action/cache")
        return True
    except Exception as e:
        print(f"[WARN] Не удалось очистить кеш: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Исправление entry point для Sales Channel."
    )
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--dry-run", action="store_true", help="Режим проверки без изменений")
    args = parser.parse_args()

    config = load_json(args.config)
    shopware_config = ShopwareConfig(
        url=config["shopware"]["url"],
        access_key_id=config["shopware"]["access_key_id"],
        secret_access_key=config["shopware"]["secret_access_key"],
    )
    client = ShopwareClient(shopware_config)

    print("=" * 60)
    print("ИСПРАВЛЕНИЕ ENTRY POINT ДЛЯ SALES CHANNEL")
    print("=" * 60)
    print(f"\nROOT_NAV_ID: {ROOT_NAV_ID}")

    # 1) Получаем текущую конфигурацию Sales Channel
    print("\n=== Шаг 1: Получение конфигурации Sales Channel ===")
    sales_channels = get_sales_channels(client)
    
    if not sales_channels:
        print("[ERROR] Sales Channels не найдены")
        return 1
    
    # Берем первый Sales Channel (обычно основной)
    sales_channel = sales_channels[0]
    sales_channel_id = sales_channel.get("id")
    sales_channel_name = sales_channel.get("name", "Unknown")
    
    print(f"Sales Channel: {sales_channel_name} ({sales_channel_id})")
    
    # Получаем полную информацию о Sales Channel
    sc_full = client._request("GET", f"/api/sales-channel/{sales_channel_id}")
    if isinstance(sc_full, dict) and "data" in sc_full:
        sales_channel_data = sc_full["data"]
    else:
        sales_channel_data = sc_full
    
    # Извлекаем данные из attributes (Shopware API возвращает данные в attributes)
    attributes = sales_channel_data.get("attributes", {})
    
    current_nav_id = attributes.get("navigationCategoryId")
    current_home_cms = attributes.get("homeCmsPageId")
    current_home_enabled = attributes.get("homeEnabled", True)
    current_footer_id = attributes.get("footerCategoryId")
    current_service_id = attributes.get("serviceCategoryId")
    
    print(f"Текущий navigationCategoryId: {current_nav_id}")
    print(f"Текущий homeCmsPageId: {current_home_cms}")
    print(f"homeEnabled: {current_home_enabled}")
    print(f"footerCategoryId: {current_footer_id}")
    print(f"serviceCategoryId: {current_service_id}")
    
    # 2) Проверяем ROOT_NAV
    print("\n=== Шаг 2: Проверка ROOT_NAV ===")
    root_nav = get_category(client, ROOT_NAV_ID)
    if not root_nav:
        print(f"[ERROR] ROOT_NAV ({ROOT_NAV_ID}) не найдена!")
        return 1
    
    root_nav_active = root_nav.get("active", False)
    root_nav_visible = root_nav.get("visible", False)
    root_nav_name = root_nav.get("name", "Unknown")
    
    print(f"ROOT_NAV: {root_nav_name}")
    print(f"  active: {root_nav_active}")
    print(f"  visible: {root_nav_visible}")
    
    if root_nav_active or root_nav_visible:
        print("[WARN] ROOT_NAV должна быть inactive и invisible!")
    
    # 3) Проверяем проблему
    print("\n=== Шаг 3: Анализ проблемы ===")
    if current_nav_id == ROOT_NAV_ID:
        print(f"[OK] navigationCategoryId указывает на ROOT_NAV ({ROOT_NAV_ID}) - правильно")
    else:
        print(f"[WARN] navigationCategoryId не указывает на ROOT_NAV")
    
    if not current_home_cms and current_home_enabled:
        print(f"[ПРОБЛЕМА] homeCmsPageId = None, но homeEnabled = True")
        print("Shopware пытается использовать navigationCategoryId как entry point")
        print("Это вызывает ошибку, т.к. ROOT_NAV - техническая категория")
    
    # 4) Решение: находим/создаем CMS страницу для entry point
    print("\n=== Шаг 4: Поиск CMS страницы для entry point ===")
    home_cms_page_id = find_home_cms_page(client)
    
    if not home_cms_page_id:
        if args.dry_run:
            print("[DRY-RUN] CMS страница не найдена. Будет создана 'Auto Home Page'.")
        else:
            print("[INFO] CMS страница не найдена. Создаем 'Auto Home Page'.")
            home_cms_page_id = create_home_cms_page(client)
    
    if not home_cms_page_id:
        print("[ERROR] Не удалось получить или создать CMS страницу для entry point.")
        return 1
    
    print(f"Будет использована CMS страница: {home_cms_page_id}")
    
    update_payload: Dict[str, Any] = {}
    
    if current_home_cms != home_cms_page_id or not current_home_enabled:
        update_payload["homeEnabled"] = True
        update_payload["homeCmsPageId"] = home_cms_page_id
    
    # Footer category
    footer_target_id = current_footer_id
    if not current_footer_id or current_footer_id == ROOT_NAV_ID:
        print("\n=== Шаг 5: Настройка footerCategory ===")
        if args.dry_run:
            print("[DRY-RUN] footerCategoryId будет установлен на категорию 'Footer'")
            footer_target_id = "<Footer-Category-ID>"
        else:
            footer_target_id = ensure_named_category(client, name="Footer", visible=False)
            if not footer_target_id:
                print("[ERROR] Не удалось получить categoryId для Footer")
                return 1
            update_payload["footerCategoryId"] = footer_target_id
    else:
        print("\n[OK] footerCategoryId уже задан корректно")
    
    # Service category
    service_target_id = current_service_id
    if not current_service_id or current_service_id == ROOT_NAV_ID:
        print("\n=== Шаг 6: Настройка serviceCategory ===")
        if args.dry_run:
            print("[DRY-RUN] serviceCategoryId будет установлен на категорию 'Service'")
            service_target_id = "<Service-Category-ID>"
        else:
            service_target_id = ensure_named_category(client, name="Service", visible=False)
            if not service_target_id:
                print("[ERROR] Не удалось получить categoryId для Service")
                return 1
            update_payload["serviceCategoryId"] = service_target_id
    else:
        print("\n[OK] serviceCategoryId уже задан корректно")
    
    if args.dry_run:
        print("\n[DRY-RUN] Будет установлено:")
        print(f"  navigationCategoryId: {ROOT_NAV_ID} (без изменений)")
        if "homeCmsPageId" in update_payload:
            print(f"  homeEnabled: True")
            print(f"  homeCmsPageId: {home_cms_page_id}")
        print(f"  footerCategoryId: {footer_target_id}")
        print(f"  serviceCategoryId: {service_target_id}")
        print("\n[DRY-RUN] Изменения НЕ применены")
        return 0
    
    if update_payload:
        try:
            client.update_sales_channel(sales_channel_id, update_payload)
            print(f"[OK] Sales Channel обновлен:")
            if "homeCmsPageId" in update_payload:
                print(f"  homeEnabled: True")
                print(f"  homeCmsPageId: {home_cms_page_id}")
            if "footerCategoryId" in update_payload:
                print(f"  footerCategoryId: {footer_target_id}")
            if "serviceCategoryId" in update_payload:
                print(f"  serviceCategoryId: {service_target_id}")
        except Exception as e:
            print(f"[ERROR] Не удалось обновить Sales Channel: {e}")
            return 1
    else:
        print("[OK] Конфигурация уже соответствует требованиям")
    
    # Очищаем кеш
    print("\n=== Шаг 7: Очистка кеша ===")
    if clear_cache(client):
        print("[OK] Кеш очищен")
    else:
        print("[WARN] Кеш не очищен (может потребоваться ручная очистка)")
    
    # 7) Финальная проверка
    print("\n=== Шаг 8: Финальная проверка ===")
    sc_final = client._request("GET", f"/api/sales-channel/{sales_channel_id}")
    if isinstance(sc_final, dict) and "data" in sc_final:
        sc_final_data = sc_final["data"]
    else:
        sc_final_data = sc_final
    
    final_attrs = sc_final_data.get("attributes", {})
    final_nav_id = final_attrs.get("navigationCategoryId")
    final_home_enabled = final_attrs.get("homeEnabled")
    final_home_cms = final_attrs.get("homeCmsPageId")
    final_footer_id = final_attrs.get("footerCategoryId")
    final_service_id = final_attrs.get("serviceCategoryId")
    
    print("\n" + "=" * 60)
    print("ИТОГОВАЯ КОНФИГУРАЦИЯ")
    print("=" * 60)
    print(f"navigationCategoryId: {final_nav_id}")
    print(f"homeEnabled: {final_home_enabled}")
    print(f"homeCmsPageId: {final_home_cms}")
    print(f"footerCategoryId: {final_footer_id}")
    print(f"serviceCategoryId: {final_service_id}")
    print(f"\nROOT_NAV статус:")
    print(f"  active: {root_nav_active}")
    print(f"  visible: {root_nav_visible}")
    
    if (
        final_nav_id == ROOT_NAV_ID
        and final_home_enabled
        and final_home_cms
        and final_footer_id
        and final_service_id
        and final_footer_id != ROOT_NAV_ID
        and final_service_id != ROOT_NAV_ID
    ):
        print("\n[OK] Конфигурация исправлена корректно!")
        print("ROOT_NAV используется только для навигации")
        print("homeEnabled включен, используется CMS страница для entry point")
        print("\nСайт должен открываться без ошибки 'Category not found'")
    else:
        print("\n[WARN] Проверьте конфигурацию вручную")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


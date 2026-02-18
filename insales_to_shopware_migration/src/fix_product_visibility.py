"""
Исправление product_visibility для отображения товаров в leaf-категориях Shopware 6.

Проблема: Товары привязаны к leaf-категориям, но не отображаются на storefront.

Решение: Создать/обновить product_visibility для storefront sales channel
с categoryId = leaf категория и visibility = 30.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from category_utils import get_category_chain, is_leaf_category


def load_config() -> ShopwareConfig:
    """Загружает конфигурацию Shopware."""
    config_path = Path(__file__).parent.parent / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Конфигурация не найдена: {config_path}")
    
    with config_path.open(encoding="utf-8") as f:
        config = json.load(f)
    
    sw = config["shopware"]
    return ShopwareConfig(
        url=sw["url"],
        access_key_id=sw["access_key_id"],
        secret_access_key=sw["secret_access_key"],
    )


def get_all_products(client: ShopwareClient, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Получает все товары из Shopware."""
    all_products = []
    page = 1
    per_page = 100
    
    while True:
        try:
            response = client._request(
                "POST",
                "/api/search/product",
                json={
                    "limit": per_page,
                    "page": page,
                    "includes": {
                        "product": [
                            "id",
                            "productNumber",
                            "name",
                            "categories",
                        ],
                    },
                },
            )
            
            if isinstance(response, dict) and "data" in response:
                data = response.get("data", [])
                if not data:
                    break
                
                all_products.extend(data)
                
                if limit and len(all_products) >= limit:
                    all_products = all_products[:limit]
                    break
                
                if len(data) < per_page:
                    break
                
                page += 1
            else:
                break
        except Exception as e:
            print(f"[ERROR] Ошибка при получении товаров: {e}")
            break
    
    return all_products


def find_leaf_category(client: ShopwareClient, product_id: str) -> Optional[str]:
    """
    Находит leaf-категорию (самую глубокую) для товара.
    
    Args:
        client: ShopwareClient
        product_id: ID товара
        
    Returns:
        ID leaf-категории или None
    """
    try:
        # Используем Search API с includes для получения категорий
        product_response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [
                    {"field": "id", "type": "equals", "value": product_id},
                ],
                "limit": 1,
                "includes": {
                    "product": ["id", "categories"],
                },
            },
        )
        
        category_ids = []
        
        if isinstance(product_response, dict) and "data" in product_response:
            data = product_response.get("data", [])
            if data:
                product_data = data[0]
                relationships = product_data.get("relationships", {})
                categories_rel = relationships.get("categories", {})
                
                if categories_rel:
                    # Получаем IDs из relationships
                    category_ids = [c.get("id") for c in categories_rel.get("data", []) if c.get("id")]
        
        # Если не нашли через relationships, пробуем через included
        if not category_ids and isinstance(product_response, dict):
            included = product_response.get("included", [])
            for item in included:
                if item.get("type") == "category":
                    cat_id = item.get("id")
                    if cat_id:
                        category_ids.append(cat_id)
        
        # Альтернативный способ: прямой GET запрос
        if not category_ids:
            try:
                product_response = client._request(
                    "GET",
                    f"/api/product/{product_id}",
                    params={
                        "associations[categories]": "{}",
                    },
                )
                
                if isinstance(product_response, dict) and "data" in product_response:
                    product_data = product_response["data"]
                    relationships = product_data.get("relationships", {})
                    categories_rel = relationships.get("categories", {})
                    
                    if categories_rel:
                        category_ids = [c.get("id") for c in categories_rel.get("data", []) if c.get("id")]
                    
                    if not category_ids:
                        included = product_response.get("included", [])
                        for item in included:
                            if item.get("type") == "category":
                                cat_id = item.get("id")
                                if cat_id:
                                    category_ids.append(cat_id)
            except Exception:
                pass
        
        if not category_ids:
            return None
        
        # Ищем leaf-категорию среди категорий товара
        for cat_id in category_ids:
            if is_leaf_category(client, cat_id):
                return cat_id
        
        # Если не нашли leaf, берём последнюю категорию из цепочки
        # (предполагаем, что она самая глубокая)
        if category_ids:
            # Получаем цепочку для последней категории
            chain = get_category_chain(client, category_ids[-1])
            if chain:
                return chain[-1]  # Последняя в цепочке = leaf
        
        return None
    except Exception as e:
        print(f"  [DEBUG] Ошибка поиска leaf категории: {e}")
        return None


def get_product_visibility(
    client: ShopwareClient,
    product_id: str,
    sales_channel_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Получает product_visibility для товара и sales channel.
    
    Returns:
        Данные visibility или None если не найдено
    """
    try:
        # Используем прямой GET запрос к товару с associations
        product_response = client._request(
            "GET",
            f"/api/product/{product_id}",
            params={
                "associations[visibilities]": "{}",
            },
        )
        
        if isinstance(product_response, dict) and "data" in product_response:
            product_data = product_response["data"]
            relationships = product_data.get("relationships", {})
            visibilities_rel = relationships.get("visibilities", {})
            
            if visibilities_rel:
                # Получаем IDs из relationships
                visibility_ids = [v.get("id") for v in visibilities_rel.get("data", []) if v.get("id")]
                
                # Получаем данные visibility из included или делаем отдельный запрос
                included = product_response.get("included", [])
                for item in included:
                    if item.get("type") == "product_visibility" and item.get("id") in visibility_ids:
                        vis_data = item.get("attributes", {})
                        vis_sales_channel_id = vis_data.get("salesChannelId")
                        if vis_sales_channel_id == sales_channel_id:
                            return {
                                "id": item.get("id"),
                                "productId": vis_data.get("productId"),
                                "salesChannelId": vis_sales_channel_id,
                                "categoryId": vis_data.get("categoryId"),
                                "visibility": vis_data.get("visibility"),
                            }
        
        # Альтернативный способ: через Search API
        response = client._request(
            "POST",
            "/api/search/product-visibility",
            json={
                "filter": [
                    {"field": "productId", "type": "equals", "value": product_id},
                    {"field": "salesChannelId", "type": "equals", "value": sales_channel_id},
                ],
                "limit": 1,
            },
        )
        
        if isinstance(response, dict) and "data" in response:
            data = response.get("data", [])
            if data:
                vis_data = data[0]
                # Если данные в attributes
                if "attributes" in vis_data:
                    attrs = vis_data["attributes"]
                    return {
                        "id": vis_data.get("id"),
                        "productId": attrs.get("productId"),
                        "salesChannelId": attrs.get("salesChannelId"),
                        "categoryId": attrs.get("categoryId"),
                        "visibility": attrs.get("visibility"),
                    }
                # Если данные напрямую
                return {
                    "id": vis_data.get("id"),
                    "productId": vis_data.get("productId"),
                    "salesChannelId": vis_data.get("salesChannelId"),
                    "categoryId": vis_data.get("categoryId"),
                    "visibility": vis_data.get("visibility"),
                }
        return None
    except Exception as e:
        print(f"  [DEBUG] Ошибка получения visibility: {e}")
        return None


def create_or_update_visibility(
    client: ShopwareClient,
    product_id: str,
    sales_channel_id: str,
    category_id: str,
    existing_visibility_id: Optional[str] = None,
    dry_run: bool = False,
) -> bool:
    """
    Создаёт или обновляет product_visibility.
    
    Args:
        client: ShopwareClient
        product_id: ID товара
        sales_channel_id: ID sales channel
        category_id: ID категории (leaf)
        existing_visibility_id: ID существующей visibility (если обновляем)
        dry_run: Если True, только проверка без изменений
        
    Returns:
        True если успешно, False если ошибка
    """
    payload: Dict[str, Any] = {
        "productId": product_id,
        "salesChannelId": sales_channel_id,
        "categoryId": category_id,
        "visibility": 30,  # 30 = all (visible everywhere)
    }
    
    if existing_visibility_id:
        # Обновляем существующую visibility
        payload["id"] = existing_visibility_id
        if dry_run:
            print(f"  [DRY-RUN] Обновление visibility {existing_visibility_id}: categoryId={category_id}")
            return True
        try:
            client._request("PATCH", f"/api/product-visibility/{existing_visibility_id}", json=payload)
            return True
        except Exception as e:
            print(f"  [ERROR] Ошибка обновления visibility: {e}")
            return False
    else:
        # Создаём новую visibility
        visibility_id = uuid4().hex
        payload["id"] = visibility_id
        if dry_run:
            print(f"  [DRY-RUN] Создание visibility {visibility_id}: categoryId={category_id}")
            return True
        try:
            client._request("POST", "/api/product-visibility", json=payload)
            return True
        except Exception as e:
            print(f"  [ERROR] Ошибка создания visibility: {e}")
            return False


def fix_product_visibility(
    client: ShopwareClient,
    product_id: str,
    product_number: str,
    product_name: str,
    storefront_sales_channel_id: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Исправляет product_visibility для товара.
    
    Returns:
        Словарь с результатами:
        {
            "product_id": str,
            "product_number": str,
            "product_name": str,
            "leaf_category_id": Optional[str],
            "action": str,  # "created", "updated", "skipped", "error"
            "existing_visibility_id": Optional[str],
            "error": Optional[str],
        }
    """
    result = {
        "product_id": product_id,
        "product_number": product_number,
        "product_name": product_name,
        "leaf_category_id": None,
        "action": "skipped",
        "existing_visibility_id": None,
        "error": None,
    }
    
    # Находим leaf-категорию
    leaf_category_id = find_leaf_category(client, product_id)
    if not leaf_category_id:
        result["action"] = "skipped"
        result["error"] = "Leaf категория не найдена (товар не привязан к категориям)"
        return result
    
    result["leaf_category_id"] = leaf_category_id
    
    # Получаем текущую visibility
    existing_visibility = get_product_visibility(client, product_id, storefront_sales_channel_id)
    
    # Проверяем, нужно ли исправление
    needs_fix = False
    existing_visibility_id = None
    
    if not existing_visibility:
        # Visibility отсутствует - нужно создать
        needs_fix = True
        result["action"] = "created"
        if not dry_run:
            print(f"  [INFO] Товар {product_number}: visibility отсутствует, будет создана")
    else:
        existing_visibility_id = existing_visibility.get("id")
        existing_category_id = existing_visibility.get("categoryId")
        existing_visibility_value = existing_visibility.get("visibility")
        
        # Проверяем, нужно ли обновление
        if existing_category_id != leaf_category_id:
            needs_fix = True
            result["action"] = "updated"
            result["existing_visibility_id"] = existing_visibility_id
            if not dry_run:
                print(f"  [INFO] Товар {product_number}: categoryId неверный ({existing_category_id} != {leaf_category_id})")
        elif existing_visibility_value != 30:
            needs_fix = True
            result["action"] = "updated"
            result["existing_visibility_id"] = existing_visibility_id
            if not dry_run:
                print(f"  [INFO] Товар {product_number}: visibility неверный ({existing_visibility_value} != 30)")
        else:
            # Всё корректно
            if not dry_run:
                print(f"  [INFO] Товар {product_number}: visibility корректна (categoryId={leaf_category_id}, visibility=30)")
    
    if not needs_fix:
        result["action"] = "skipped"
        return result
    
    # Исправляем visibility
    success = create_or_update_visibility(
        client,
        product_id,
        storefront_sales_channel_id,
        leaf_category_id,
        existing_visibility_id,
        dry_run,
    )
    
    if not success:
        result["action"] = "error"
        result["error"] = "Ошибка при создании/обновлении visibility"
    
    return result


def main():
    """Основная функция исправления product_visibility."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Исправление product_visibility для товаров")
    parser.add_argument("--dry-run", action="store_true", help="Только проверка без изменений")
    parser.add_argument("--limit", type=int, default=None, help="Ограничить количество товаров")
    args = parser.parse_args()
    
    print("=" * 80)
    print("ИСПРАВЛЕНИЕ PRODUCT_VISIBILITY ДЛЯ LEAF-КАТЕГОРИЙ")
    print("=" * 80)
    print()
    
    if args.dry_run:
        print("[INFO] Режим DRY-RUN: изменения не будут применены")
        print()
    
    # Загружаем конфигурацию
    try:
        config = load_config()
        client = ShopwareClient(config)
    except Exception as e:
        print(f"[ERROR] Не удалось загрузить конфигурацию: {e}")
        return
    
    # Получаем storefront sales channel ID
    try:
        storefront_sales_channel_id = client.get_storefront_sales_channel_id()
        print(f"[INFO] Storefront Sales Channel ID: {storefront_sales_channel_id}")
    except Exception as e:
        print(f"[ERROR] Не удалось получить storefront sales channel ID: {e}")
        return
    
    print()
    print("[INFO] Загрузка товаров из Shopware...")
    
    # Получаем все товары
    products = get_all_products(client, limit=args.limit)
    total_products = len(products)
    
    print(f"[INFO] Загружено товаров: {total_products}")
    print()
    
    if total_products == 0:
        print("[WARNING] Товары не найдены")
        return
    
    # Исправляем visibility для каждого товара
    print("[INFO] Проверка и исправление product_visibility...")
    print()
    
    results: List[Dict[str, Any]] = []
    created_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    
    for idx, product in enumerate(products, 1):
        if idx % 50 == 0:
            print(f"[INFO] Обработано товаров: {idx}/{total_products}")
        
        product_id = product.get("id", "")
        product_number = product.get("productNumber", "")
        product_name = product.get("name", "")
        
        result = fix_product_visibility(
            client,
            product_id,
            product_number,
            product_name,
            storefront_sales_channel_id,
            dry_run=args.dry_run,
        )
        
        results.append(result)
        
        if result["action"] == "created":
            created_count += 1
            if not args.dry_run:
                print(f"[{idx}/{total_products}] {result['product_number']}: Создана visibility (categoryId={result['leaf_category_id']})")
        elif result["action"] == "updated":
            updated_count += 1
            if not args.dry_run:
                print(f"[{idx}/{total_products}] {result['product_number']}: Обновлена visibility (categoryId={result['leaf_category_id']})")
        elif result["action"] == "error":
            error_count += 1
            print(f"[{idx}/{total_products}] {result['product_number']}: ОШИБКА - {result.get('error', 'Unknown')}")
        else:
            skipped_count += 1
            # Логируем причину пропуска для первых 5 товаров
            if skipped_count <= 5:
                if result.get("error"):
                    print(f"  [SKIP] {result['product_number']}: {result['error']}")
                else:
                    print(f"  [SKIP] {result['product_number']}: visibility уже корректна")
    
    print()
    print("=" * 80)
    print("РЕЗУЛЬТАТЫ")
    print("=" * 80)
    print()
    
    print(f"Всего товаров проверено: {total_products}")
    print(f"  [CREATED] Создано visibility: {created_count}")
    print(f"  [UPDATED] Обновлено visibility: {updated_count}")
    print(f"  [SKIPPED] Пропущено (уже корректно): {skipped_count}")
    print(f"  [ERROR] Ошибок: {error_count}")
    print()
    
    # Показываем примеры исправлений
    examples = [r for r in results if r["action"] in ("created", "updated")]
    if examples:
        print("Примеры исправлений (первые 10):")
        print()
        for result in examples[:10]:
            action_text = "Создана" if result["action"] == "created" else "Обновлена"
            print(f"  {result['product_number']}: {action_text} visibility")
            print(f"    Товар: {result['product_name']}")
            print(f"    categoryId: {result['leaf_category_id']}")
            if result.get("existing_visibility_id"):
                print(f"    Существующая visibility ID: {result['existing_visibility_id']}")
            print()
    
    # Сохраняем результаты в файл
    output_path = Path(__file__).parent.parent / "diagnostics" / "product_visibility_fix.json"
    output_path.parent.mkdir(exist_ok=True)
    
    summary = {
        "total_products": total_products,
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "dry_run": args.dry_run,
        "examples": [
            {
                "product_number": r["product_number"],
                "product_name": r["product_name"],
                "leaf_category_id": r["leaf_category_id"],
                "action": r["action"],
            }
            for r in examples[:50]
        ],
    }
    
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"[INFO] Результаты сохранены в: {output_path}")
    print()
    print("=" * 80)
    print("ЗАВЕРШЕНО")
    print("=" * 80)


if __name__ == "__main__":
    main()


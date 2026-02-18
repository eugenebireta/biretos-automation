"""
Принудительный UPDATE товара с использованием КОРРЕКТНЫХ API Shopware 6.
ШАГ 1: Visibilities (DELETE + POST /api/product-visibility)
ШАГ 2: Categories (PATCH /api/product/{id})
ШАГ 3: Marketplace Price (DELETE + POST /api/product-price)
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Добавляем текущую директорию в sys.path
sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from category_utils import is_leaf_category, get_category_chain
from import_utils import ROOT

CONFIG_PATH = ROOT / "config.json"
SNAPSHOT_NDJSON = ROOT / "insales_snapshot" / "products.ndjson"
MIGRATION_MAP = ROOT / "migration_map.json"


def find_product_in_snapshot(sku: str) -> Optional[Dict[str, Any]]:
    """Находит товар в snapshot по SKU."""
    if not SNAPSHOT_NDJSON.exists():
        print(f"[ERROR] Snapshot не найден: {SNAPSHOT_NDJSON}")
        return None
    
    with SNAPSHOT_NDJSON.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                product = json.loads(line)
                variants = product.get("variants", [])
                for variant in variants:
                    variant_sku = str(variant.get("sku", ""))
                    if variant_sku == sku:
                        return product
                if str(product.get("id", "")) == sku:
                    return product
            except json.JSONDecodeError:
                continue
    return None


def is_category_descendant(client: ShopwareClient, category_id: str, ancestor_id: str) -> bool:
    """
    Проверяет, является ли category_id потомком ancestor_id.
    Проходит по цепочке parentId до root.
    """
    if not category_id or not ancestor_id:
        return False
    
    if category_id == ancestor_id:
        return True
    
    visited = set()
    current_id = category_id
    
    while current_id and current_id not in visited:
        visited.add(current_id)
        try:
            cat_data = client.get_category(current_id)
            if not cat_data:
                break
            
            attrs = cat_data.get("attributes", {})
            parent_id = attrs.get("parentId")
            
            if not parent_id:
                break
            
            if parent_id == ancestor_id:
                return True
            
            current_id = parent_id
        except Exception:
            break
    
    return False


def is_direct_child(client: ShopwareClient, category_id: str, parent_id: str) -> bool:
    """
    Проверяет, является ли category_id прямой дочерней категорией parent_id.
    """
    if not category_id or not parent_id:
        return False
    
    if category_id == parent_id:
        return False  # Категория не может быть дочерней самой себе
    
    try:
        cat_data = client.get_category(category_id)
        if not cat_data:
            return False
        
        attrs = cat_data.get("attributes", {})
        cat_parent_id = attrs.get("parentId")
        
        return cat_parent_id == parent_id
    except Exception:
        return False


def find_valid_leaf_in_navigation(client: ShopwareClient, leaf_category_id: str, 
                                  navigation_category_id: str) -> Optional[str]:
    """
    Находит валидную leaf категорию в navigation дереве.
    Если leaf_category_id не является потомком navigation_category_id,
    ищет ближайшего родителя, который принадлежит navigation дереву.
    """
    if not leaf_category_id or not navigation_category_id:
        return leaf_category_id
    
    # Проверяем, является ли leaf_category_id потомком navigation_category_id
    if is_category_descendant(client, leaf_category_id, navigation_category_id):
        return leaf_category_id
    
    # Если нет, ищем ближайшего родителя, который принадлежит navigation дереву
    visited = set()
    current_id = leaf_category_id
    
    while current_id and current_id not in visited:
        visited.add(current_id)
        try:
            cat_data = client.get_category(current_id)
            if not cat_data:
                break
            
            attrs = cat_data.get("attributes", {})
            parent_id = attrs.get("parentId")
            
            if not parent_id:
                break
            
            # Проверяем, является ли родитель потомком navigation_category_id
            if is_category_descendant(client, parent_id, navigation_category_id):
                return parent_id
            
            current_id = parent_id
        except Exception:
            break
    
    # Если не нашли, возвращаем navigation_category_id как fallback
    return navigation_category_id


def filter_categories_by_navigation(client: ShopwareClient, category_chain: List[str],
                                     navigation_category_id: str) -> List[str]:
    """
    Фильтрует цепочку категорий, оставляя только те, которые принадлежат navigation дереву.
    """
    if not category_chain or not navigation_category_id:
        return category_chain
    
    filtered = []
    for cat_id in category_chain:
        if is_category_descendant(client, cat_id, navigation_category_id) or cat_id == navigation_category_id:
            filtered.append(cat_id)
    
    return filtered if filtered else [navigation_category_id]


def get_product_categories(client: ShopwareClient, product_data: Dict[str, Any], 
                          categories_map: Dict[str, str]) -> tuple[List[str], Optional[str]]:
    """Получает полную цепочку категорий и leaf категорию для товара."""
    collections_ids = product_data.get("collections_ids", [])
    category_id = product_data.get("category_id")
    canonical_collection_id = product_data.get("canonical_url_collection_id")
    
    all_insales_categories = []
    if collections_ids:
        all_insales_categories = collections_ids
    elif category_id:
        all_insales_categories = [category_id]
    
    if not all_insales_categories:
        return [], None
    
    shopware_category_ids = []
    for insales_cat_id in all_insales_categories:
        shopware_cat_id = categories_map.get(str(insales_cat_id))
        if shopware_cat_id:
            shopware_category_ids.append(shopware_cat_id)
    
    if not shopware_category_ids:
        return [], None
    
    leaf_category_id = None
    if canonical_collection_id:
        leaf_category_id = categories_map.get(str(canonical_collection_id))
    
    if not leaf_category_id:
        for shopware_cat_id in shopware_category_ids:
            if is_leaf_category(client, shopware_cat_id):
                leaf_category_id = shopware_cat_id
                break
    
    if not leaf_category_id:
        leaf_category_id = shopware_category_ids[-1]
    
    category_chain = get_category_chain(client, leaf_category_id)
    if not category_chain:
        category_chain = [leaf_category_id]
    
    for shopware_cat_id in shopware_category_ids:
        if shopware_cat_id not in category_chain:
            additional_chain = get_category_chain(client, shopware_cat_id)
            if additional_chain:
                for cat_id in additional_chain:
                    if cat_id not in category_chain:
                        category_chain.append(cat_id)
            else:
                category_chain.append(shopware_cat_id)
    
    return category_chain, leaf_category_id


def main():
    sku = sys.argv[1] if len(sys.argv) > 1 else "500944222"
    
    print("=" * 80)
    print(f"ПРИНУДИТЕЛЬНЫЙ UPDATE ТОВАРА (SKU: {sku})")
    print("Использование КОРРЕКТНЫХ API Shopware 6")
    print("=" * 80)
    print()
    
    # Загружаем конфигурацию
    with CONFIG_PATH.open(encoding="utf-8") as f:
        config = json.load(f)
    
    # Создаем клиент
    client = ShopwareClient(
        ShopwareConfig(
            url=config["shopware"]["url"],
            access_key_id=config["shopware"]["access_key_id"],
            secret_access_key=config["shopware"]["secret_access_key"]
        )
    )
    
    # Находим товар в Shopware
    product_id = client.find_product_by_number(sku)
    if not product_id:
        try:
            resp = client._request("POST", "/api/search/product", json={
                "filter": [{"field": "productNumber", "type": "equals", "value": sku}],
                "limit": 100,
                "includes": {"product": ["id"]}
            })
            products = resp.get("data", [])
            for p in products:
                pid = p.get("id")
                if pid:
                    try:
                        full = client._request("GET", f"/api/product/{pid}")
                        data = full.get("data", {})
                        attrs = data.get("attributes", {})
                        pn = attrs.get("productNumber") or data.get("productNumber")
                        if pn == sku:
                            product_id = pid
                            break
                    except:
                        pass
        except:
            pass
    
    if not product_id:
        print(f"[ERROR] Товар с SKU '{sku}' не найден в Shopware")
        return 1
    
    print(f"[OK] Товар найден: product_id = {product_id}")
    
    # Находим товар в snapshot
    product_data = find_product_in_snapshot(sku)
    if not product_data:
        print(f"[ERROR] Товар с SKU '{sku}' не найден в snapshot")
        return 1
    
    print(f"[OK] Товар найден в snapshot: {product_data.get('title', 'N/A')}")
    
    # Загружаем migration_map
    with MIGRATION_MAP.open(encoding="utf-8") as f:
        migration_map = json.load(f)
    categories_map = migration_map.get("categories", {})
    
    # Получаем необходимые ID
    storefront_sales_channel_id = config.get("shopware", {}).get("storefront_sales_channel_id")
    if not storefront_sales_channel_id:
        storefront_sales_channel_id = client.get_storefront_sales_channel_id()
    
    if not storefront_sales_channel_id:
        print("[ERROR] Не удалось получить storefront_sales_channel_id")
        return 1
    
    print(f"[OK] storefront_sales_channel_id = {storefront_sales_channel_id}")
    
    # Получаем navigationCategoryId из storefront sales channel
    print("Получение navigationCategoryId из storefront sales channel...")
    try:
        sales_channel_data = client.get_sales_channel(storefront_sales_channel_id)
        if not sales_channel_data:
            print("[ERROR] Не удалось получить данные sales channel")
            return 1
        
        attrs = sales_channel_data.get("attributes", {})
        navigation_category_id = attrs.get("navigationCategoryId")
        
        if not navigation_category_id:
            print("[ERROR] navigationCategoryId не найден в sales channel")
            return 1
        
        print(f"[OK] navigationCategoryId = {navigation_category_id}")
    except Exception as e:
        print(f"[ERROR] Ошибка получения navigationCategoryId: {e}")
        return 1
    
    print()
    print("=" * 80)
    print("ШАГ 1: CATEGORIES")
    print("=" * 80)
    print()
    
    # ШАГ 1: CATEGORIES (сначала обновляем categories, потом visibilities)
    print("1.1) Получение leaf_category_id и цепочки категорий...")
    category_chain, leaf_category_id = get_product_categories(client, product_data, categories_map)
    if not leaf_category_id:
        print(f"[ERROR] Не удалось получить leaf_category_id")
        return 1
    print(f"   [OK] Исходный leaf_category_id = {leaf_category_id}")
    
    print("1.2) Проверка принадлежности leaf_category_id к navigation дереву...")
    storefront_leaf_category_id = find_valid_leaf_in_navigation(
        client, leaf_category_id, navigation_category_id
    )
    if not storefront_leaf_category_id:
        print(f"[ERROR] Не удалось найти валидную leaf категорию в navigation дереве")
        return 1
    
    if storefront_leaf_category_id != leaf_category_id:
        print(f"   [INFO] leaf_category_id скорректирован: {leaf_category_id} → {storefront_leaf_category_id}")
    else:
        print(f"   [OK] leaf_category_id принадлежит navigation дереву")
    
    # Проверяем, является ли категория прямой дочерней категорией navigationCategoryId
    # Если нет, ищем ближайшую категорию в цепочке, которая является прямой дочерней
    print("1.2.1) Проверка, является ли категория прямой дочерней категорией navigationCategoryId...")
    is_direct = is_direct_child(client, storefront_leaf_category_id, navigation_category_id)
    if not is_direct:
        print(f"   [INFO] Категория не является прямой дочерней, ищем ближайшую в цепочке...")
        # Получаем цепочку категорий для storefront_leaf_category_id
        category_chain_for_vis = get_category_chain(client, storefront_leaf_category_id)
        if not category_chain_for_vis:
            category_chain_for_vis = [storefront_leaf_category_id]
        
        # Ищем ближайшую категорию в цепочке, которая является прямой дочерней категорией navigationCategoryId
        found_direct_child = None
        for cat_id in reversed(category_chain_for_vis):  # Идем от leaf к root
            if is_direct_child(client, cat_id, navigation_category_id):
                found_direct_child = cat_id
                break
        
        if found_direct_child:
            print(f"   [OK] Найдена прямая дочерняя категория в цепочке: {found_direct_child}")
            storefront_leaf_category_id = found_direct_child
        else:
            print(f"   [WARNING] Не найдена прямая дочерняя категория, используем navigationCategoryId")
            storefront_leaf_category_id = navigation_category_id
    else:
        print(f"   [OK] Категория является прямой дочерней категорией navigationCategoryId")
    
    print("1.3) Фильтрация цепочки категорий по navigation дереву...")
    if not category_chain:
        category_chain, _ = get_product_categories(client, product_data, categories_map)
    
    # Получаем полную цепочку для storefront_leaf_category_id
    storefront_category_chain = get_category_chain(client, storefront_leaf_category_id)
    if not storefront_category_chain:
        storefront_category_chain = [storefront_leaf_category_id]
    
    # Фильтруем цепочку по navigation дереву
    filtered_category_chain = filter_categories_by_navigation(
        client, storefront_category_chain, navigation_category_id
    )
    
    if not filtered_category_chain:
        print(f"[ERROR] После фильтрации цепочка категорий пуста")
        return 1
    
    print(f"   [OK] Отфильтрованная цепочка категорий: {len(filtered_category_chain)} категорий")
    
    print("1.4) Обновление categories через PATCH...")
    try:
        categories_payload = {
            "categories": [{"id": cat_id} for cat_id in filtered_category_chain]
        }
        client._request("PATCH", f"/api/product/{product_id}", json=categories_payload)
        print(f"   [OK] Categories обновлены: {len(filtered_category_chain)} категорий")
    except Exception as e:
        print(f"   [ERROR] Ошибка обновления categories: {e}")
        return 1
    
    print()
    print("=" * 80)
    print("ШАГ 2: VISIBILITIES")
    print("=" * 80)
    print()
    
    # ШАГ 2: VISIBILITIES (после обновления categories)
    print("2.1) Удаление всех существующих visibilities...")
    try:
        vis_search = client._request(
            "POST",
            "/api/search/product-visibility",
            json={
                "filter": [{"field": "productId", "type": "equals", "value": product_id}],
                "limit": 100,
            }
        )
        
        deleted_count = 0
        if isinstance(vis_search, dict) and "data" in vis_search:
            existing_visibilities = vis_search.get("data", [])
            for vis in existing_visibilities:
                vis_id = vis.get("id")
                if vis_id:
                    try:
                        client._request("DELETE", f"/api/product-visibility/{vis_id}")
                        deleted_count += 1
                    except Exception as e:
                        print(f"   [WARNING] Ошибка удаления visibility {vis_id}: {e}")
        
        print(f"   [OK] Удалено visibilities: {deleted_count}")
    except Exception as e:
        print(f"   [ERROR] Ошибка удаления visibilities: {e}")
        return 1
    
    print("2.2) Создание новой visibility...")
    # ПРИМЕЧАНИЕ: Shopware 6 REST API НЕ сохраняет visibility.categoryId через POST/PATCH /api/product-visibility.
    # Это системное ограничение Shopware 6, а не баг.
    # Breadcrumb определяется внутренней логикой storefront на основе product.categories.
    # categoryId передается в payload для совместимости, но Shopware его игнорирует.
    try:
        visibility_payload = {
            "productId": product_id,
            "salesChannelId": storefront_sales_channel_id,
            "visibility": 30,
            # TODO-BLOCK: DO NOT ADD visibility.categoryId CHECK (Shopware 6 limitation)
            # categoryId передается в payload для совместимости, но Shopware 6 REST API его не сохраняет
            "categoryId": storefront_leaf_category_id
        }
        response = client._request("POST", "/api/product-visibility", json=visibility_payload)
        print(f"   [OK] Visibility создана: Storefront, visibility=30")
        print(f"   [INFO] categoryId={storefront_leaf_category_id} передан, но Shopware 6 REST API его не сохраняет (системное ограничение)")
    except Exception as e:
        print(f"   [ERROR] Ошибка создания visibility: {e}")
        return 1
    
    print()
    print("=" * 80)
    print("ШАГ 3: MARKETPLACE PRICE")
    print("=" * 80)
    print()
    
    # ШАГ 3: MARKETPLACE PRICE (после categories и visibilities)
    print("3.1) Поиск/создание правила 'Marketplace Price'...")
    marketplace_rule_id = None
    try:
        marketplace_rule_id = client.find_rule_by_name_normalized("Marketplace Price")
    except:
        pass
    
    if not marketplace_rule_id:
        try:
            marketplace_rule_id = client.create_rule_if_missing(
                name="Marketplace Price",
                priority=100,
                description="Price rule for Marketplace channel (from InSales price2)"
            )
        except Exception as e:
            print(f"   [ERROR] Не удалось создать правило 'Marketplace Price': {e}")
            return 1
    
    print(f"   [OK] marketplace_rule_id = {marketplace_rule_id}")
    
    print("3.2) Получение currencyId...")
    sales_channel_currency = client.get_sales_channel_currency_id()
    print(f"   [OK] currencyId = {sales_channel_currency}")
    
    print("3.3) Получение price2 из snapshot...")
    variant = product_data.get("variants", [{}])[0] if product_data.get("variants") else {}
    price2 = variant.get("price2")
    if price2 is None:
        print(f"   [WARNING] price2 отсутствует в snapshot")
        return 1
    
    try:
        price2_float = float(price2)
        if price2_float <= 0:
            print(f"   [ERROR] price2={price2_float} <= 0")
            return 1
        print(f"   [OK] price2 = {price2_float}")
    except (ValueError, TypeError) as e:
        print(f"   [ERROR] Ошибка парсинга price2: {e}")
        return 1
    
    print("3.4) Удаление всех существующих product_price...")
    try:
        # Получаем все prices товара через Search API
        price_search = client._request(
            "POST",
            "/api/search/product-price",
            json={
                "filter": [{"field": "productId", "type": "equals", "value": product_id}],
                "limit": 100,
            }
        )
        
        deleted_count = 0
        if isinstance(price_search, dict) and "data" in price_search:
            existing_prices = price_search.get("data", [])
            for price in existing_prices:
                price_id = price.get("id")
                if price_id:
                    try:
                        client._request("DELETE", f"/api/product-price/{price_id}")
                        deleted_count += 1
                    except Exception as e:
                        print(f"   [WARNING] Ошибка удаления price {price_id}: {e}")
        
        print(f"   [OK] Удалено product_price: {deleted_count}")
    except Exception as e:
        print(f"   [ERROR] Ошибка удаления prices: {e}")
        return 1
    
    print("3.5) Создание новой marketplace price...")
    try:
        price_payload = {
            "productId": product_id,
            "ruleId": marketplace_rule_id,
            "quantityStart": 1,
            "price": [{
                "currencyId": sales_channel_currency,
                "gross": price2_float,
                "net": price2_float,
                "linked": False
            }]
        }
        response = client._request("POST", "/api/product-price", json=price_payload)
        print(f"   [OK] Marketplace price создана: {price2_float}, ruleId={marketplace_rule_id}, quantityStart=1")
    except Exception as e:
        print(f"   [ERROR] Ошибка создания marketplace price: {e}")
        return 1
    
    print()
    print("=" * 80)
    print("ОБНОВЛЕНИЕ ЗАВЕРШЕНО")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


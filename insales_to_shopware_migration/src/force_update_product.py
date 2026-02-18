"""
Принудительный UPDATE товара для приведения в каноническое состояние.
Исправляет: ean, visibilities, categories, marketplace price.
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
                # Ищем по variant.sku (приоритет) или product.id
                variants = product.get("variants", [])
                for variant in variants:
                    variant_sku = str(variant.get("sku", ""))
                    if variant_sku == sku:
                        return product
                # Fallback: ищем по product.id
                if str(product.get("id", "")) == sku:
                    return product
            except json.JSONDecodeError:
                continue
    return None


def get_product_categories(client: ShopwareClient, product_data: Dict[str, Any], 
                          categories_map: Dict[str, str]) -> tuple[List[str], Optional[str]]:
    """Получает полную цепочку категорий и leaf категорию для товара."""
    collections_ids = product_data.get("collections_ids", [])
    category_id = product_data.get("category_id")
    canonical_collection_id = product_data.get("canonical_url_collection_id")
    
    # Формируем список всех категорий товара
    all_insales_categories = []
    if collections_ids:
        all_insales_categories = collections_ids
    elif category_id:
        all_insales_categories = [category_id]
    
    if not all_insales_categories:
        return [], None
    
    # Маппим категории InSales -> Shopware
    shopware_category_ids = []
    for insales_cat_id in all_insales_categories:
        shopware_cat_id = categories_map.get(str(insales_cat_id))
        if shopware_cat_id:
            shopware_category_ids.append(shopware_cat_id)
    
    if not shopware_category_ids:
        return [], None
    
    # Определяем leaf-категорию
    leaf_category_id = None
    # Сначала canonical_url_collection_id
    if canonical_collection_id:
        leaf_category_id = categories_map.get(str(canonical_collection_id))
    
    # Затем is_leaf_category()
    if not leaf_category_id:
        for shopware_cat_id in shopware_category_ids:
            if is_leaf_category(client, shopware_cat_id):
                leaf_category_id = shopware_cat_id
                break
    
    # Fallback: последняя из списка
    if not leaf_category_id:
        leaf_category_id = shopware_category_ids[-1]
    
    # Формируем полную цепочку категорий
    category_chain = get_category_chain(client, leaf_category_id)
    if not category_chain:
        category_chain = [leaf_category_id]
    
    # Объединяем все связанные категории без дублей
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
    
    # Если не нашли через find_product_by_number, пробуем прямой поиск
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
    
    # Загружаем migration_map для категорий
    with MIGRATION_MAP.open(encoding="utf-8") as f:
        migration_map = json.load(f)
    categories_map = migration_map.get("categories", {})
    
    # Получаем необходимые ID
    storefront_sales_channel_id = config.get("shopware", {}).get("storefront_sales_channel_id")
    if not storefront_sales_channel_id:
        storefront_sales_channel_id = client.get_storefront_sales_channel_id()
    
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
            print(f"[WARNING] Не удалось создать правило 'Marketplace Price': {e}")
    
    sales_channel_currency = client.get_sales_channel_currency_id()
    
    # Получаем данные варианта
    variant = product_data.get("variants", [{}])[0] if product_data.get("variants") else {}
    price2 = variant.get("price2")
    
    print()
    print("=" * 80)
    print("ПРИМЕНЕНИЕ ИЗМЕНЕНИЙ")
    print("=" * 80)
    print()
    
    # 1) Устанавливаем ean = null
    print("1) Установка ean = null...")
    try:
        ean_payload = {"ean": None}
        client._request("PATCH", f"/api/product/{product_id}", json=ean_payload)
        print("   [OK] ean установлен в null")
    except Exception as e:
        print(f"   [ERROR] Ошибка установки ean: {e}")
        return 1
    
    # 2) Удаляем все visibilities и добавляем новую
    print("2) Обновление visibilities...")
    try:
        # Получаем все существующие visibilities
        vis_search = client._request(
            "POST",
            "/api/search/product-visibility",
            json={
                "filter": [{"field": "productId", "type": "equals", "value": product_id}],
                "limit": 100,
            }
        )
        
        # Удаляем все существующие visibilities
        if isinstance(vis_search, dict) and "data" in vis_search:
            existing_visibilities = vis_search.get("data", [])
            for vis in existing_visibilities:
                vis_id = vis.get("id")
                if vis_id:
                    try:
                        client._request("DELETE", f"/api/product-visibility/{vis_id}")
                    except Exception:
                        pass  # Игнорируем ошибки удаления
        
        # Получаем категории для visibility
        category_chain, leaf_category_id = get_product_categories(client, product_data, categories_map)
        
        # Добавляем новую visibility для Storefront
        if storefront_sales_channel_id:
            # Получаем категории для visibility
            category_chain, leaf_category_id = get_product_categories(client, product_data, categories_map)
            
            visibility_item = {
                "salesChannelId": storefront_sales_channel_id,
                "visibility": 30
            }
            if leaf_category_id:
                visibility_item["categoryId"] = leaf_category_id
            
            visibilities_payload = {"visibilities": [visibility_item]}
            
            import time
            time.sleep(0.3)  # Задержка после удаления старых visibilities
            
            client._request("PATCH", f"/api/product/{product_id}", json=visibilities_payload)
            print(f"   [OK] Visibilities обновлены: Storefront, visibility=30, categoryId={leaf_category_id or 'N/A'}")
        else:
            print(f"   [WARNING] storefront_sales_channel_id не найден")
    except Exception as e:
        print(f"   [ERROR] Ошибка обновления visibilities: {e}")
        return 1
    
    # 3) Обновляем categories и mainCategory
    print("3) Обновление categories...")
    try:
        category_chain, leaf_category_id = get_product_categories(client, product_data, categories_map)
        
        if category_chain and leaf_category_id:
            # Обновляем categories и mainCategory в одном PATCH
            categories_payload = {
                "categories": [{"id": cat_id} for cat_id in category_chain],
            }
            if storefront_sales_channel_id:
                categories_payload["mainCategories"] = [{
                    "salesChannelId": storefront_sales_channel_id,
                    "categoryId": leaf_category_id
                }]
            
            try:
                client._request("PATCH", f"/api/product/{product_id}", json=categories_payload)
            except Exception as cat_e:
                # Если ошибка дубликата mainCategory, пробуем отдельно
                if "duplicate" in str(cat_e).lower() or "main_category" in str(cat_e).lower():
                    # Обновляем только categories
                    categories_only_payload = {"categories": [{"id": cat_id} for cat_id in category_chain]}
                    client._request("PATCH", f"/api/product/{product_id}", json=categories_only_payload)
                else:
                    raise
            
            import time
            time.sleep(0.5)  # Задержка для применения изменений
            
            print(f"   [OK] Categories обновлены: {len(category_chain)} категорий, mainCategory={leaf_category_id}")
        else:
            print(f"   [WARNING] Не удалось получить категории для товара")
    except Exception as e:
        print(f"   [ERROR] Ошибка обновления categories: {e}")
        return 1
    
    # 4) Удаляем все advanced prices и добавляем marketplace price
    print("4) Обновление marketplace price...")
    try:
        if marketplace_rule_id and price2 is not None:
            try:
                price2_float = float(price2)
                if price2_float > 0:
                    # УДАЛЯЕМ ВСЕ advanced prices, устанавливая только marketplace price
                    # PATCH с новым списком prices заменит все существующие advanced prices
                    new_prices = [{
                        "ruleId": marketplace_rule_id,
                        "quantityStart": 1,
                        "price": [{
                            "currencyId": sales_channel_currency,
                            "gross": price2_float,
                            "net": price2_float,
                            "linked": False
                        }]
                    }]
                    
                    prices_payload = {"prices": new_prices}
                    client._request("PATCH", f"/api/product/{product_id}", json=prices_payload)
                    print(f"   [OK] Marketplace price обновлена: {price2_float}, ruleId={marketplace_rule_id}, quantityStart=1")
                    print(f"   [OK] Все остальные advanced prices удалены")
                else:
                    print(f"   [WARNING] price2={price2_float} <= 0, пропущено")
            except (ValueError, TypeError) as e:
                print(f"   [ERROR] Ошибка парсинга price2: {e}")
        else:
            if not marketplace_rule_id:
                print(f"   [WARNING] marketplace_rule_id не найден")
            if price2 is None:
                print(f"   [WARNING] price2 отсутствует в snapshot")
    except Exception as e:
        print(f"   [ERROR] Ошибка обновления marketplace price: {e}")
        return 1
    
    print()
    print("=" * 80)
    print("ОБНОВЛЕНИЕ ЗАВЕРШЕНО")
    print("=" * 80)
    print()
    print("[INFO] Ожидание применения изменений в Shopware API...")
    import time
    time.sleep(2)  # Задержка для применения изменений в Shopware
    print("[INFO] Готово. Можно запускать проверку.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


"""
Исправление categoryId через отдельный endpoint /api/product-visibility/{id}.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json, ROOT, split_pipe
import csv

def find_storefront_sales_channel(client: ShopwareClient) -> str | None:
    """Находит ID storefront sales channel."""
    try:
        sc_response = client._request("GET", "/api/sales-channel")
        sales_channels = sc_response.get("data", []) if isinstance(sc_response, dict) else []
        
        for sc in sales_channels:
            attrs = sc.get("attributes", {})
            type_id = attrs.get("typeId")
            if not type_id:
                continue
            try:
                type_resp = client._request("GET", f"/api/sales-channel-type/{type_id}")
                type_data = type_resp.get("data", {}) if isinstance(type_resp, dict) else {}
                type_attrs = type_data.get("attributes", {})
                type_name = type_attrs.get("name", "").lower()
                if "storefront" in type_name:
                    return sc.get("id")
            except Exception:
                continue
    except Exception as e:
        print(f"ERROR: Failed to find storefront sales channel: {e}")
    return None

def find_product_by_number(client: ShopwareClient, product_number: str) -> str | None:
    """Находит product ID по productNumber."""
    try:
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [{"field": "productNumber", "type": "equals", "value": product_number}],
                "limit": 1
            }
        )
        data = response.get("data", []) if isinstance(response, dict) else []
        if data:
            return data[0].get("id")
    except Exception as e:
        print(f"ERROR: Failed to find product: {e}")
    return None

def update_categoryId_via_visibility(client: ShopwareClient, product_id: str, storefront_sc_id: str, main_category_id: str) -> bool:
    """Обновляет categoryId через отдельный endpoint /api/product-visibility/{id}."""
    try:
        # Получаем существующие visibilities
        vis_response = client._request("GET", f"/api/product/{product_id}/visibilities")
        vis_data = vis_response.get("data", []) if isinstance(vis_response, dict) else []
        
        # Ищем visibility для storefront
        visibility_id = None
        for vis_item in vis_data:
            vis_attrs = vis_item.get("attributes", {})
            if vis_attrs.get("salesChannelId") == storefront_sc_id:
                visibility_id = vis_item.get("id")
                break
        
        if not visibility_id:
            print(f"  [ERROR] Visibility для storefront не найдена")
            return False
        
        # Обновляем через отдельный endpoint
        update_payload = {
            "categoryId": main_category_id
        }
        
        client._request("PATCH", f"/api/product-visibility/{visibility_id}", json=update_payload)
        return True
        
    except Exception as e:
        print(f"  [ERROR] Ошибка при обновлении: {e}")
        return False

def main():
    config_path = ROOT / "config.json"
    config = load_json(config_path)
    
    shopware_config = ShopwareConfig(
        url=config["shopware"]["url"],
        access_key_id=config["shopware"]["access_key_id"],
        secret_access_key=config["shopware"]["secret_access_key"],
    )
    client = ShopwareClient(shopware_config)
    
    # Находим storefront sales channel
    storefront_sc_id = find_storefront_sales_channel(client)
    if not storefront_sc_id:
        print("❌ [ERROR] Storefront sales channel не найден")
        return 1
    
    print(f"✅ [OK] Storefront sales channel: {storefront_sc_id}")
    
    # Читаем CSV
    csv_path = ROOT / "output" / "products_import.csv"
    if not csv_path.exists():
        print(f"❌ [ERROR] CSV файл не найден: {csv_path}")
        return 1
    
    print(f"\nЧтение CSV...")
    rows = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    
    print(f"Загружено из CSV: {len(rows)} товаров")
    
    # Получаем все товары из Shopware
    print(f"\nПолучение товаров из Shopware...")
    products_response = client._request("POST", "/api/search/product", json={"limit": 500})
    products_data = products_response.get("data", []) if isinstance(products_response, dict) else []
    
    print(f"Найдено товаров в Shopware: {len(products_data)}")
    
    # Создаём маппинг productNumber -> product_id
    product_map = {}
    for product in products_data:
        product_attrs = product.get("attributes", {})
        product_number = product_attrs.get("productNumber")
        if product_number:
            product_map[product_number] = product.get("id")
    
    # Обновляем categoryId для каждого товара
    print(f"\n{'='*60}")
    print(f"НАЧАЛО ОБНОВЛЕНИЯ CATEGORYID")
    print(f"{'='*60}")
    
    updated = 0
    skipped = 0
    errors = 0
    
    for row in rows:
        product_number = row.get("productNumber", "").strip()
        if not product_number:
            continue
        
        product_id = product_map.get(product_number)
        if not product_id:
            skipped += 1
            continue
        
        main_category_id = row.get("mainCategoryId", "").strip()
        if not main_category_id:
            skipped += 1
            continue
        
        if update_categoryId_via_visibility(client, product_id, storefront_sc_id, main_category_id):
            updated += 1
            print(f"  [OK] {product_number}: categoryId обновлён")
        else:
            errors += 1
            print(f"  [FAIL] {product_number}: ошибка обновления")
    
    print(f"\n{'='*60}")
    print(f"ОБНОВЛЕНИЕ ЗАВЕРШЕНО")
    print(f"{'='*60}")
    print(f"Обновлено: {updated}")
    print(f"Пропущено: {skipped}")
    print(f"Ошибок: {errors}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())


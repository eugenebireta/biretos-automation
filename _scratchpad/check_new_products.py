"""
Проверка созданных товаров и их visibilities.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json, ROOT

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

def check_visibilities(client: ShopwareClient, product_id: str):
    """Проверяет visibilities товара."""
    try:
        # Получаем информацию о товаре
        product_response = client._request("GET", f"/api/product/{product_id}")
        product_data = product_response.get("data", {}) if isinstance(product_response, dict) else {}
        product_attrs = product_data.get("attributes", {})
        
        product_number = product_attrs.get("productNumber", "N/A")
        product_name = product_attrs.get("name", "N/A")
        
        print(f"\n{'='*60}")
        print(f"Товар: {product_number} - {product_name}")
        print(f"{'='*60}")
        
        # Получаем visibilities
        vis_response = client._request("GET", f"/api/product/{product_id}/visibilities")
        vis_data = vis_response.get("data", []) if isinstance(vis_response, dict) else []
        
        if not vis_data:
            print("❌ [FAIL] Visibilities отсутствуют")
            return False
        
        print(f"✅ [OK] Найдено visibilities: {len(vis_data)}")
        
        # Находим storefront sales channel
        sc_response = client._request("GET", "/api/sales-channel")
        sales_channels = sc_response.get("data", []) if isinstance(sc_response, dict) else []
        
        storefront_sc_id = None
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
                    storefront_sc_id = sc.get("id")
                    break
            except Exception:
                continue
        
        if not storefront_sc_id:
            print("❌ [FAIL] Storefront sales channel не найден")
            return False
        
        print(f"✅ [OK] Storefront sales channel ID: {storefront_sc_id}")
        
        # Ищем visibility для storefront
        storefront_visibility = None
        for vis_item in vis_data:
            vis_attrs = vis_item.get("attributes", {})
            sc_id = vis_attrs.get("salesChannelId")
            if sc_id == storefront_sc_id:
                storefront_visibility = vis_item  # Используем весь объект, а не только attributes
                break
        
        if not storefront_visibility:
            print(f"❌ [FAIL] Visibility для storefront sales channel не найдена")
            return False
        
        print(f"✅ [OK] Visibility для storefront найдена")
        
        # Проверяем categoryId - может быть в attributes или в relationships
        vis_attrs = storefront_visibility.get("attributes", {})
        category_id = vis_attrs.get("categoryId")
        
        # Если не в attributes, проверяем relationships
        if not category_id:
            relationships = storefront_visibility.get("relationships", {})
            category_rel = relationships.get("category")
            if category_rel:
                category_data = category_rel.get("data", {})
                category_id = category_data.get("id")
        if not category_id:
            print(f"❌ [FAIL] categoryId отсутствует в storefront visibility")
            print(f"   Visibility data: {storefront_visibility}")
            return False
        
        print(f"✅ [OK] categoryId установлен: {category_id}")
        
        # Проверяем другие visibilities
        other_visibilities = [v for v in vis_data if v.get("attributes", {}).get("salesChannelId") != storefront_sc_id]
        if other_visibilities:
            print(f"✅ [OK] Другие visibilities: {len(other_visibilities)}")
        
        print(f"\n✅ [SUCCESS] Все проверки пройдены")
        return True
        
    except Exception as e:
        print(f"❌ [ERROR] Ошибка при проверке: {e}")
        import traceback
        traceback.print_exc()
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
    
    # Проверяем созданные товары
    product_numbers = ["498271720", "498271735", "498271898"]
    
    success_count = 0
    for product_number in product_numbers:
        product_id = find_product_by_number(client, product_number)
        if not product_id:
            print(f"❌ [ERROR] Товар {product_number} не найден")
            continue
        
        if check_visibilities(client, product_id):
            success_count += 1
    
    print(f"\n{'='*60}")
    print(f"Итого: {success_count}/{len(product_numbers)} товаров прошли проверку")
    print(f"{'='*60}")
    
    return 0 if success_count == len(product_numbers) else 1

if __name__ == "__main__":
    sys.exit(main())


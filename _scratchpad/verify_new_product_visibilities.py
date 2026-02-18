"""
Проверка, что при создании нового товара categoryId корректно устанавливается в visibilities.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json, ROOT

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

def verify_product_visibilities(client: ShopwareClient, product_id: str, expected_category_id: str | None = None):
    """Проверяет visibilities товара и наличие categoryId для storefront."""
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
        storefront_sc_id = find_storefront_sales_channel(client)
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
                storefront_visibility = vis_attrs
                break
        
        if not storefront_visibility:
            print(f"❌ [FAIL] Visibility для storefront sales channel не найдена")
            return False
        
        print(f"✅ [OK] Visibility для storefront найдена")
        
        # Проверяем categoryId
        category_id = storefront_visibility.get("categoryId")
        if not category_id:
            print(f"❌ [FAIL] categoryId отсутствует в storefront visibility")
            print(f"   Visibility data: {storefront_visibility}")
            return False
        
        print(f"✅ [OK] categoryId установлен: {category_id}")
        
        if expected_category_id and category_id != expected_category_id:
            print(f"⚠️  [WARNING] categoryId не совпадает с ожидаемым")
            print(f"   Ожидалось: {expected_category_id}")
            print(f"   Получено: {category_id}")
            return False
        
        # Проверяем другие visibilities
        other_visibilities = [v for v in vis_data if v.get("attributes", {}).get("salesChannelId") != storefront_sc_id]
        if other_visibilities:
            print(f"✅ [OK] Другие visibilities: {len(other_visibilities)}")
            for vis_item in other_visibilities:
                vis_attrs = vis_item.get("attributes", {})
                sc_id = vis_attrs.get("salesChannelId")
                has_category = "categoryId" in vis_attrs and vis_attrs.get("categoryId")
                print(f"   - Sales Channel {sc_id}: categoryId={'✅' if has_category else '❌'}")
        
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
    
    # Запрашиваем product_id для проверки
    if len(sys.argv) > 1:
        product_id = sys.argv[1]
    else:
        product_id = input("Введите product ID для проверки: ").strip()
    
    if not product_id:
        print("❌ [ERROR] Product ID не указан")
        return 1
    
    success = verify_product_visibilities(client, product_id)
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())


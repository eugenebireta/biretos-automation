"""Проверка структуры visibilities с categoryId"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json

ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
config = load_json(ROOT / "config.json")

shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

print("=" * 60)
print("ПРОВЕРКА СТРУКТУРЫ VISIBILITIES")
print("=" * 60)

# Получаем товар
response = client._request("GET", "/api/product", params={"limit": 1})
products = response.get("data", []) if isinstance(response, dict) else []

if products:
    product_id = products[0].get("id")
    
    # Получаем visibilities
    print(f"\n1. Получение visibilities для товара {product_id}...")
    try:
        vis_response = client._request("GET", f"/api/product/{product_id}/visibilities")
        vis_data = vis_response.get("data", []) if isinstance(vis_response, dict) else []
        
        print(f"   Найдено visibilities: {len(vis_data)}")
        if vis_data:
            print(f"\n2. Структура visibility:")
            for idx, vis in enumerate(vis_data[:3], 1):
                attrs = vis.get("attributes", {})
                print(f"   Visibility {idx}:")
                print(f"     salesChannelId: {attrs.get('salesChannelId', 'N/A')}")
                print(f"     visibility: {attrs.get('visibility', 'N/A')}")
                print(f"     categoryId: {attrs.get('categoryId', 'N/A')}")
                print(f"     productId: {attrs.get('productId', 'N/A')}")
        else:
            print("   ⚠️ Visibilities не найдены")
            
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")

# Проверяем Sales Channels
print(f"\n3. Проверка Sales Channels...")
try:
    sc_response = client._request("GET", "/api/sales-channel")
    sales_channels = sc_response.get("data", []) if isinstance(sc_response, dict) else []
    
    print(f"   Найдено Sales Channels: {len(sales_channels)}")
    for sc in sales_channels:
        attrs = sc.get("attributes", {})
        sc_id = sc.get("id")
        sc_type = attrs.get("typeId", "N/A")
        sc_name = attrs.get("name", "N/A")
        
        # Получаем тип Sales Channel
        if sc_type != "N/A":
            try:
                type_response = client._request("GET", f"/api/sales-channel-type/{sc_type}")
                type_data = type_response.get("data", {}) if isinstance(type_response, dict) else {}
                type_attrs = type_data.get("attributes", {})
                type_name = type_attrs.get("name", "N/A")
                print(f"   - {sc_name} (ID: {sc_id[:16]}..., Type: {type_name})")
                
                if "storefront" in type_name.lower():
                    print(f"     ✅ Это STOREFRONT Sales Channel!")
            except:
                print(f"   - {sc_name} (ID: {sc_id[:16]}...)")
        else:
            print(f"   - {sc_name} (ID: {sc_id[:16]}...)")
            
except Exception as e:
    print(f"   ❌ Ошибка: {e}")

print("\n" + "=" * 60)









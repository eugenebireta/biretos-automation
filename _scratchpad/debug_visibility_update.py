"""Отладка обновления visibility"""
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

# Получаем storefront
sc_response = client._request("GET", "/api/sales-channel")
sales_channels = sc_response.get("data", []) if isinstance(sc_response, dict) else []

STOREFRONT_SALES_CHANNEL_ID = None
for sc in sales_channels:
    sc_id = sc.get("id")
    if not sc_id:
        continue
    try:
        sc_attrs = sc.get("attributes", {})
        type_id = sc_attrs.get("typeId")
        if type_id:
            type_response = client._request("GET", f"/api/sales-channel-type/{type_id}")
            type_data = type_response.get("data", {}) if isinstance(type_response, dict) else {}
            type_attrs = type_data.get("attributes", {})
            type_name = type_attrs.get("name", "").lower()
            if "storefront" in type_name:
                STOREFRONT_SALES_CHANNEL_ID = sc_id
                break
    except Exception:
        continue

print(f"Storefront Sales Channel ID: {STOREFRONT_SALES_CHANNEL_ID}")

# Проверяем товар
product_number = "498271735"
response = client._request("GET", "/api/product", params={"filter[productNumber]": product_number})
products = response.get("data", []) if isinstance(response, dict) else []

if products:
    product_id = products[0].get("id")
    
    # Получаем visibilities
    vis_response = client._request("GET", f"/api/product/{product_id}/visibilities")
    vis_data = vis_response.get("data", []) if isinstance(vis_response, dict) else []
    
    print(f"\nТовар: {product_number}")
    print(f"Visibilities: {len(vis_data)}")
    
    for vis_item in vis_data:
        vis_id = vis_item.get("id")
        vis_attrs = vis_item.get("attributes", {})
        sc_id = vis_attrs.get("salesChannelId")
        category_id = vis_attrs.get("categoryId")
        visibility = vis_attrs.get("visibility")
        
        print(f"\n  Visibility ID: {vis_id}")
        print(f"  Sales Channel ID: {sc_id}")
        print(f"  Category ID: {category_id}")
        print(f"  Visibility: {visibility}")
        
        if sc_id == STOREFRONT_SALES_CHANNEL_ID:
            print(f"  ✅ Это STOREFRONT visibility")
            if category_id:
                print(f"  ✅ categoryId установлен: {category_id}")
            else:
                print(f"  ❌ categoryId НЕ установлен")
                
                # Пробуем обновить
                main_category_id = "67c46b54a5944429ab54e64707dd6418"  # Из CSV
                print(f"\n  Попытка обновления с categoryId: {main_category_id}")
                
                payload = {
                    "id": product_id,
                    "visibilities": [{
                        "id": vis_id,  # Включаем id для обновления
                        "salesChannelId": STOREFRONT_SALES_CHANNEL_ID,
                        "visibility": visibility,
                        "categoryId": main_category_id
                    }]
                }
                
                try:
                    client._request("PATCH", f"/api/product/{product_id}", json=payload)
                    print(f"  ✅ Обновление отправлено")
                    
                    # Проверяем результат
                    vis_response2 = client._request("GET", f"/api/product/{product_id}/visibilities")
                    vis_data2 = vis_response2.get("data", []) if isinstance(vis_response2, dict) else []
                    for vis_item2 in vis_data2:
                        vis_attrs2 = vis_item2.get("attributes", {})
                        if vis_attrs2.get("salesChannelId") == STOREFRONT_SALES_CHANNEL_ID:
                            new_category_id = vis_attrs2.get("categoryId")
                            print(f"  Новый categoryId: {new_category_id if new_category_id else 'НЕТ'}")
                            break
                except Exception as e:
                    print(f"  ❌ Ошибка обновления: {e}")









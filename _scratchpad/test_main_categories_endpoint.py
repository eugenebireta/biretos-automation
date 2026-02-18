"""Тест установки mainCategory через main-categories endpoint"""
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
    main_category_id = "67c46b54a5944429ab54e64707dd6418"
    
    print(f"\nТовар: {product_number}")
    print(f"mainCategoryId: {main_category_id}")
    
    # Пробуем создать main-category через Sync API
    print(f"\nСоздание main-category через Sync API...")
    
    import uuid
    main_cat_id = str(uuid.uuid4()).replace('-', '')
    
    sync_body = {
        "product_main_category": {
            "entity": "product_main_category",
            "action": "upsert",
            "payload": [
                {
                    "id": main_cat_id,
                    "productId": product_id,
                    "salesChannelId": STOREFRONT_SALES_CHANNEL_ID,
                    "categoryId": main_category_id
                }
            ]
        }
    }
    
    try:
        response = client._request("POST", "/api/_action/sync", json=sync_body)
        print(f"✅ Sync API ответ получен")
        print(f"Response: {response}")
        
        # Проверяем результат
        mc_response = client._request("GET", f"/api/product/{product_id}/main-categories")
        mc_data = mc_response.get("data", []) if isinstance(mc_response, dict) else []
        print(f"\nMain Categories после создания: {len(mc_data)}")
        
        if mc_data:
            for mc_item in mc_data:
                mc_attrs = mc_item.get("attributes", {})
                print(f"  Category ID: {mc_attrs.get('categoryId')}")
                print(f"  Sales Channel ID: {mc_attrs.get('salesChannelId')}")
        else:
            print("  ⚠️ Main Categories не найдены")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()









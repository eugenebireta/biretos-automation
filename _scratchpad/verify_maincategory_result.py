"""Проверка результата обновления mainCategory"""
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
print("ПРОВЕРКА РЕЗУЛЬТАТА ОБНОВЛЕНИЯ mainCategory")
print("=" * 60)

# Получаем storefront sales channel
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

if not STOREFRONT_SALES_CHANNEL_ID:
    print("❌ Storefront не найден!")
    sys.exit(1)

# Проверяем несколько товаров
print("\nПроверка товаров...")
response = client._request("GET", "/api/product", params={"limit": 5})
products = response.get("data", []) if isinstance(response, dict) else []

for product in products:
    product_id = product.get("id")
    
    # Получаем visibilities
    try:
        vis_response = client._request("GET", f"/api/product/{product_id}/visibilities")
        vis_data = vis_response.get("data", []) if isinstance(vis_response, dict) else []
        
        # Получаем детали товара
        detail = client._request("GET", f"/api/product/{product_id}")
        detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
        attrs = detail_data.get("attributes", {})
        product_number = attrs.get("productNumber", "N/A")
        name = attrs.get("name", "N/A")[:50]
        
        # Ищем storefront visibility
        storefront_vis = None
        for vis_item in vis_data:
            vis_attrs = vis_item.get("attributes", {})
            if vis_attrs.get("salesChannelId") == STOREFRONT_SALES_CHANNEL_ID:
                storefront_vis = vis_attrs
                break
        
        if storefront_vis:
            category_id = storefront_vis.get("categoryId")
            if category_id:
                # Получаем название категории
                try:
                    cat_response = client._request("GET", f"/api/category/{category_id}")
                    cat_data = cat_response.get("data", {}) if isinstance(cat_response, dict) else {}
                    cat_attrs = cat_data.get("attributes", {})
                    cat_name = cat_attrs.get("name", "N/A")
                    print(f"\n✅ {product_number}: {name}...")
                    print(f"   mainCategory: {cat_name} (ID: {category_id[:16]}...)")
                except Exception:
                    print(f"\n✅ {product_number}: {name}...")
                    print(f"   mainCategory: ID {category_id[:16]}... (название не получено)")
            else:
                print(f"\n⚠️ {product_number}: {name}...")
                print(f"   mainCategory: НЕ УСТАНОВЛЕН")
        else:
            print(f"\n⚠️ {product_number}: {name}...")
            print(f"   Storefront visibility: НЕ НАЙДЕНА")
            
    except Exception as e:
        print(f"\n❌ Ошибка проверки товара: {e}")

print("\n" + "=" * 60)
print("ПРОВЕРКА ЗАВЕРШЕНА")
print("=" * 60)









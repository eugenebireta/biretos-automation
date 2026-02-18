"""Тест обновления visibility с categoryId"""
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
print("ТЕСТ ОБНОВЛЕНИЯ VISIBILITY С categoryId")
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
                print(f"Storefront Sales Channel: {sc_id}")
                break
    except Exception:
        continue

if not STOREFRONT_SALES_CHANNEL_ID:
    print("❌ Storefront не найден!")
    sys.exit(1)

# Получаем товар
response = client._request("GET", "/api/product", params={"limit": 1})
products = response.get("data", []) if isinstance(response, dict) else []

if products:
    product_id = products[0].get("id")
    
    # Получаем детали товара
    detail = client._request("GET", f"/api/product/{product_id}")
    detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
    attrs = detail_data.get("attributes", {})
    
    print(f"\nТовар: {attrs.get('productNumber', 'N/A')}")
    
    # Получаем visibilities
    existing_visibilities = attrs.get("visibilities", [])
    print(f"Visibilities из attributes: {len(existing_visibilities)}")
    
    if existing_visibilities:
        for vis in existing_visibilities:
            if isinstance(vis, dict):
                print(f"  - salesChannelId: {vis.get('salesChannelId', 'N/A')}")
                print(f"    visibility: {vis.get('visibility', 'N/A')}")
                print(f"    categoryId: {vis.get('categoryId', 'N/A')}")
    
    # Пробуем получить через relationships
    relationships = detail_data.get("relationships", {})
    vis_rel = relationships.get("visibilities", {})
    vis_data = vis_rel.get("data", []) if isinstance(vis_rel, dict) else []
    print(f"\nVisibilities из relationships: {len(vis_data)}")
    
    # Тест обновления
    main_category_id = "67c46b54a5944429ab54e64707dd6418"  # Пример из CSV
    print(f"\nТест обновления с mainCategoryId: {main_category_id}")
    
    # Формируем payload
    storefront_visibility = None
    other_visibilities = []
    
    for vis in existing_visibilities:
        if isinstance(vis, dict):
            vis_sc_id = vis.get("salesChannelId")
            if vis_sc_id == STOREFRONT_SALES_CHANNEL_ID:
                storefront_visibility = vis
            else:
                other_visibilities.append(vis)
    
    if storefront_visibility:
        current_category_id = storefront_visibility.get("categoryId")
        if current_category_id != main_category_id:
            visibility_level = storefront_visibility.get("visibility", 30)
            storefront_visibility = {
                "salesChannelId": STOREFRONT_SALES_CHANNEL_ID,
                "visibility": visibility_level,
                "categoryId": main_category_id
            }
            print(f"  Обновление visibility: categoryId {current_category_id} -> {main_category_id}")
        else:
            print(f"  categoryId уже правильный")
            storefront_visibility = None
    else:
        storefront_visibility = {
            "salesChannelId": STOREFRONT_SALES_CHANNEL_ID,
            "visibility": 30,
            "categoryId": main_category_id
        }
        print(f"  Создание новой visibility")
    
    if storefront_visibility:
        all_visibilities = other_visibilities + [storefront_visibility]
        payload = {
            "id": product_id,
            "visibilities": all_visibilities
        }
        print(f"\nPayload для обновления:")
        print(f"  visibilities: {len(all_visibilities)}")
        for vis in all_visibilities:
            print(f"    - salesChannelId: {vis.get('salesChannelId', 'N/A')[:16]}...")
            print(f"      categoryId: {vis.get('categoryId', 'N/A')[:16] if vis.get('categoryId') else 'N/A'}...")
        
        # НЕ выполняем реальное обновление в тесте
        print(f"\n✅ Payload сформирован корректно (обновление не выполнено)")

print("=" * 60)









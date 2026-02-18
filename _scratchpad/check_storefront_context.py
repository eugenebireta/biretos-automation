"""
Проверка storefront-контекста для генерации thumbnails
"""
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
print("ПРОВЕРКА STOREFRONT-КОНТЕКСТА")
print("=" * 60)

# 1. Проверка Sales Channels
print("\n1. Проверка Sales Channels...")
try:
    response = client._request("GET", "/api/sales-channel")
    sales_channels = response.get("data", []) if isinstance(response, dict) else []
    
    storefront_channels = []
    for sc in sales_channels:
        attrs = sc.get("attributes", {})
        sc_type = attrs.get("typeId", "")
        
        # Получаем тип Sales Channel
        type_response = client._request("GET", f"/api/sales-channel-type/{sc_type}")
        type_data = type_response.get("data", {}) if isinstance(type_response, dict) else {}
        type_attrs = type_data.get("attributes", {})
        type_name = type_attrs.get("name", "")
        
        if "storefront" in type_name.lower() or "store" in type_name.lower():
            storefront_channels.append({
                "id": sc.get("id"),
                "name": attrs.get("name", "N/A"),
                "type": type_name,
                "active": attrs.get("active", False),
                "domains": []
            })
    
    print(f"   Найдено Storefront Sales Channels: {len(storefront_channels)}")
    
    if not storefront_channels:
        print("   [ERROR] Нет активных Storefront Sales Channels!")
    else:
        for sc in storefront_channels:
            print(f"\n   Sales Channel: {sc['name']}")
            print(f"     ID: {sc['id']}")
            print(f"     Type: {sc['type']}")
            print(f"     Active: {sc['active']}")
            
            # Проверяем домены
            sc_id = sc['id']
            domains_response = client._request("GET", "/api/sales-channel-domain", params={
                "filter[salesChannelId]": sc_id
            })
            domains = domains_response.get("data", []) if isinstance(domains_response, dict) else []
            
            print(f"     Domains: {len(domains)}")
            for domain in domains:
                domain_attrs = domain.get("attributes", {})
                print(f"       - {domain_attrs.get('url', 'N/A')}")
                sc['domains'].append(domain_attrs.get('url', ''))
            
            # Проверяем тему
            theme_response = client._request("GET", f"/api/sales-channel/{sc_id}")
            theme_data = theme_response.get("data", {}) if isinstance(theme_response, dict) else {}
            theme_attrs = theme_data.get("attributes", {})
            theme_id = theme_attrs.get("themeId")
            
            if theme_id:
                theme_detail = client._request("GET", f"/api/theme/{theme_id}")
                theme_detail_data = theme_detail.get("data", {}) if isinstance(theme_detail, dict) else {}
                theme_detail_attrs = theme_detail_data.get("attributes", {})
                print(f"     Theme: {theme_detail_attrs.get('name', 'N/A')}")
            else:
                print(f"     Theme: НЕ НАЗНАЧЕНА!")
            
            # Проверяем доступность товаров
            products_response = client._request("GET", "/api/product", params={
                "filter[visibilities.salesChannelId]": sc_id,
                "limit": 5
            })
            products = products_response.get("data", []) if isinstance(products_response, dict) else []
            print(f"     Products visible: {len(products)}")
            
except Exception as e:
    print(f"   [ERROR] Ошибка проверки Sales Channels: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)









"""
Проверка связей медиа с товарами через product-media
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
print("ПРОВЕРКА СВЯЗЕЙ МЕДИА С ТОВАРАМИ")
print("=" * 60)

# Получаем товар
response = client._request("GET", "/api/product", params={"limit": 1})
products = response.get("data", []) if isinstance(response, dict) else []

if products:
    product_id = products[0].get("id")
    
    # Получаем товар с включением медиа
    print(f"\n1. Получение товара {product_id} с медиа...")
    try:
        detail = client._request("GET", f"/api/product/{product_id}", params={
            "associations[media][]": "media",
            "associations[cover][]": "cover"
        })
        detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
        attrs = detail_data.get("attributes", {})
        
        print(f"   Cover ID: {attrs.get('coverId', 'НЕТ')}")
        
        # Проверяем relationships
        relationships = detail_data.get("relationships", {})
        print(f"\n2. Relationships:")
        for rel_name, rel_data in relationships.items():
            if rel_data and isinstance(rel_data, dict):
                rel_items = rel_data.get("data", [])
                count = len(rel_items) if rel_items else 0
                print(f"   {rel_name}: {count}")
                if rel_name == "media" and rel_items:
                    print(f"     Первое медиа: {rel_items[0]}")
            else:
                print(f"   {rel_name}: None или не dict")
        
        # Пробуем получить медиа через product-media endpoint
        print(f"\n3. Проверка через product-media...")
        try:
            # Ищем product-media по product_id
            pm_response = client._request("GET", "/api/product-media", params={
                "filter[productId]": product_id
            })
            pm_data = pm_response.get("data", []) if isinstance(pm_response, dict) else []
            print(f"   Product-media записей: {len(pm_data)}")
            
            if pm_data:
                for pm in pm_data[:3]:
                    pm_attrs = pm.get("attributes", {})
                    print(f"     - Media ID: {pm_attrs.get('mediaId', 'N/A')}")
                    print(f"       Position: {pm_attrs.get('position', 'N/A')}")
            else:
                print(f"   ⚠ ПРОБЛЕМА: Нет product-media записей!")
                print(f"   Это объясняет, почему медиа не отображаются в relationships!")
                
        except Exception as e:
            print(f"   Ошибка: {str(e)[:100]}")
            
    except Exception as e:
        print(f"Ошибка: {e}")

print("\n" + "=" * 60)


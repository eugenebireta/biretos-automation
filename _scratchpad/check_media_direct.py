"""
Проверка медиа напрямую через coverId
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
print("ПРОВЕРКА МЕДИА ЧЕРЕЗ COVERID")
print("=" * 60)

# Получаем товары
response = client._request("GET", "/api/product", params={"limit": 5})
products = response.get("data", []) if isinstance(response, dict) else []

for idx, product in enumerate(products, 1):
    product_id = product.get("id")
    
    try:
        detail = client._request("GET", f"/api/product/{product_id}")
        detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
        attrs = detail_data.get("attributes", {})
        
        cover_id = attrs.get("coverId")
        product_number = attrs.get("productNumber", "N/A")
        
        print(f"\n{idx}. {product_number}")
        print(f"   Cover ID: {cover_id if cover_id else 'НЕТ'}")
        
        if cover_id:
            # Проверяем медиа напрямую
            try:
                media_detail = client._request("GET", f"/api/media/{cover_id}")
                media_detail_data = media_detail.get("data", {}) if isinstance(media_detail, dict) else {}
                media_attrs = media_detail_data.get("attributes", {})
                
                url = media_attrs.get("url", "")
                file_name = media_attrs.get("fileName", "")
                thumbnails = media_attrs.get("thumbnails", [])
                
                print(f"   Медиа найдено:")
                print(f"     - URL: {url[:80] if url else 'N/A'}...")
                print(f"     - File: {file_name if file_name else 'N/A'}")
                print(f"     - Thumbnails: {len(thumbnails)}")
                
                if not thumbnails:
                    print(f"     ⚠ ПРОБЛЕМА: Нет thumbnails!")
                else:
                    print(f"     ✓ Thumbnails есть")
                    for thumb in thumbnails[:2]:
                        print(f"       - {thumb.get('url', 'N/A')[:60]}...")
                        
            except Exception as e:
                print(f"   ⚠ Ошибка получения медиа: {str(e)[:100]}")
        else:
            print(f"   ⚠ Нет coverId")
            
    except Exception as e:
        print(f"{idx}. Ошибка: {str(e)[:100]}")

print("\n" + "=" * 60)









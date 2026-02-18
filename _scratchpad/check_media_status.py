"""
Проверка статуса медиа у товаров
"""
import sys
import json
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
print("ПРОВЕРКА СТАТУСА МЕДИА У ТОВАРОВ")
print("=" * 60)

# Получаем товары
print("\n1. Получение товаров...")
response = client._request("GET", "/api/product", params={"limit": 20})
products = response.get("data", []) if isinstance(response, dict) else []
print(f"Найдено товаров: {len(products)}")

# Проверяем каждый товар
print("\n2. Детальная проверка медиа:")
print("-" * 60)

products_without_media = []
products_without_cover = []
products_without_thumbnails = []

for idx, product in enumerate(products, 1):
    product_id = product.get("id")
    product_number = product.get("productNumber", "N/A")
    
    try:
        # Получаем детали товара
        detail = client._request("GET", f"/api/product/{product_id}")
        detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
        attrs = detail_data.get("attributes", {})
        
        # Проверяем cover
        cover_id = attrs.get("coverId")
        
        # Проверяем медиа через relationships
        relationships = detail_data.get("relationships", {})
        media_rel = relationships.get("media", {})
        media_data = media_rel.get("data", [])
        
        print(f"\n{idx}. {product_number}")
        print(f"   Cover ID: {cover_id if cover_id else 'НЕТ'}")
        print(f"   Медиа: {len(media_data)} файлов")
        
        if not cover_id:
            products_without_cover.append(product_number)
        
        if not media_data:
            products_without_media.append(product_number)
            print(f"   ⚠ ПРОБЛЕМА: Нет медиа!")
        else:
            # Проверяем первое медиа на наличие thumbnails
            first_media = media_data[0] if isinstance(media_data, list) else {}
            media_id = first_media.get("id")
            
            if media_id:
                try:
                    media_detail = client._request("GET", f"/api/media/{media_id}")
                    media_detail_data = media_detail.get("data", {}) if isinstance(media_detail, dict) else {}
                    media_attrs_detail = media_detail_data.get("attributes", {})
                    
                    thumbnails = media_attrs_detail.get("thumbnails", [])
                    url = media_attrs_detail.get("url", "")
                    
                    print(f"   Первое медиа: {media_id[:16]}...")
                    print(f"   URL: {url[:60] if url else 'N/A'}...")
                    print(f"   Thumbnails: {len(thumbnails)}")
                    
                    if not thumbnails:
                        products_without_thumbnails.append(product_number)
                        print(f"   ⚠ ПРОБЛЕМА: Нет thumbnails!")
                    else:
                        print(f"   ✓ Thumbnails есть: {thumbnails[0].get('url', 'N/A')[:50] if thumbnails else 'N/A'}...")
                        
                except Exception as e:
                    print(f"   ⚠ Ошибка получения деталей медиа: {str(e)[:100]}")
            
    except Exception as e:
        print(f"{idx}. Ошибка проверки {product_number}: {str(e)[:100]}")

print("\n" + "=" * 60)
print("ИТОГИ ПРОВЕРКИ")
print("=" * 60)
print(f"Товаров без медиа: {len(products_without_media)}")
if products_without_media:
    print(f"  Примеры: {', '.join(products_without_media[:5])}")
print(f"Товаров без cover: {len(products_without_cover)}")
if products_without_cover:
    print(f"  Примеры: {', '.join(products_without_cover[:5])}")
print(f"Товаров без thumbnails: {len(products_without_thumbnails)}")
if products_without_thumbnails:
    print(f"  Примеры: {', '.join(products_without_thumbnails[:5])}")

print("\n" + "=" * 60)









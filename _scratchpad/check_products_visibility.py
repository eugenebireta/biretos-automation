"""
Проверка видимости товаров на фронтенде и наличия фото
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
print("ПРОВЕРКА ВИДИМОСТИ ТОВАРОВ И ФОТО")
print("=" * 60)

# Проверяем несколько товаров
test_numbers = ["498271735", "498271898", "498271938", "498272057", "498272105"]

print(f"\nПроверка товаров:")
print("-" * 60)

for product_number in test_numbers:
    try:
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [{"field": "productNumber", "type": "equals", "value": product_number}],
                "includes": {
                    "product": [
                        "id",
                        "productNumber",
                        "name",
                        "active",
                        "visibilities",
                        "cover",
                        "media"
                    ]
                },
                "limit": 1,
            },
        )
        
        if response.get("total") and response.get("data"):
            product = response["data"][0]
            product_id = product.get("id")
            
            # Получаем детали
            detail = client._request("GET", f"/api/product/{product_id}")
            detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
            attrs = detail_data.get("attributes", {})
            
            print(f"\n{product_number}:")
            print(f"  ID: {product_id}")
            print(f"  Название: {attrs.get('name', 'N/A')[:50]}...")
            print(f"  Активен: {attrs.get('active', 'N/A')}")
            
            # Проверяем видимость (visibilities)
            visibilities = attrs.get("visibilities", [])
            if visibilities:
                print(f"  Видимость (visibilities): {len(visibilities)} записей")
                for vis in visibilities[:3]:  # Показываем первые 3
                    if isinstance(vis, dict):
                        print(f"    - Sales Channel ID: {vis.get('salesChannelId')}")
            else:
                print(f"  ⚠ НЕТ видимости (visibilities) - товар не привязан к Sales Channel!")
            
            # Проверяем фото (cover и media)
            cover = attrs.get("cover", {})
            media = attrs.get("media", [])
            
            if cover:
                print(f"  Обложка (cover): есть")
                if isinstance(cover, dict):
                    media_id = cover.get("id")
                    print(f"    Media ID: {media_id}")
            else:
                print(f"  ⚠ НЕТ обложки (cover)")
            
            if media:
                print(f"  Медиа (media): {len(media)} файлов")
            else:
                print(f"  ⚠ НЕТ медиа (media)")
            
            # Проверяем категории
            categories = attrs.get("categories", [])
            if categories:
                print(f"  Категории: {len(categories)}")
            else:
                print(f"  ⚠ НЕТ категорий")
        else:
            print(f"{product_number}: не найден")
    except Exception as e:
        print(f"{product_number}: ошибка - {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 60)









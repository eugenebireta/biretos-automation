"""
Прямая проверка товаров через GET запрос
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
print("ПРОВЕРКА ТОВАРОВ ЧЕРЕЗ GET ЗАПРОС")
print("=" * 60)

# Получаем список товаров
print("\n1. Список товаров (первые 10):")
print("-" * 60)
try:
    response = client._request("GET", "/api/product", params={"limit": 10})
    products = response.get("data", []) if isinstance(response, dict) else []
    print(f"Найдено товаров: {len(products)}")
    
    for idx, product in enumerate(products, 1):
        product_id = product.get("id")
        product_number = product.get("productNumber", "N/A")
        
        try:
            detail = client._request("GET", f"/api/product/{product_id}")
            detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
            attrs = detail_data.get("attributes", {})
            
            name = attrs.get("name", "N/A")
            active = attrs.get("active", False)
            
            # Проверяем видимость
            visibilities = attrs.get("visibilities", [])
            
            # Проверяем фото
            cover = attrs.get("cover")
            media = attrs.get("media", [])
            
            # Проверяем категории
            categories = attrs.get("categories", [])
            
            print(f"\n{idx}. {product_number}")
            print(f"   Название: {name[:50]}...")
            print(f"   Активен: {active}")
            print(f"   Видимость (visibilities): {len(visibilities)} записей")
            if not visibilities:
                print(f"   ⚠ ПРОБЛЕМА: Нет привязки к Sales Channel!")
            
            print(f"   Обложка (cover): {'есть' if cover else 'НЕТ'}")
            print(f"   Медиа (media): {len(media)} файлов")
            if not cover and not media:
                print(f"   ⚠ ПРОБЛЕМА: Нет фото!")
            
            print(f"   Категории: {len(categories)}")
            if not categories:
                print(f"   ⚠ ПРОБЛЕМА: Нет категорий!")
                
        except Exception as e:
            print(f"{idx}. Ошибка получения деталей товара {product_id}: {e}")
except Exception as e:
    print(f"Ошибка получения списка товаров: {e}")
    import traceback
    traceback.print_exc()

# Получаем Sales Channels
print("\n2. Sales Channels для привязки:")
print("-" * 60)
try:
    sc_response = client._request("GET", "/api/sales-channel")
    sales_channels = sc_response.get("data", []) if isinstance(sc_response, dict) else []
    print(f"Найдено Sales Channels: {len(sales_channels)}")
    for sc in sales_channels:
        sc_id = sc.get("id")
        print(f"  - {sc_id}")
except Exception as e:
    print(f"Ошибка получения Sales Channels: {e}")

print("\n" + "=" * 60)









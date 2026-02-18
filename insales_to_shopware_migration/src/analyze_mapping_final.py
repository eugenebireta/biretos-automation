"""
Финальный анализ: проверка реальных товаров в Shopware и их сопоставление.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"


def get_shopware_products_sample(client, limit=30):
    """Получает выборку товаров из Shopware"""
    try:
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "limit": limit,
                "includes": {"product": ["id", "productNumber", "name", "customFields"]}
            }
        )
        return response.get("data", [])
    except Exception as e:
        print(f"Ошибка: {e}")
        return []


def main():
    print("=" * 80)
    print("АНАЛИЗ РЕАЛЬНЫХ ТОВАРОВ В SHOPWARE")
    print("=" * 80)
    print()
    
    # Загружаем конфигурацию
    with CONFIG_PATH.open() as f:
        config = json.load(f)
    
    sw_config = config["shopware"]
    client = ShopwareClient(
        ShopwareConfig(
            sw_config["url"],
            sw_config["access_key_id"],
            sw_config["secret_access_key"]
        )
    )
    
    # Получаем товары
    products = get_shopware_products_sample(client, limit=30)
    print(f"Получено товаров из Shopware: {len(products)}")
    print()
    
    # Анализируем productNumber
    print("=" * 80)
    print("АНАЛИЗ PRODUCTNUMBER")
    print("=" * 80)
    print()
    
    with_number = []
    without_number = []
    
    for product in products:
        product_id = product.get("id")
        product_number = product.get("productNumber")
        product_name = product.get("name", {})
        if isinstance(product_name, dict):
            product_name = product_name.get("ru-RU") or str(product_name)
        else:
            product_name = str(product_name)
        
        custom_fields = product.get("customFields", {})
        
        if product_number:
            with_number.append({
                "id": product_id,
                "productNumber": product_number,
                "name": product_name,
                "customFields": custom_fields
            })
        else:
            without_number.append({
                "id": product_id,
                "name": product_name,
                "customFields": custom_fields
            })
    
    print(f"Товаров С productNumber: {len(with_number)}")
    print(f"Товаров БЕЗ productNumber: {len(without_number)}")
    print()
    
    # Примеры товаров с productNumber
    if with_number:
        print("Примеры товаров С productNumber:")
        for i, p in enumerate(with_number[:5], 1):
            print(f"\n{i}. ID: {p['id']}")
            print(f"   productNumber: {p['productNumber']}")
            print(f"   Название: {p['name'][:60]}...")
            if p['customFields']:
                print(f"   customFields: {json.dumps(p['customFields'], ensure_ascii=False)}")
    
    # Примеры товаров без productNumber
    if without_number:
        print("\n" + "=" * 80)
        print("Примеры товаров БЕЗ productNumber:")
        for i, p in enumerate(without_number[:5], 1):
            print(f"\n{i}. ID: {p['id']}")
            print(f"   Название: {p['name'][:60]}...")
            if p['customFields']:
                print(f"   customFields: {json.dumps(p['customFields'], ensure_ascii=False)}")
    
    # Выводы
    print()
    print("=" * 80)
    print("ВЫВОДЫ")
    print("=" * 80)
    print()
    
    if len(with_number) == 0:
        print("КРИТИЧЕСКАЯ ПРОБЛЕМА:")
        print("  В Shopware НЕТ товаров с productNumber!")
        print("  Это означает, что:")
        print("  1. Товары не были импортированы")
        print("  2. Или productNumber не был установлен при импорте")
        print()
        print("РЕКОМЕНДАЦИЯ:")
        print("  Невозможно восстановить price2 БЕЗ переимпорта товаров")
        print("  или установки productNumber для существующих товаров")
    elif len(with_number) < len(products) * 0.5:
        print("ПРОБЛЕМА:")
        print(f"  Только {len(with_number)}/{len(products)} товаров имеют productNumber")
        print()
        print("РЕКОМЕНДАЦИЯ:")
        print("  Использовать productNumber как основной ключ")
        print("  Для товаров без productNumber нужен fallback (customFields или ID)")
    else:
        print("OK:")
        print(f"  Большинство товаров ({len(with_number)}/{len(products)}) имеют productNumber")
        print()
        print("РЕКОМЕНДАЦИЯ:")
        print("  ОСНОВНОЙ КЛЮЧ: productNumber (SKU из InSales)")
        print("  - Поле InSales: variants[0].sku")
        print("  - Поле Shopware: product.productNumber")
        print()
        if len(without_number) > 0:
            print("  FALLBACK: customFields.insales_id или migration_map")
            print("  - Для товаров без productNumber")
    
    print()
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())




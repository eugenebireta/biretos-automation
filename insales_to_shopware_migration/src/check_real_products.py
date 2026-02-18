"""
Проверка реальных товаров в Shopware для поиска ключа сопоставления.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
MIGRATION_MAP_PATH = ROOT / "migration_map.json"

# Берем несколько ID из migration_map для проверки
TEST_INSALES_IDS = ["287629663", "287629664", "287629670", "287629671", "287629677"]


def main():
    print("=" * 80)
    print("ПРОВЕРКА РЕАЛЬНЫХ ТОВАРОВ В SHOPWARE")
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
    
    # Загружаем migration_map
    migration_map = {}
    if MIGRATION_MAP_PATH.exists():
        with MIGRATION_MAP_PATH.open() as f:
            migration_map = json.load(f)
    
    products_map = migration_map.get("products", {})
    print(f"В migration_map найдено {len(products_map)} товаров")
    print()
    
    # Проверяем несколько товаров из migration_map
    found_count = 0
    for insales_id in TEST_INSALES_IDS:
        shopware_id = products_map.get(insales_id)
        if not shopware_id:
            print(f"InSales ID {insales_id}: НЕТ в migration_map")
            continue
        
        print(f"InSales ID {insales_id} -> Shopware ID {shopware_id}")
        
        try:
            response = client._request("GET", f"/api/product/{shopware_id}")
            product_data = response.get("data", {}) if isinstance(response, dict) else {}
            
            if product_data:
                found_count += 1
                product_number = product_data.get("productNumber")
                product_name = product_data.get("name", {})
                if isinstance(product_name, dict):
                    product_name = product_name.get("ru-RU") or str(product_name)
                else:
                    product_name = str(product_name)
                
                custom_fields = product_data.get("customFields", {})
                
                print(f"  OK: Товар найден")
                print(f"  productNumber: {product_number}")
                print(f"  Название: {product_name[:60]}...")
                if custom_fields:
                    print(f"  customFields: {json.dumps(custom_fields, ensure_ascii=False)}")
                else:
                    print(f"  customFields: отсутствуют")
            else:
                print(f"  ERROR: Товар не найден в Shopware")
        except Exception as e:
            print(f"  ERROR: {str(e)[:100]}")
        
        print()
    
    # Получаем список реальных товаров из Shopware (первые 10)
    print("=" * 80)
    print("ПЕРВЫЕ 10 ТОВАРОВ ИЗ SHOPWARE")
    print("=" * 80)
    print()
    
    try:
        response = client._request("GET", "/api/product", params={"limit": 10})
        products = response.get("data", []) if isinstance(response, dict) else []
        
        for product in products:
            product_id = product.get("id")
            product_number = product.get("productNumber")
            product_name = product.get("name", {})
            if isinstance(product_name, dict):
                product_name = product_name.get("ru-RU") or str(product_name)
            else:
                product_name = str(product_name)
            
            custom_fields = product.get("customFields", {})
            
            print(f"ID: {product_id}")
            print(f"  productNumber: {product_number}")
            print(f"  Название: {product_name[:60]}...")
            if custom_fields:
                print(f"  customFields: {json.dumps(custom_fields, ensure_ascii=False)}")
            print()
    except Exception as e:
        print(f"ERROR: {e}")
    
    print("=" * 80)
    print(f"Найдено товаров по migration_map: {found_count}/{len(TEST_INSALES_IDS)}")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())




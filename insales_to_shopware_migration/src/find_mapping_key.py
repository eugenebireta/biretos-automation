"""
Финальный анализ ключа сопоставления товаров.
Проверяет все возможные варианты.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = ROOT / "insales_snapshot" / "products.ndjson"
CONFIG_PATH = ROOT / "config.json"
MIGRATION_MAP_PATH = ROOT / "migration_map.json"


def load_sample_insales_products(count=20):
    """Загружает выборку товаров из snapshot"""
    products = []
    if not SNAPSHOT_PATH.exists():
        return products
    
    with SNAPSHOT_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                product = json.loads(line)
                variants = product.get("variants", [])
                if variants and variants[0].get("sku"):
                    products.append(product)
                    if len(products) >= count:
                        break
            except json.JSONDecodeError:
                continue
    return products


def search_products_in_shopware(client, limit=100):
    """Получает товары из Shopware с productNumber"""
    try:
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [
                    {
                        "type": "range",
                        "field": "productNumber",
                        "parameters": {
                            "gte": "0"
                        }
                    }
                ],
                "limit": limit,
                "includes": {"product": ["id", "productNumber", "name", "customFields"]}
            }
        )
        return response.get("data", [])
    except Exception as e:
        print(f"Ошибка поиска товаров: {e}")
        return []


def main():
    print("=" * 80)
    print("АНАЛИЗ КЛЮЧА СОПОСТАВЛЕНИЯ ТОВАРОВ")
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
    print(f"В migration_map: {len(products_map)} товаров")
    print()
    
    # Получаем товары из Shopware с productNumber
    print("Поиск товаров в Shopware с productNumber...")
    shopware_products = search_products_in_shopware(client, limit=50)
    print(f"Найдено товаров с productNumber: {len(shopware_products)}")
    print()
    
    # Загружаем выборку из snapshot
    print("Загрузка выборки из snapshot...")
    insales_products = load_sample_insales_products(count=20)
    print(f"Загружено товаров из snapshot: {len(insales_products)}")
    print()
    
    # Анализ сопоставления
    print("=" * 80)
    print("АНАЛИЗ СОПОСТАВЛЕНИЯ")
    print("=" * 80)
    print()
    
    matches = {
        "by_productNumber": 0,
        "by_migration_map": 0,
        "by_customFields": 0,
        "not_found": 0
    }
    
    examples = []
    
    for insales_product in insales_products[:10]:
        insales_id = insales_product.get("id")
        variants = insales_product.get("variants", [])
        if not variants:
            continue
        
        sku = variants[0].get("sku")
        product_name = insales_product.get("title", "")
        
        print(f"InSales ID: {insales_id}, SKU: {sku}")
        print(f"  Название: {product_name[:60]}...")
        
        found = False
        
        # Метод 1: По productNumber (SKU)
        if sku:
            product_id = client.find_product_by_number(sku)
            if product_id:
                matches["by_productNumber"] += 1
                found = True
                print(f"  OK: Найден по productNumber")
                examples.append({
                    "method": "productNumber",
                    "insales_sku": sku,
                    "insales_id": insales_id,
                    "shopware_id": product_id
                })
        
        # Метод 2: По migration_map
        if not found and str(insales_id) in products_map:
            shopware_id = products_map[str(insales_id)]
            try:
                response = client._request("GET", f"/api/product/{shopware_id}")
                if response.get("data"):
                    matches["by_migration_map"] += 1
                    found = True
                    print(f"  OK: Найден по migration_map")
                    examples.append({
                        "method": "migration_map",
                        "insales_id": insales_id,
                        "shopware_id": shopware_id
                    })
            except:
                pass
        
        # Метод 3: По customFields
        if not found:
            # Проверяем товары из Shopware на наличие insales_id в customFields
            for sw_product in shopware_products:
                custom_fields = sw_product.get("customFields", {})
                if custom_fields and str(insales_id) in str(custom_fields.values()):
                    matches["by_customFields"] += 1
                    found = True
                    print(f"  OK: Найден по customFields")
                    break
        
        if not found:
            matches["not_found"] += 1
            print(f"  ERROR: Не найден")
        
        print()
    
    # Итоговый отчет
    print("=" * 80)
    print("ИТОГОВЫЙ ОТЧЕТ")
    print("=" * 80)
    print()
    print(f"Найдено по productNumber: {matches['by_productNumber']}")
    print(f"Найдено по migration_map: {matches['by_migration_map']}")
    print(f"Найдено по customFields: {matches['by_customFields']}")
    print(f"Не найдено: {matches['not_found']}")
    print()
    
    if examples:
        print("Примеры совпадений:")
        for i, ex in enumerate(examples[:5], 1):
            print(f"\n{i}. Метод: {ex['method']}")
            print(f"   InSales ID: {ex.get('insales_id')}")
            if 'insales_sku' in ex:
                print(f"   InSales SKU: {ex['insales_sku']}")
            print(f"   Shopware ID: {ex['shopware_id']}")
    
    # Рекомендация
    print()
    print("=" * 80)
    print("РЕКОМЕНДАЦИЯ")
    print("=" * 80)
    
    if matches["by_productNumber"] > 0:
        print("ОСНОВНОЙ КЛЮЧ: productNumber (SKU из InSales)")
        print("  - Поле InSales: variants[0].sku")
        print("  - Поле Shopware: product.productNumber")
        print("  - Надежность: ВЫСОКАЯ (если SKU уникальны)")
    elif matches["by_migration_map"] > 0:
        print("ОСНОВНОЙ КЛЮЧ: migration_map.products")
        print("  - Поле InSales: product.id")
        print("  - Поле Shopware: product.id (из migration_map)")
        print("  - Надежность: СРЕДНЯЯ (если товары не переимпортированы)")
    else:
        print("КРИТИЧЕСКАЯ ПРОБЛЕМА: Товары не найдены!")
        print("  Возможные причины:")
        print("  - Товары не были импортированы")
        print("  - Товары были удалены")
        print("  - Товары были переимпортированы с другими ID")
    
    print()
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())




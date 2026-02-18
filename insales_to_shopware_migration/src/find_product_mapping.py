"""
Поиск реального ключа сопоставления товаров InSales → Shopware.

Проверяет:
1. productNumber (SKU)
2. customFields (insales_id, external_id)
3. Название товара
4. ID из migration_map
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).parent))
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = ROOT / "insales_snapshot" / "products.ndjson"
CONFIG_PATH = ROOT / "config.json"
MIGRATION_MAP_PATH = ROOT / "migration_map.json"

# Тестовые SKU из snapshot
TEST_SKUS = ["500944170", "500944171", "500944177", "500944178", "500944203"]


def load_insales_product_by_sku(sku: str) -> Optional[Dict[str, Any]]:
    """Загружает товар из snapshot по SKU"""
    if not SNAPSHOT_PATH.exists():
        return None
    
    with SNAPSHOT_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                product = json.loads(line)
                variants = product.get("variants", [])
                if variants and variants[0].get("sku") == sku:
                    return product
            except json.JSONDecodeError:
                continue
    return None


def search_product_by_custom_field(
    client: ShopwareClient,
    field_name: str,
    field_value: str
) -> Optional[Dict[str, Any]]:
    """Ищет товар по customField"""
    try:
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [
                    {
                        "type": "equals",
                        "field": f"customFields.{field_name}",
                        "value": field_value
                    }
                ],
                "limit": 1
            }
        )
        if response.get("total") and response.get("data"):
            product_id = response["data"][0]["id"]
            return get_product_full_data(client, product_id)
    except Exception as e:
        print(f"  Ошибка поиска по customField.{field_name}: {e}")
    return None


def search_product_by_name(
    client: ShopwareClient,
    name: str
) -> Optional[Dict[str, Any]]:
    """Ищет товар по названию"""
    try:
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [
                    {
                        "type": "equals",
                        "field": "name",
                        "value": name
                    }
                ],
                "limit": 5
            }
        )
        if response.get("total") and response.get("data"):
            # Возвращаем первый результат
            product_id = response["data"][0]["id"]
            return get_product_full_data(client, product_id)
    except Exception as e:
        print(f"  Ошибка поиска по названию: {e}")
    return None


def get_product_full_data(client: ShopwareClient, product_id: str) -> Optional[Dict[str, Any]]:
    """Получает полные данные товара"""
    try:
        response = client._request("GET", f"/api/product/{product_id}")
        return response.get("data", {}) if isinstance(response, dict) else {}
    except Exception as e:
        print(f"  Ошибка получения товара {product_id}: {e}")
    return None


def analyze_product_mapping(
    client: ShopwareClient,
    insales_product: Dict[str, Any],
    migration_map: Dict[str, Any]
) -> Dict[str, Any]:
    """Анализирует все возможные способы сопоставления товара"""
    result = {
        "insales_id": insales_product.get("id"),
        "insales_sku": None,
        "insales_name": insales_product.get("title", ""),
        "found_by": [],
        "product_data": None
    }
    
    variants = insales_product.get("variants", [])
    if variants:
        result["insales_sku"] = variants[0].get("sku")
    
    # Метод 1: По productNumber (SKU)
    if result["insales_sku"]:
        product_id = client.find_product_by_number(result["insales_sku"])
        if product_id:
            result["found_by"].append("productNumber")
            result["product_data"] = get_product_full_data(client, product_id)
            return result
    
    # Метод 2: По customFields.insales_id
    insales_id_str = str(result["insales_id"])
    product_data = search_product_by_custom_field(client, "insales_id", insales_id_str)
    if product_data:
        result["found_by"].append("customFields.insales_id")
        result["product_data"] = product_data
        return result
    
    # Метод 3: По customFields.external_id
    product_data = search_product_by_custom_field(client, "external_id", insales_id_str)
    if product_data:
        result["found_by"].append("customFields.external_id")
        result["product_data"] = product_data
        return result
    
    # Метод 4: По migration_map (если есть)
    products_map = migration_map.get("products", {})
    if str(result["insales_id"]) in products_map:
        shopware_id = products_map[str(result["insales_id"])]
        product_data = get_product_full_data(client, shopware_id)
        if product_data:
            result["found_by"].append("migration_map.products")
            result["product_data"] = product_data
            return result
    
    # Метод 5: По названию (fallback)
    product_data = search_product_by_name(client, result["insales_name"])
    if product_data:
        result["found_by"].append("name")
        result["product_data"] = product_data
        return result
    
    return result


def main():
    print("=" * 80)
    print("ПОИСК КЛЮЧА СОПОСТАВЛЕНИЯ ТОВАРОВ InSales -> Shopware")
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
    
    print(f"Тестовые SKU: {', '.join(TEST_SKUS)}")
    print()
    
    results = []
    for sku in TEST_SKUS:
        print(f"Проверка SKU: {sku}")
        
        # Загружаем товар из snapshot
        insales_product = load_insales_product_by_sku(sku)
        if not insales_product:
            print(f"  ERROR: Товар не найден в snapshot")
            continue
        
        insales_id = insales_product.get("id")
        insales_name = insales_product.get("title", "Unknown")
        print(f"  InSales ID: {insales_id}")
        print(f"  Название: {insales_name[:60]}...")
        
        # Анализируем сопоставление
        mapping_result = analyze_product_mapping(client, insales_product, migration_map)
        
        if mapping_result["found_by"]:
            print(f"  OK: Найден в Shopware через: {', '.join(mapping_result['found_by'])}")
            product_data = mapping_result["product_data"]
            if product_data:
                shopware_id = product_data.get("id")
                shopware_number = product_data.get("productNumber")
                shopware_name = product_data.get("name", {}).get("ru-RU") or str(product_data.get("name", ""))
                custom_fields = product_data.get("customFields", {})
                
                print(f"    Shopware ID: {shopware_id}")
                print(f"    Shopware productNumber: {shopware_number}")
                print(f"    Shopware название: {shopware_name[:60]}...")
                if custom_fields:
                    print(f"    CustomFields: {json.dumps(custom_fields, ensure_ascii=False)}")
        else:
            print(f"  ERROR: Товар не найден в Shopware")
        
        results.append(mapping_result)
        print()
    
    # Итоговая статистика
    print("=" * 80)
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 80)
    
    found_count = sum(1 for r in results if r["found_by"])
    print(f"Найдено товаров: {found_count}/{len(results)}")
    
    # Группировка по методам поиска
    methods = {}
    for r in results:
        for method in r["found_by"]:
            methods[method] = methods.get(method, 0) + 1
    
    if methods:
        print("\nМетоды сопоставления:")
        for method, count in sorted(methods.items(), key=lambda x: -x[1]):
            print(f"  {method}: {count} товаров")
    
    # Примеры совпадений
    print("\nПримеры совпадений:")
    for i, r in enumerate(results[:5], 1):
        if r["found_by"]:
            print(f"\n{i}. SKU: {r['insales_sku']}")
            print(f"   InSales ID: {r['insales_id']}")
            print(f"   Найдено через: {', '.join(r['found_by'])}")
            if r["product_data"]:
                print(f"   Shopware productNumber: {r['product_data'].get('productNumber')}")
                print(f"   Shopware ID: {r['product_data'].get('id')}")
    
    print("\n" + "=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


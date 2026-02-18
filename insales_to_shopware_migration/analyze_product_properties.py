"""
Анализ характеристик товара из InSales snapshot и сравнение с Shopware
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from clients import ShopwareClient, ShopwareConfig

# Загружаем конфигурацию
config = json.load(open(Path(__file__).parent / "config.json", encoding="utf-8"))
shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

# Товар для анализа
product_sku = "500944170"

print("=" * 80)
print("АНАЛИЗ ХАРАКТЕРИСТИК ТОВАРА")
print("=" * 80)
print(f"SKU: {product_sku}\n")

# 1. Получаем характеристики из snapshot
print("1. ХАРАКТЕРИСТИКИ В INSALES (из snapshot):")
print("-" * 80)
snapshot_file = Path(__file__).parent / "insales_snapshot" / "products.ndjson"
insales_properties = []

if snapshot_file.exists():
    with open(snapshot_file, encoding="utf-8") as f:
        for line in f:
            product = json.loads(line)
            # Проверяем по SKU из вариантов
            variants = product.get("variants", [])
            product_sku_found = False
            for variant in variants:
                if variant.get("sku") == product_sku:
                    product_sku_found = True
                    break
            
            if product_sku_found or str(product.get("id")) == product_sku:
                # В NDJSON характеристики хранятся в поле "characteristics"
                insales_properties = product.get("characteristics", []) or product.get("properties", [])
                print(f"Товар: {product.get('title')}")
                print(f"ID товара: {product.get('id')}")
                print(f"Всего характеристик в InSales: {len(insales_properties)}\n")
                
                for i, prop in enumerate(insales_properties, 1):
                    prop_id = prop.get("property_id") or prop.get("id")
                    prop_title = prop.get("title") or prop.get("name") or prop.get("permalink") or "Без названия"
                    prop_value = prop.get("value") or prop.get("title") or ""
                    print(f"  {i}. {prop_title}: {prop_value} (property_id: {prop_id})")
                break
else:
    print("Файл snapshot не найден")

print("\n" + "=" * 80)

# 2. Получаем характеристики из Shopware
print("2. ХАРАКТЕРИСТИКИ В SHOPWARE:")
print("-" * 80)

# Ищем товар по SKU
try:
    response = client._request(
        "POST",
        "/api/search/product",
        json={
            "filter": [{"field": "productNumber", "type": "equals", "value": product_sku}],
            "includes": {"product": ["id", "productNumber", "name", "properties"]},
            "limit": 1,
        },
    )
    
    if response.get("total") and response.get("data"):
        product_id = response["data"][0].get("id")
        
        # Получаем полную информацию о товаре
        full_product = client._request("GET", f"/api/product/{product_id}")
        if full_product and "data" in full_product:
            product_data = full_product["data"]
            shopware_properties = product_data.get("properties", [])
            
            print(f"Товар: {product_data.get('name')}")
            print(f"Всего характеристик в Shopware: {len(shopware_properties)}\n")
            
            # Получаем детали каждой характеристики
            for i, prop in enumerate(shopware_properties, 1):
                prop_id = prop.get("id")
                # Получаем детали property option
                try:
                    prop_option = client._request("GET", f"/api/property-group-option/{prop_id}")
                    if prop_option and "data" in prop_option:
                        option_data = prop_option["data"]
                        group_id = option_data.get("groupId")
                        option_name = option_data.get("name") or "Без названия"
                        
                        # Получаем информацию о группе
                        if group_id:
                            group = client._request("GET", f"/api/property-group/{group_id}")
                            if group and "data" in group:
                                group_name = group["data"].get("name") or "Без названия"
                                print(f"  {i}. {group_name}: {option_name} (option_id: {prop_id}, group_id: {group_id})")
                            else:
                                print(f"  {i}. {option_name} (option_id: {prop_id}, group_id: {group_id})")
                        else:
                            print(f"  {i}. {option_name} (option_id: {prop_id})")
                    else:
                        print(f"  {i}. [Не удалось получить детали] (option_id: {prop_id})")
                except Exception as e:
                    print(f"  {i}. [Ошибка получения деталей] (option_id: {prop_id}): {e}")
        else:
            print("Товар не найден в Shopware")
    else:
        print("Товар не найден в Shopware")
except Exception as e:
    print(f"Ошибка при поиске товара: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)

# 3. Сравнение
print("3. СРАВНЕНИЕ:")
print("-" * 80)

insales_prop_titles = {prop.get("title") or prop.get("name") or "Без названия": prop.get("value") or "" 
                       for prop in insales_properties}

# Получаем названия характеристик из Shopware
shopware_prop_titles = set()
if response.get("total") and response.get("data"):
    product_id = response["data"][0].get("id")
    full_product = client._request("GET", f"/api/product/{product_id}")
    if full_product and "data" in full_product:
        shopware_properties = full_product["data"].get("properties", [])
        for prop in shopware_properties:
            try:
                prop_option = client._request("GET", f"/api/property-group-option/{prop.get('id')}")
                if prop_option and "data" in prop_option:
                    option_data = prop_option["data"]
                    group_id = option_data.get("groupId")
                    if group_id:
                        group = client._request("GET", f"/api/property-group/{group_id}")
                        if group and "data" in group:
                            group_name = group["data"].get("name") or "Без названия"
                            shopware_prop_titles.add(group_name)
            except:
                pass

missing_in_shopware = insales_prop_titles.keys() - shopware_prop_titles
extra_in_shopware = shopware_prop_titles - insales_prop_titles.keys()
common = insales_prop_titles.keys() & shopware_prop_titles

print(f"Характеристик в InSales: {len(insales_prop_titles)}")
print(f"Характеристик в Shopware: {len(shopware_prop_titles)}")
print(f"Общих: {len(common)}")
print(f"Отсутствуют в Shopware: {len(missing_in_shopware)}")
print(f"Лишние в Shopware: {len(extra_in_shopware)}")

if missing_in_shopware:
    print("\n[ОТСУТСТВУЮТ В SHOPWARE]:")
    for prop_title in sorted(missing_in_shopware):
        print(f"  - {prop_title}: {insales_prop_titles[prop_title]}")

if extra_in_shopware:
    print("\n➕ ЛИШНИЕ В SHOPWARE:")
    for prop_title in sorted(extra_in_shopware):
        print(f"  - {prop_title}")

if common:
    print("\n[ОБЩИЕ ХАРАКТЕРИСТИКИ]:")
    for prop_title in sorted(common):
        print(f"  - {prop_title}")

print("\n" + "=" * 80)


"""
Финальная проверка импорта SKU (productNumber) и штрих-кода
на тестовых 10 товарах
"""
import json
from pathlib import Path
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
SNAPSHOT_PATH = ROOT / "insales_snapshot" / "products.ndjson"

# Тестовые SKU
TEST_SKUS = ["500944170", "500944171", "500944177", "500944178", "500944203", 
             "500944207", "500944219", "500944220", "500944221", "500944222"]

def load_insales_data():
    """Загружает данные из InSales snapshot"""
    insales_map = {}
    
    if not SNAPSHOT_PATH.exists():
        return insales_map
    
    with SNAPSHOT_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                product = json.loads(line)
                variants = product.get("variants", [])
                if variants:
                    variant = variants[0]
                    sku = str(variant.get("sku", ""))
                    if sku in TEST_SKUS:
                        insales_map[sku] = {
                            "sku": sku,
                            "barcode": variant.get("barcode"),
                            "ean": variant.get("ean"),
                            "product_id": product.get("id"),
                            "title": product.get("title", "")[:50]
                        }
            except json.JSONDecodeError:
                continue
    
    return insales_map

def main():
    print("=" * 100)
    print("ФИНАЛЬНАЯ ПРОВЕРКА ИМПОРТА SKU (productNumber) И ШТРИХ-КОДА")
    print("=" * 100)
    print()
    
    # Загружаем конфигурацию
    with CONFIG_PATH.open() as f:
        config = json.load(f)
    
    client = ShopwareClient(
        ShopwareConfig(
            config["shopware"]["url"],
            config["shopware"]["access_key_id"],
            config["shopware"]["secret_access_key"]
        )
    )
    
    # Загружаем данные из InSales snapshot
    print("Загрузка данных из InSales snapshot...")
    insales_data = load_insales_data()
    print(f"Загружено {len(insales_data)} товаров из snapshot")
    print()
    
    # Получаем последние 20 товаров из Shopware
    print("Получение последних товаров из Shopware...")
    search_response = client._request(
        "POST",
        "/api/search/product",
        json={
            "limit": 20,
            "sort": [{"field": "createdAt", "order": "DESC"}],
            "includes": {"product": ["id", "productNumber", "name"]},
        },
    )
    
    products_to_check = []
    for p in search_response.get("data", [])[:20]:
        pid = p.get("id")
        # Получаем полные данные через GET API
        try:
            full_data = client._request("GET", f"/api/product/{pid}")
            data = full_data.get("data", {})
            attrs = data.get("attributes", {})
            pn = attrs.get("productNumber") or data.get("productNumber")
            
            # Проверяем, является ли это тестовым товаром
            if pn and pn in TEST_SKUS:
                products_to_check.append({
                    "id": pid,
                    "data": data,
                    "attributes": attrs
                })
                if len(products_to_check) >= 10:
                    break
        except Exception as e:
            print(f"Ошибка получения товара {pid}: {e}")
            continue
    
    print(f"Найдено {len(products_to_check)} тестовых товаров для проверки")
    print()
    
    # Выводим таблицу результатов
    print("=" * 100)
    print("ТАБЛИЦА ПРОВЕРКИ ТОВАРОВ")
    print("=" * 100)
    print()
    
    print(f"{'ID':<40} {'Name':<40} {'productNumber':<15} {'attributes.productNumber':<25} {'EAN/Barcode':<20} {'CustomFields':<30}")
    print("-" * 100)
    
    results = []
    
    for product_info in products_to_check:
        pid = product_info["id"]
        data = product_info["data"]
        attrs = product_info["attributes"]
        
        # Извлекаем данные
        name = attrs.get("name", "")[:40] or data.get("name", "")[:40]
        product_number_root = data.get("productNumber")
        product_number_attrs = attrs.get("productNumber")
        product_number = product_number_attrs or product_number_root
        
        # EAN/Barcode
        ean = attrs.get("ean") or data.get("ean")
        barcode = attrs.get("barcode") or data.get("barcode")
        ean_barcode = ean or barcode or "N/A"
        
        # CustomFields
        custom_fields = attrs.get("customFields") or data.get("customFields") or {}
        custom_fields_str = json.dumps(custom_fields)[:30] if custom_fields else "N/A"
        
        # Сопоставление с InSales
        insales_info = insales_data.get(product_number, {})
        insales_sku = insales_info.get("sku", "N/A")
        insales_barcode = insales_info.get("barcode") or insales_info.get("ean")
        
        # Проверка productNumber
        productnumber_ok = (product_number == insales_sku) if insales_sku != "N/A" else "?"
        
        # Проверка barcode
        barcode_in_insales = "есть" if insales_barcode else "нет"
        barcode_imported = "импортирован" if (ean or barcode or custom_fields.get("internal_barcode")) else "не импортирован"
        
        results.append({
            "id": pid,
            "name": name,
            "product_number": product_number,
            "product_number_root": product_number_root,
            "product_number_attrs": product_number_attrs,
            "ean_barcode": ean_barcode,
            "custom_fields": custom_fields,
            "insales_sku": insales_sku,
            "insales_barcode": insales_barcode,
            "productnumber_ok": productnumber_ok,
            "barcode_in_insales": barcode_in_insales,
            "barcode_imported": barcode_imported
        })
        
        print(f"{pid:<40} {name:<40} {str(product_number_root):<15} {str(product_number_attrs):<25} {str(ean_barcode):<20} {custom_fields_str:<30}")
    
    print()
    print("=" * 100)
    print("СОПОСТАВЛЕНИЕ С INSALES SNAPSHOT")
    print("=" * 100)
    print()
    
    print(f"{'SKU':<15} {'productNumber':<15} {'InSales SKU':<15} {'productNumber OK':<20} {'Barcode InSales':<20} {'Barcode Imported':<20}")
    print("-" * 100)
    
    for result in results:
        pn_ok_str = "OK" if result["productnumber_ok"] == True else ("НЕ OK" if result["productnumber_ok"] == False else "?")
        print(f"{result['product_number']:<15} {result['product_number']:<15} {result['insales_sku']:<15} {pn_ok_str:<20} {result['barcode_in_insales']:<20} {result['barcode_imported']:<20}")
    
    print()
    print("=" * 100)
    print("ДЕТАЛЬНАЯ ИНФОРМАЦИЯ ПО КАЖДОМУ ТОВАРУ")
    print("=" * 100)
    print()
    
    for idx, result in enumerate(results, 1):
        print(f"[{idx}] Товар: {result['name']}")
        print(f"    Shopware ID: {result['id']}")
        print(f"    productNumber (root): {result['product_number_root']}")
        print(f"    productNumber (attributes): {result['product_number_attrs']}")
        print(f"    InSales SKU: {result['insales_sku']}")
        print(f"    productNumber OK: {'OK' if result['productnumber_ok'] == True else ('НЕ OK' if result['productnumber_ok'] == False else '?')}")
        print(f"    EAN/Barcode в Shopware: {result['ean_barcode']}")
        print(f"    Barcode в InSales: {result['insales_barcode'] or 'нет'}")
        print(f"    Barcode в InSales: {result['barcode_in_insales']}")
        print(f"    Barcode импортирован: {result['barcode_imported']}")
        if result['custom_fields']:
            print(f"    CustomFields: {json.dumps(result['custom_fields'], ensure_ascii=False)}")
        print()
    
    print("=" * 100)
    print("ИТОГОВЫЙ ВЫВОД")
    print("=" * 100)
    print()
    
    # Статистика
    productnumber_ok_count = sum(1 for r in results if r["productnumber_ok"] == True)
    productnumber_fail_count = sum(1 for r in results if r["productnumber_ok"] == False)
    barcode_in_insales_count = sum(1 for r in results if r["barcode_in_insales"] == "есть")
    barcode_imported_count = sum(1 for r in results if r["barcode_imported"] == "импортирован")
    
    print(f"productNumber:")
    print(f"  OK: {productnumber_ok_count}/{len(results)}")
    print(f"  НЕ OK: {productnumber_fail_count}/{len(results)}")
    print()
    print(f"barcode:")
    print(f"  Есть в InSales: {barcode_in_insales_count}/{len(results)}")
    print(f"  Импортирован: {barcode_imported_count}/{len(results)}")
    print()
    print("=" * 100)

if __name__ == "__main__":
    main()




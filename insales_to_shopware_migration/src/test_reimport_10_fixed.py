"""
Финальный тестовый переимпорт 10 товаров из InSales с проверкой Marketplace цен.
Исправленная версия: использует ID из результата импорта.
"""
import json
import sys
import time
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
SNAPSHOT_PATH = ROOT / "insales_snapshot" / "products.ndjson"
RESULT_PATH = ROOT.parent / "_scratchpad" / "full_import_result.json"

# Тестовые SKU для проверки
TEST_SKUS = ["500944170", "500944171", "500944177", "500944178", "500944203", 
             "500944207", "500944219", "500944220", "500944221", "500944222"]


def load_test_products():
    """Загружает тестовые товары из snapshot по SKU"""
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
                if variants:
                    sku = variants[0].get("sku")
                    if sku and str(sku) in TEST_SKUS:
                        products.append(product)
                        if len(products) >= 10:
                            break
            except json.JSONDecodeError:
                continue
    
    return products


def delete_product_by_number(client, product_number):
    """Удаляет товар по productNumber"""
    try:
        product_id = client.find_product_by_number(product_number)
        if product_id:
            client._request("DELETE", f"/api/product/{product_id}")
            return True, product_id
        return False, None
    except Exception as e:
        return False, str(e)


def load_import_result():
    """Загружает результат импорта из JSON файла"""
    if not RESULT_PATH.exists():
        return {}
    
    try:
        with RESULT_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def verify_product_by_id(client, product_id, product_number, expected_base_price, expected_marketplace_price):
    """Проверяет товар по ID после импорта"""
    try:
        # Получаем полные данные
        response = client._request("GET", f"/api/product/{product_id}")
        product_data = response.get("data", {}) if isinstance(response, dict) else {}
        
        if not product_data:
            return False, "Товар не найден по ID", None, None, None
        
        # Проверяем productNumber
        attributes = product_data.get("attributes", {})
        found_product_number = attributes.get("productNumber") or product_data.get("productNumber")
        
        # Проверяем base price
        base_prices = product_data.get("price", [])
        found_base_price = None
        if base_prices and len(base_prices) > 0:
            found_base_price = base_prices[0].get("gross")
        
        # Проверяем Marketplace price
        advanced_prices = product_data.get("prices", [])
        found_marketplace_price = None
        marketplace_rule_id = None
        
        # Ищем Price Rule "Marketplace Price"
        marketplace_rule = client.find_price_rule_by_name("Marketplace Price")
        
        if advanced_prices:
            for price_entry in advanced_prices:
                rule_id = price_entry.get("ruleId")
                if rule_id == marketplace_rule:
                    price_list = price_entry.get("price", [])
                    if price_list and len(price_list) > 0:
                        found_marketplace_price = price_list[0].get("gross")
                        marketplace_rule_id = rule_id
                        break
        
        # Валидация
        checks = []
        if found_product_number == product_number:
            checks.append("productNumber OK")
        else:
            checks.append(f"productNumber FAIL (found: {found_product_number}, expected: {product_number})")
        
        if found_base_price and abs(float(found_base_price) - float(expected_base_price)) < 0.01:
            checks.append("base_price OK")
        else:
            checks.append(f"base_price FAIL (found: {found_base_price}, expected: {expected_base_price})")
        
        if expected_marketplace_price:
            if found_marketplace_price and abs(float(found_marketplace_price) - float(expected_marketplace_price)) < 0.01:
                checks.append("marketplace_price OK")
            else:
                checks.append(f"marketplace_price FAIL (found: {found_marketplace_price}, expected: {expected_marketplace_price})")
        else:
            if not found_marketplace_price:
                checks.append("marketplace_price OK (не требуется)")
            else:
                checks.append(f"marketplace_price FAIL (не ожидался, но найден: {found_marketplace_price})")
        
        all_ok = all("OK" in check for check in checks)
        status = "OK" if all_ok else "FAIL"
        
        return all_ok, status, found_base_price, found_marketplace_price, "; ".join(checks)
        
    except Exception as e:
        return False, f"ERROR: {str(e)}", None, None, None


def main():
    print("=" * 80)
    print("ФИНАЛЬНЫЙ ТЕСТОВЫЙ ПЕРЕИМПОРТ 10 ТОВАРОВ")
    print("=" * 80)
    print()
    
    # Загружаем конфигурацию
    if not CONFIG_PATH.exists():
        print(f"ERROR: Конфигурация не найдена: {CONFIG_PATH}")
        return 1
    
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
    
    # Шаг 1: Загружаем тестовые товары
    print("Шаг 1: Загрузка тестовых товаров из snapshot...")
    test_products = load_test_products()
    print(f"Загружено {len(test_products)} товаров")
    
    if len(test_products) < 10:
        print(f"WARNING: Загружено только {len(test_products)} товаров из 10")
    
    # Извлекаем данные для удаления и импорта
    products_data = []
    for product in test_products:
        variants = product.get("variants", [])
        if not variants:
            continue
        
        variant = variants[0]
        sku = variant.get("sku")
        base_price = variant.get("price")
        marketplace_price = variant.get("price2")
        product_name = product.get("title", "Unknown")
        
        if sku:
            products_data.append({
                "sku": str(sku),
                "base_price": float(base_price) if base_price else 0,
                "marketplace_price": float(marketplace_price) if marketplace_price else None,
                "product_name": product_name
            })
    
    print(f"Подготовлено {len(products_data)} товаров для обработки")
    print()
    
    # Шаг 2: Удаляем существующие товары
    print("=" * 80)
    print("Шаг 2: Удаление существующих товаров")
    print("=" * 80)
    print()
    
    deleted_count = 0
    for item in products_data:
        sku = item["sku"]
        print(f"Удаление товара {sku}...")
        success, result = delete_product_by_number(client, sku)
        if success:
            print(f"  OK: Товар удален (ID: {result})")
            deleted_count += 1
        else:
            if result is None:
                print(f"  SKIP: Товар не найден (возможно, уже удален)")
            else:
                print(f"  ERROR: {result}")
        time.sleep(0.2)
    
    print(f"\nУдалено товаров: {deleted_count}/{len(products_data)}")
    print()
    
    # Шаг 3: Запускаем импорт через full_import.py
    print("=" * 80)
    print("Шаг 3: Импорт товаров через full_import.py")
    print("=" * 80)
    print()
    print("Запуск: python full_import.py --source snapshot --limit 10")
    print()
    
    result = subprocess.run(
        [sys.executable, "full_import.py", "--source", "snapshot", "--limit", "10"],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    if result.returncode != 0:
        print(f"ERROR: Импорт завершился с ошибкой (код: {result.returncode})")
        return 1
    
    print()
    print("Ожидание применения изменений в Shopware...")
    time.sleep(5)  # Даем больше времени на применение изменений
    
    # Шаг 4: Проверяем товары через Search API
    print("=" * 80)
    print("Шаг 4: Проверка результатов импорта")
    print("=" * 80)
    print()
    
    # Ищем товары по одному через find_product_by_number
    print("Поиск товаров в Shopware...")
    sku_to_id = {}
    for item in products_data:
        sku = item["sku"]
        product_id = client.find_product_by_number(sku)
        if product_id:
            sku_to_id[sku] = product_id
    
    print(f"Найдено {len(sku_to_id)} товаров из {len(products_data)}")
    print()
    
    results_table = []
    all_ok = True
    
    for item in products_data:
        sku = item["sku"]
        expected_base = item["base_price"]
        expected_marketplace = item["marketplace_price"]
        
        print(f"Проверка товара {sku}...")
        
        # Ищем product_id
        product_id = sku_to_id.get(sku)
        if not product_id:
            # Пробуем найти через find_product_by_number
            product_id = client.find_product_by_number(sku)
        
        if not product_id:
            results_table.append({
                "sku": sku,
                "base_price": "N/A",
                "marketplace_price": "N/A",
                "status": "FAIL",
                "details": "Товар не найден после импорта"
            })
            all_ok = False
            print(f"  FAIL: Товар не найден после импорта")
            continue
        
        ok, status, found_base, found_marketplace, details = verify_product_by_id(
            client, product_id, sku, expected_base, expected_marketplace
        )
        
        results_table.append({
            "sku": sku,
            "base_price": found_base or "N/A",
            "marketplace_price": found_marketplace or "N/A",
            "status": status,
            "details": details
        })
        
        if not ok:
            all_ok = False
        
        print(f"  {status}: {details}")
        time.sleep(0.2)
    
    # Выводим таблицу результатов
    print()
    print("=" * 80)
    print("ИТОГОВАЯ ТАБЛИЦА РЕЗУЛЬТАТОВ")
    print("=" * 80)
    print()
    print(f"{'SKU':<15} {'Base Price':<15} {'Marketplace Price':<20} {'Status':<10}")
    print("-" * 80)
    
    for row in results_table:
        marketplace_str = str(row["marketplace_price"]) if row["marketplace_price"] != "N/A" else "N/A"
        print(f"{row['sku']:<15} {row['base_price']:<15} {marketplace_str:<20} {row['status']:<10}")
    
    print()
    print("=" * 80)
    print("ФИНАЛЬНЫЙ ВЕРДИКТ")
    print("=" * 80)
    print()
    
    if all_ok:
        print("РАБОТАЕТ")
        print()
        print("Схема импорта считается финальной для 5000 товаров.")
        print("Все проверки пройдены успешно:")
        print("  - productNumber установлен корректно")
        print("  - base price установлен корректно")
        print("  - Marketplace price установлен корректно")
    else:
        print("НЕ РАБОТАЕТ")
        print()
        print("Обнаружены проблемы при проверке товаров.")
        print("Схема требует доработки перед импортом 5000 товаров.")
    
    print()
    print("=" * 80)
    
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())


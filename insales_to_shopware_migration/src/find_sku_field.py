"""
Точное определение поля Shopware, где хранится InSales SKU (Артикул).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
SNAPSHOT_PATH = ROOT / "insales_snapshot" / "products.ndjson"

# Примеры SKU из InSales для поиска
TEST_SKUS = ["500944170", "500944171", "500944177", "500944178", "500944203"]


def find_sku_in_data(data, sku, path=""):
    """Рекурсивно ищет значение SKU в структуре данных"""
    matches = []
    
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            if isinstance(value, (str, int, float)):
                if str(value) == sku:
                    matches.append(current_path)
            elif isinstance(value, (dict, list)):
                matches.extend(find_sku_in_data(value, sku, current_path))
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            current_path = f"{path}[{idx}]" if path else f"[{idx}]"
            matches.extend(find_sku_in_data(item, sku, current_path))
    
    return matches


def get_product_full_data(client, product_id):
    """Получает полные данные товара с associations"""
    try:
        response = client._request("GET", f"/api/product/{product_id}")
        return response.get("data", {}) if isinstance(response, dict) else {}
    except Exception as e:
        print(f"ERROR: {e}")
        return {}


def get_products_list(client, limit=20):
    """Получает список товаров из Shopware"""
    try:
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "limit": limit,
                "includes": {"product": ["id", "productNumber", "name"]}
            }
        )
        return response.get("data", [])
    except Exception as e:
        print(f"ERROR: {e}")
        return []


def load_insales_sku_map():
    """Загружает маппинг InSales ID -> SKU из snapshot"""
    sku_map = {}
    if not SNAPSHOT_PATH.exists():
        return sku_map
    
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
                    if sku:
                        sku_map[str(sku)] = product.get("id")
            except json.JSONDecodeError:
                continue
    return sku_map


def main():
    print("=" * 80)
    print("ПОИСК ПОЛЯ SHOPWARE ДЛЯ INSales SKU (АРТИКУЛ)")
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
    
    # Загружаем маппинг SKU -> InSales ID
    sku_map = load_insales_sku_map()
    print(f"Загружено {len(sku_map)} товаров с SKU из snapshot")
    print()
    
    # Получаем список товаров из Shopware
    print("Получение товаров из Shopware...")
    products = get_products_list(client, limit=20)
    print(f"Получено {len(products)} товаров")
    print()
    
    # Проверяем первые 5 товаров
    print("=" * 80)
    print("АНАЛИЗ ПОЛЕЙ ТОВАРОВ")
    print("=" * 80)
    print()
    
    field_matches = {}  # {field_path: count}
    
    for idx, product in enumerate(products[:5], 1):
        product_id = product.get("id")
        product_name = product.get("name", {})
        if isinstance(product_name, dict):
            product_name = product_name.get("ru-RU") or str(product_name)
        else:
            product_name = str(product_name)
        
        print(f"[{idx}/5] Товар: {product_name[:60]}...")
        print(f"  Shopware ID: {product_id}")
        print()
        
        # Получаем полные данные товара
        full_data = get_product_full_data(client, product_id)
        if not full_data:
            print("  ERROR: Не удалось получить данные")
            print()
            continue
        
        # Проверяем основные поля
        print("  Основные поля:")
        product_number = full_data.get("productNumber")
        manufacturer_number = full_data.get("manufacturerNumber")
        print(f"    productNumber: {product_number}")
        print(f"    manufacturerNumber: {manufacturer_number}")
        
        # Проверяем customFields
        custom_fields = full_data.get("customFields", {})
        print(f"    customFields: {json.dumps(custom_fields, ensure_ascii=False) if custom_fields else 'отсутствуют'}")
        
        # Проверяем variants
        variants = full_data.get("variants", [])
        if variants:
            print(f"    variants: найдено {len(variants)} вариантов")
            for v_idx, variant in enumerate(variants[:3], 1):
                variant_number = variant.get("productNumber")
                variant_sku = variant.get("sku")
                print(f"      variant[{v_idx}].productNumber: {variant_number}")
                print(f"      variant[{v_idx}].sku: {variant_sku}")
        else:
            print("    variants: отсутствуют")
        
        # Ищем все значения вида 500944170 в структуре данных
        print()
        print("  Поиск значений вида '500944170' в структуре данных...")
        all_matches = []
        for test_sku in TEST_SKUS:
            matches = find_sku_in_data(full_data, test_sku)
            if matches:
                all_matches.extend([(test_sku, m) for m in matches])
        
        if all_matches:
            print("    Найдено совпадений:")
            for sku, path in all_matches:
                print(f"      SKU {sku} -> {path}")
                if path not in field_matches:
                    field_matches[path] = 0
                field_matches[path] += 1
        else:
            print("    Совпадений не найдено")
        
        # Выводим полную структуру для анализа (первые уровни)
        print()
        print("  Структура данных (первые уровни):")
        for key in list(full_data.keys())[:15]:
            value = full_data[key]
            if isinstance(value, (str, int, float, bool, type(None))):
                print(f"    {key}: {value}")
            elif isinstance(value, dict):
                print(f"    {key}: {{dict с {len(value)} полями}}")
            elif isinstance(value, list):
                print(f"    {key}: [list с {len(value)} элементами]")
        
        print()
        print("-" * 80)
        print()
    
    # Итоговый анализ
    print("=" * 80)
    print("ИТОГОВЫЙ АНАЛИЗ")
    print("=" * 80)
    print()
    
    if field_matches:
        print("Поля, содержащие InSales SKU:")
        for field_path, count in sorted(field_matches.items(), key=lambda x: x[1], reverse=True):
            print(f"  {field_path}: найдено в {count} товарах")
    else:
        print("Не найдено полей, содержащих InSales SKU в проверенных товарах")
        print()
        print("Возможные причины:")
        print("1. Товары в Shopware не соответствуют товарам из snapshot")
        print("2. SKU хранится в другом формате или поле")
        print("3. Товары были импортированы без SKU")
    
    print()
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())




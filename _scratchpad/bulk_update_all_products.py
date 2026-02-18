"""
Массовое обновление всех товаров: категории, properties, visibilities
"""
import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json, split_pipe, load_properties, ensure_property_option
import csv

ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
config = load_json(ROOT / "config.json")

shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

print("=" * 60)
print("МАССОВОЕ ОБНОВЛЕНИЕ ВСЕХ ТОВАРОВ")
print("=" * 60)

# Получаем Sales Channels
print("\nПолучение Sales Channels...")
sc_response = client._request("GET", "/api/sales-channel")
sales_channels = sc_response.get("data", []) if isinstance(sc_response, dict) else []
sales_channel_ids = [sc.get("id") for sc in sales_channels if sc.get("id")]
print(f"Найдено Sales Channels: {len(sales_channel_ids)}")

# Определяем Storefront Sales Channel ID
print("\nОпределение Storefront Sales Channel...")
STOREFRONT_SALES_CHANNEL_ID = None
for sc in sales_channels:
    sc_id = sc.get("id")
    if not sc_id:
        continue
    
    # Получаем тип Sales Channel
    try:
        sc_attrs = sc.get("attributes", {})
        type_id = sc_attrs.get("typeId")
        if type_id:
            type_response = client._request("GET", f"/api/sales-channel-type/{type_id}")
            type_data = type_response.get("data", {}) if isinstance(type_response, dict) else {}
            type_attrs = type_data.get("attributes", {})
            type_name = type_attrs.get("name", "").lower()
            
            if "storefront" in type_name:
                STOREFRONT_SALES_CHANNEL_ID = sc_id
                print(f"  ✅ Storefront Sales Channel найден: {sc_id}")
                break
    except Exception:
        continue

if not STOREFRONT_SALES_CHANNEL_ID:
    print("  ❌ FATAL ERROR: Storefront Sales Channel не найден!")
    print("  Прерывание выполнения.")
    sys.exit(1)

# Читаем CSV
print("\nЧтение CSV...")
csv_data = {}
csv_path = ROOT / "output" / "products_import.csv"
with csv_path.open("r", encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        product_number = row.get("productNumber")
        if product_number:
            csv_data[product_number] = row

print(f"Загружено из CSV: {len(csv_data)} товаров")

# Получаем все товары через пагинацию
print("\nПолучение всех товаров из Shopware...")
all_products = []
limit = 100
offset = 0

while True:
    response = client._request("GET", "/api/product", params={"limit": limit, "offset": offset})
    products = response.get("data", []) if isinstance(response, dict) else []
    if not products:
        break
    all_products.extend(products)
    offset += limit
    print(f"  Загружено: {len(all_products)} товаров...")
    if len(products) < limit:
        break

print(f"Всего товаров в Shopware: {len(all_products)}")

# Обновляем товары
print("\n" + "=" * 60)
print("НАЧАЛО ОБНОВЛЕНИЯ")
print("=" * 60)

fixed = 0
skipped = 0
errors = []
option_map = {}  # Кеш для property options (общий для всех товаров)
start_time = time.time()

for idx, product in enumerate(all_products, 1):
    product_id = product.get("id")
    
    try:
        # Получаем детали товара с visibilities
        detail = client._request("GET", f"/api/product/{product_id}", params={
            "associations[visibilities][]": "visibilities"
        })
        detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
        attrs = detail_data.get("attributes", {})
        
        product_number = attrs.get("productNumber")
        if not product_number:
            skipped += 1
            continue
        
        # Получаем данные из CSV
        csv_row = csv_data.get(product_number)
        if not csv_row:
            skipped += 1
            if idx % 100 == 0:
                print(f"[{idx}/{len(all_products)}] Пропущен (нет в CSV): {product_number}")
            continue
        
        # Формируем payload для обновления
        update_payload = {}
        
        # Проверяем существующие категории перед добавлением
        existing_categories = attrs.get("categories", [])
        existing_category_ids = {cat.get("id") for cat in existing_categories if isinstance(cat, dict) and cat.get("id")}
        
        # Добавляем ВСЕ категории из цепочки (включая последнюю подкатегорию, например "Переключатели")
        category_ids = split_pipe(csv_row.get("categoryIds") or "")
        if category_ids:
            # ВАЖНО: Всегда добавляем ВСЕ категории из CSV для полной цепочки
            # Это включает root, все parent-категории и leaf category (Переключатели)
            update_payload["categories"] = [{"id": cid} for cid in category_ids]
            print(f"  [INFO] {product_number}: Добавлено {len(category_ids)} категорий из CSV")
            
            # После добавления категорий устанавливаем mainCategory через visibility.categoryId
            # Это нужно для правильных breadcrumbs на сайте (полный путь)
            # Находим самую глубокую категорию (последнюю в списке - она самая глубокая)
            deepest_category_id = category_ids[-1] if category_ids else None
            
            if deepest_category_id:
                # Получаем существующие visibilities
                try:
                    vis_response = client._request("GET", f"/api/product/{product_id}/visibilities")
                    vis_data = vis_response.get("data", []) if isinstance(vis_response, dict) else []
                    
                    # Ищем visibility для storefront
                    storefront_visibility_id = None
                    for vis_item in vis_data:
                        vis_attrs = vis_item.get("attributes", {})
                        if vis_attrs.get("salesChannelId") == STOREFRONT_SALES_CHANNEL_ID:
                            storefront_visibility_id = vis_item.get("id")
                            break
                    
                    # Обновляем categoryId через отдельный endpoint для breadcrumbs
                    if storefront_visibility_id:
                        try:
                            client._request("PATCH", f"/api/product-visibility/{storefront_visibility_id}", json={
                                "categoryId": deepest_category_id
                            })
                            print(f"  [OK] {product_number}: mainCategory установлен через visibility (для breadcrumbs)")
                        except Exception as e:
                            error_msg = str(e)[:200]
                            print(f"  [WARNING] {product_number}: Не удалось установить mainCategory: {error_msg}")
                except Exception as e:
                    error_msg = str(e)[:200]
                    print(f"  [WARNING] {product_number}: Не удалось получить visibilities: {error_msg}")
        
        # УДАЛЕНО: mainCategoryId из CSV - используем самую глубокую категорию из category_ids
        
        # Проверяем существующие properties перед добавлением
        existing_properties = attrs.get("properties", [])
        existing_property_ids = {prop.get("id") for prop in existing_properties if isinstance(prop, dict) and prop.get("id")}
        
        # Добавляем properties (характеристики) - только новые
        property_payload = []
        for entry in load_properties(csv_row.get("propertiesJson") or ""):
            option_id = ensure_property_option(client, option_map, entry)
            if option_id and option_id not in existing_property_ids:
                property_payload.append({"id": option_id})
        
        if property_payload:
            # Объединяем существующие и новые properties
            all_property_ids = list(existing_property_ids) + [p["id"] for p in property_payload]
            update_payload["properties"] = [{"id": pid} for pid in all_property_ids]
        elif not existing_property_ids:
            # Если properties нет вообще, но есть в CSV - добавляем
            property_payload_new = []
            for entry in load_properties(csv_row.get("propertiesJson") or ""):
                option_id = ensure_property_option(client, option_map, entry)
                if option_id:
                    property_payload_new.append({"id": option_id})
            if property_payload_new:
                update_payload["properties"] = property_payload_new
        
        # УДАЛЕНО: Обработка visibilities для установки mainCategory через categoryId
        # Shopware 6.7.x не поддерживает стабильную установку mainCategory через API
        # Shopware сам выберет самую глубокую категорию из product.categories для breadcrumbs
        
        if update_payload:
            try:
                client._request("PATCH", f"/api/product/{product_id}", json=update_payload)
                fixed += 1
                
                if idx % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = idx / elapsed if elapsed > 0 else 0
                    remaining = (len(all_products) - idx) / rate if rate > 0 else 0
                    print(f"[{idx}/{len(all_products)}] Обновлено: {fixed}, Пропущено: {skipped}, Ошибок: {len(errors)} | "
                          f"Скорость: {rate:.1f} товаров/сек | Осталось: {remaining:.0f} сек")
            except Exception as e:
                error_full = str(e)
                error_msg = f"Ошибка обновления {product_number}: {error_full[:200]}"
                errors.append({"product_id": product_id, "product_number": product_number, "error": error_full})
                print(f"  [FAIL] {product_number}: {error_msg}")
        else:
            skipped += 1
    
    except Exception as e:
        error_full = str(e)
        error_msg = f"Ошибка обновления {product_id}: {error_full[:200]}"
        errors.append({"product_id": product_id, "product_number": product_number, "error": error_full})
        print(f"[{idx}/{len(all_products)}] ERROR: {error_msg}")
        # Выводим полный текст ошибки для первых 3 ошибок
        if len(errors) <= 3:
            print(f"      Полный текст: {error_full}")

elapsed = time.time() - start_time
print("\n" + "=" * 60)
print("ОБНОВЛЕНИЕ ЗАВЕРШЕНО")
print("=" * 60)
print(f"Всего обработано: {len(all_products)}")
print(f"Обновлено: {fixed}")
print(f"Пропущено: {skipped}")
print(f"Ошибок: {len(errors)}")
print(f"Время выполнения: {elapsed:.1f} сек")
print(f"Средняя скорость: {len(all_products)/elapsed:.1f} товаров/сек" if elapsed > 0 else "N/A")

if errors:
    print(f"\nПервые 10 ошибок:")
    for error in errors[:10]:
        print(f"  - {error}")
    if len(errors) > 10:
        print(f"  ... и ещё {len(errors) - 10} ошибок")


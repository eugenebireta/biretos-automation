"""
Исправление товаров, найденных через GET запрос
"""
import sys
from pathlib import Path

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
print("ИСПРАВЛЕНИЕ ТОВАРОВ (через GET)")
print("=" * 60)

# Получаем Sales Channels
sc_response = client._request("GET", "/api/sales-channel")
sales_channels = sc_response.get("data", []) if isinstance(sc_response, dict) else []
sales_channel_ids = [sc.get("id") for sc in sales_channels if sc.get("id")]
print(f"Sales Channels: {len(sales_channel_ids)}")

# Читаем CSV для получения данных
csv_data = {}
csv_path = ROOT / "output" / "products_import.csv"
with csv_path.open("r", encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        product_number = row.get("productNumber")
        if product_number:
            csv_data[product_number] = row

print(f"Загружено из CSV: {len(csv_data)} товаров")

# Получаем товары через GET
print("\nПолучение товаров через GET...")
response = client._request("GET", "/api/product", params={"limit": 20})
products = response.get("data", []) if isinstance(response, dict) else []
print(f"Найдено товаров: {len(products)}")

fixed = 0
errors = []

for idx, product in enumerate(products, 1):
    product_id = product.get("id")
    
    try:
        # Получаем детали товара
        detail = client._request("GET", f"/api/product/{product_id}")
        detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
        attrs = detail_data.get("attributes", {})
        
        product_number = attrs.get("productNumber")
        if not product_number:
            continue
        
        print(f"\n{idx}. {product_number}")
        
        # Получаем данные из CSV
        csv_row = csv_data.get(product_number)
        if not csv_row:
            print(f"   ⚠ Нет данных в CSV, пропускаем")
            continue
        
        # Формируем payload для обновления
        update_payload = {}
        
        # Добавляем ВСЕ категории из цепочки (не только конечную)
        category_ids = split_pipe(csv_row.get("categoryIds") or "")
        if category_ids:
            update_payload["categories"] = [{"id": cid} for cid in category_ids]
            print(f"   Категории: {len(category_ids)}")
        
        # Добавляем properties (характеристики)
        option_map = {}  # Кеш для property options
        property_payload = []
        for entry in load_properties(csv_row.get("propertiesJson") or ""):
            option_id = ensure_property_option(client, option_map, entry)
            if option_id:
                property_payload.append({"id": option_id})
        
        if property_payload:
            update_payload["properties"] = property_payload
            print(f"   Properties: {len(property_payload)}")
        
        # Проверяем существующие visibilities перед добавлением
        existing_visibilities = attrs.get("visibilities", [])
        existing_sc_ids = {v.get("salesChannelId") for v in existing_visibilities if isinstance(v, dict)}
        
        # Добавляем привязку к Sales Channel только если её нет
        if sales_channel_ids:
            new_visibilities = [
                {"salesChannelId": sc_id, "visibility": 30}
                for sc_id in sales_channel_ids
                if sc_id not in existing_sc_ids
            ]
            if new_visibilities:
                # Если есть существующие, добавляем их тоже, чтобы не потерять
                if existing_visibilities:
                    update_payload["visibilities"] = [
                        {"salesChannelId": v.get("salesChannelId"), "visibility": v.get("visibility", 30)}
                        for v in existing_visibilities if isinstance(v, dict) and v.get("salesChannelId")
                    ] + new_visibilities
                else:
                    update_payload["visibilities"] = new_visibilities
                print(f"   Sales Channels: добавлено {len(new_visibilities)} новых")
            elif existing_visibilities:
                print(f"   Sales Channels: уже привязаны ({len(existing_visibilities)})")
        
        if update_payload:
            client._request("PATCH", f"/api/product/{product_id}", json=update_payload)
            fixed += 1
            print(f"   [OK] Обновлен")
        else:
            print(f"   - Нечего обновлять")
        
    except Exception as e:
        error_msg = f"Ошибка обновления {product_id}: {e}"
        errors.append(error_msg)
        print(f"   [ERROR]: {error_msg}")

print("\n" + "=" * 60)
print(f"Исправлено товаров: {fixed}")
print(f"Ошибок: {len(errors)}")
if errors:
    print("\nОшибки:")
    for error in errors[:5]:
        print(f"  - {error}")


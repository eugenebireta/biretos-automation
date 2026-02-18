"""
Скрипт для исправления существующих товаров: добавление фото и привязки к Sales Channel
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json, split_pipe
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
print("ИСПРАВЛЕНИЕ СУЩЕСТВУЮЩИХ ТОВАРОВ")
print("=" * 60)

# Получаем Sales Channels
print("\nПолучение Sales Channels...")
sc_response = client._request("GET", "/api/sales-channel")
sales_channels = sc_response.get("data", []) if isinstance(sc_response, dict) else []
sales_channel_ids = [sc.get("id") for sc in sales_channels if sc.get("id")]
print(f"Найдено Sales Channels: {len(sales_channel_ids)}")

# Читаем CSV
csv_path = ROOT / "output" / "products_import.csv"
print(f"\nЧтение CSV: {csv_path}")

fixed = 0
errors = []

with csv_path.open("r", encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    for idx, row in enumerate(reader, 1):
        if idx > 10:  # Ограничиваем первыми 10 для теста
            break
        
        product_number = row.get("productNumber")
        
        try:
            # Ищем товар
            response = client._request(
                "POST",
                "/api/search/product",
                json={
                    "filter": [{"field": "productNumber", "type": "equals", "value": product_number}],
                    "includes": {"product": ["id"]},
                    "limit": 1,
                },
            )
            
            if not response.get("total") or not response.get("data"):
                print(f"{idx}. {product_number}: не найден, пропускаем")
                continue
            
            product_id = response["data"][0]["id"]
            
            # Формируем payload для обновления
            update_payload = {}
            
            # Добавляем категории
            category_ids = split_pipe(row.get("categoryIds") or "")
            if category_ids:
                update_payload["categories"] = [{"id": cid} for cid in category_ids]
            
            # Добавляем изображения
            image_urls = split_pipe(row.get("imageUrls") or "")
            if image_urls:
                update_payload["media"] = [{"url": url} for url in image_urls if url]
            
            # Добавляем привязку к Sales Channel
            if sales_channel_ids:
                update_payload["visibilities"] = [
                    {"salesChannelId": sc_id, "visibility": 30}
                    for sc_id in sales_channel_ids
                ]
            
            if update_payload:
                print(f"\n{idx}. Обновление {product_number}...")
                print(f"   Категории: {len(category_ids) if category_ids else 0}")
                print(f"   Изображения: {len(image_urls) if image_urls else 0}")
                print(f"   Sales Channels: {len(sales_channel_ids)}")
                
                client._request("PATCH", f"/api/product/{product_id}", json=update_payload)
                fixed += 1
                print(f"   ✓ Обновлён")
            else:
                print(f"{idx}. {product_number}: нечего обновлять")
        
        except Exception as e:
            error_msg = f"Ошибка обновления {product_number}: {e}"
            errors.append(error_msg)
            print(f"{idx}. ERROR: {error_msg}")

print("\n" + "=" * 60)
print(f"Исправлено товаров: {fixed}")
print(f"Ошибок: {len(errors)}")
if errors:
    print("\nОшибки:")
    for error in errors[:5]:
        print(f"  - {error}")









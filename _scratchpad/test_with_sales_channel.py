"""
Тест импорта с Sales Channel ID в заголовках
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json, build_payload
import json

ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
config = load_json(ROOT / "config.json")

shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

# Получаем Sales Channel
print("=== Получение Sales Channel ===")
try:
    response = client._request("GET", "/api/sales-channel")
    sales_channels = response.get("data", []) if isinstance(response, dict) else []
    print(f"Найдено Sales Channels: {len(sales_channels)}")
    for sc in sales_channels:
        sc_id = sc.get('id')
        sc_name = sc.get('name') or sc.get('typeId') or 'Unknown'
        print(f"  ID: {sc_id}, Name/Type: {sc_name}")
        if sc_id:
            # Пробуем создать товар с этим Sales Channel ID
            print(f"\n=== Тест импорта с Sales Channel ID: {sc_id} ===")
            
            # Получаем тестовый товар из CSV
            import csv
            csv_path = ROOT / "output" / "products_import.csv"
            with csv_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                row = next(reader)
            
            option_map = {}
            payload = build_payload(row, shopware_client=client, option_map=option_map)
            
            # Добавляем Sales Channel ID в заголовки
            headers = {"sw-sales-channel-id": sc_id, "sw-currency-id": client.get_system_currency_id()}
            
            print(f"Payload price: {json.dumps(payload['price'], indent=2, ensure_ascii=False)}")
            print(f"Headers: {headers}")
            
            try:
                # Пробуем создать товар
                response = client._request("POST", "/api/product", json=payload, headers=headers)
                print(f"✓ УСПЕХ! Товар создан: {payload['productNumber']}")
                print(f"Response: {json.dumps(response, indent=2, ensure_ascii=False) if response else 'None'}")
                break
            except Exception as e:
                print(f"✗ Ошибка: {e}")
                continue
except Exception as e:
    print(f"Ошибка получения Sales Channel: {e}")









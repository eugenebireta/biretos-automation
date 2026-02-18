"""
Тест импорта с Sales Channel ID в заголовках
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json, build_payload
import csv
import json

ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
config = load_json(ROOT / "config.json")

shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

print("=== Получение Sales Channel ===")
try:
    response = client._request("GET", "/api/sales-channel")
    sales_channels = response.get("data", []) if isinstance(response, dict) else []
    print(f"Найдено Sales Channels: {len(sales_channels)}")
    
    if sales_channels:
        sc_id = sales_channels[0].get('id')
        print(f"Используем Sales Channel ID: {sc_id}")
        
        # Получаем тестовый товар
        csv_path = ROOT / "output" / "products_import.csv"
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            row = next(reader)
        
        option_map = {}
        payload = build_payload(row, shopware_client=client, option_map=option_map)
        
        system_currency_id = client.get_system_currency_id()
        system_language_id = client.get_system_language_id()
        
        print(f"\n=== Тест импорта с заголовками ===")
        print(f"System Currency ID: {system_currency_id}")
        print(f"System Language ID: {system_language_id}")
        print(f"Sales Channel ID: {sc_id}")
        print(f"Payload price: {json.dumps(payload['price'], indent=2, ensure_ascii=False)}")
        
        # Пробуем с заголовками
        headers = {
            "sw-currency-id": system_currency_id,
            "sw-language-id": system_language_id,
            "sw-sales-channel-id": sc_id,
        }
        print(f"Headers: {json.dumps(headers, indent=2, ensure_ascii=False)}")
        
        try:
            response = client._request("POST", "/api/product", json=payload, headers=headers)
            print(f"\nSUCCESS! Product created: {payload['productNumber']}")
            print(f"Response: {json.dumps(response, indent=2, ensure_ascii=False) if response else 'None'}")
        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("Sales Channels не найдены")
        
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()









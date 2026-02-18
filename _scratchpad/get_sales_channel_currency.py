"""
Получение валюты из Sales Channel
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json
import json

ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
config = load_json(ROOT / "config.json")

shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

print("=== Получение Sales Channel с валютой ===")
try:
    response = client._request(
        "POST",
        "/api/search/sales-channel",
        json={
            "includes": {"sales_channel": ["id", "name", "currencyId", "currency"]},
            "associations": {
                "currency": {
                    "associations": {}
                }
            },
            "limit": 10
        }
    )
    sales_channels = response.get("data", []) if isinstance(response, dict) else []
    print(f"Найдено Sales Channels: {len(sales_channels)}")
    
    default_currency_id = None
    for sc in sales_channels:
        sc_id = sc.get('id')
        currency_id = sc.get('currencyId')
        print(f"Sales Channel ID: {sc_id}, Currency ID: {currency_id}")
        if currency_id and not default_currency_id:
            default_currency_id = currency_id
            print(f">>> Используем валюту из Sales Channel: {currency_id}")
    
    if default_currency_id:
        print(f"\n=== Тест импорта с валютой из Sales Channel ===")
        import csv
        csv_path = ROOT / "output" / "products_import.csv"
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            row = next(reader)
        
        # Создаем payload с валютой из Sales Channel
        from import_utils import build_payload
        option_map = {}
        
        # Временно переопределяем get_system_currency_id для использования валюты из Sales Channel
        original_method = client.get_system_currency_id
        client.get_system_currency_id = lambda: default_currency_id
        
        payload = build_payload(row, shopware_client=client, option_map=option_map)
        
        print(f"Payload price: {json.dumps(payload['price'], indent=2, ensure_ascii=False)}")
        
        # Добавляем Sales Channel ID в заголовки
        headers = {"sw-sales-channel-id": sales_channels[0].get('id'), "sw-currency-id": default_currency_id}
        print(f"Headers: {json.dumps(headers, indent=2, ensure_ascii=False)}")
        
        try:
            response = client._request("POST", "/api/product", json=payload, headers=headers)
            print(f"SUCCESS! Product created: {payload['productNumber']}")
        except Exception as e:
            print(f"ERROR: {e}")
        
        # Восстанавливаем оригинальный метод
        client.get_system_currency_id = original_method
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()









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

print("=== Получение валюты из Sales Channel ===")

try:
    # Получаем Sales Channel с валютой
    response = client._request(
        "POST",
        "/api/search/sales-channel",
        json={
            "includes": {
                "sales_channel": ["id", "name", "currencyId", "currency"]
            },
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
    
    for sc in sales_channels:
        sc_id = sc.get('id')
        currency_id = sc.get('currencyId')
        print(f"Sales Channel ID: {sc_id}, Currency ID: {currency_id}")
        
        if currency_id:
            print(f"\n>>> Валюта из Sales Channel: {currency_id}")
            
            # Проверяем, совпадает ли с системной валютой
            system_currency = client.get_system_currency_id()
            print(f"System Currency: {system_currency}")
            
            if currency_id == system_currency:
                print("✓ Валюта Sales Channel совпадает с системной валютой")
            else:
                print("⚠ Валюта Sales Channel отличается от системной валюты")
                print(f"  Попробуем использовать валюту из Sales Channel: {currency_id}")
                
                # Пробуем создать товар с валютой из Sales Channel
                import csv
                csv_path = ROOT / "output" / "products_import.csv"
                with csv_path.open("r", encoding="utf-8", newline="") as f:
                    reader = csv.DictReader(f)
                    row = next(reader)
                
                from import_utils import build_payload
                option_map = {}
                
                # Временно переопределяем get_system_currency_id
                original_method = client.get_system_currency_id
                client.get_system_currency_id = lambda: currency_id
                
                payload = build_payload(row, shopware_client=client, option_map=option_map)
                
                print(f"\nPayload price: {json.dumps(payload['price'], indent=2, ensure_ascii=False)}")
                
                headers = {
                    "sw-currency-id": currency_id,
                    "sw-language-id": client.get_system_language_id(),
                    "sw-sales-channel-id": sc_id,
                }
                
                try:
                    response = client._request("POST", "/api/product", json=payload, headers=headers)
                    print(f"\nSUCCESS! Product created with Sales Channel currency!")
                    break
                except Exception as e:
                    print(f"\nERROR with Sales Channel currency: {e}")
                
                # Восстанавливаем оригинальный метод
                client.get_system_currency_id = original_method
            break
        
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()









"""
Проверка валюты по умолчанию в Sales Channels
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

print("=== Проверка валюты в Sales Channels ===")

try:
    # Получаем все Sales Channels с детальной информацией
    response = client._request(
        "POST",
        "/api/search/sales-channel",
        json={
            "includes": {
                "sales_channel": [
                    "id",
                    "name",
                    "typeId",
                    "currencyId",
                    "languageId",
                    "domains"
                ]
            },
            "limit": 100
        }
    )
    
    sales_channels = response.get("data", []) if isinstance(response, dict) else []
    print(f"Найдено Sales Channels: {len(sales_channels)}\n")
    
    for sc in sales_channels:
        sc_id = sc.get('id')
        sc_name = sc.get('name', 'N/A')
        currency_id = sc.get('currencyId')
        language_id = sc.get('languageId')
        sc_type = sc.get('typeId', 'N/A')
        
        print(f"Sales Channel: {sc_name}")
        print(f"  ID: {sc_id}")
        print(f"  Type ID: {sc_type}")
        print(f"  Currency ID: {currency_id}")
        print(f"  Language ID: {language_id}")
        
        # Получаем детали валюты
        if currency_id:
            try:
                currency_response = client._request(
                    "POST",
                    "/api/search/currency",
                    json={
                        "filter": [{"field": "id", "type": "equals", "value": currency_id}],
                        "includes": {"currency": ["id", "isoCode", "name", "symbol", "factor"]},
                        "limit": 1,
                    }
                )
                if currency_response.get("total") and currency_response.get("data"):
                    curr = currency_response["data"][0]
                    print(f"  Валюта:")
                    print(f"    ISO Code: {curr.get('isoCode')}")
                    print(f"    Name: {curr.get('name')}")
                    print(f"    Symbol: {curr.get('symbol')}")
                    print(f"    Factor: {curr.get('factor')}")
            except Exception as e:
                print(f"  ⚠ Не удалось получить детали валюты: {e}")
        
        print()
    
    # Определяем валюту по умолчанию из первого Sales Channel
    if sales_channels and sales_channels[0].get('currencyId'):
        default_currency_id = sales_channels[0].get('currencyId')
        print(f"=== Рекомендуемая валюта по умолчанию ===")
        print(f"Currency ID из первого Sales Channel: {default_currency_id}")
        
        # Проверяем, совпадает ли она с RUB
        try:
            rub_id = client.get_currency_id("RUB")
            if rub_id == default_currency_id:
                print(f"✓ Валюта совпадает с RUB: {rub_id}")
            else:
                print(f"⚠ Валюта отличается от RUB")
                print(f"  RUB ID: {rub_id}")
                print(f"  Sales Channel Currency ID: {default_currency_id}")
        except Exception as e:
            print(f"⚠ Ошибка проверки RUB: {e}")
            
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()









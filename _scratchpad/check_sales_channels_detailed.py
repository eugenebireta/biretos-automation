"""
Детальная проверка Sales Channels через GET API
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

print("=== Детальная проверка Sales Channels ===")

try:
    # Получаем список Sales Channels через GET
    response = client._request("GET", "/api/sales-channel")
    sales_channels = response.get("data", []) if isinstance(response, dict) else []
    print(f"Найдено Sales Channels: {len(sales_channels)}\n")
    
    for sc in sales_channels:
        sc_id = sc.get('id')
        sc_name = sc.get('name', 'N/A')
        currency_id = sc.get('currencyId')
        language_id = sc.get('languageId')
        
        print(f"Sales Channel: {sc_name}")
        print(f"  ID: {sc_id}")
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
        else:
            print(f"  ⚠ Currency ID не установлен")
        
        print()
    
    # Пробуем получить детали каждого Sales Channel через GET с includes
    print("=== Детальная информация через GET ===")
    for sc in sales_channels:
        sc_id = sc.get('id')
        try:
            detail_response = client._request(
                "GET",
                f"/api/sales-channel/{sc_id}",
                params={"associations[currency][]": "id,isoCode,name"}
            )
            print(f"Sales Channel {sc_id}:")
            print(json.dumps(detail_response, indent=2, ensure_ascii=False)[:500])
            print()
        except Exception as e:
            print(f"Ошибка получения деталей для {sc_id}: {e}")
            
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()









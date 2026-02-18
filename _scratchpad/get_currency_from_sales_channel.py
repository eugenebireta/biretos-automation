"""
Получение валюты напрямую из Sales Channel
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
    # Получаем список Sales Channels
    response = client._request("GET", "/api/sales-channel")
    sales_channels = response.get("data", []) if isinstance(response, dict) else []
    
    print(f"Найдено Sales Channels: {len(sales_channels)}\n")
    
    for sc in sales_channels:
        sc_id = sc.get('id')
        
        # Получаем детали Sales Channel с ассоциациями
        try:
            detail_response = client._request("GET", f"/api/sales-channel/{sc_id}")
            sc_data = detail_response.get("data", {}) if isinstance(detail_response, dict) else {}
            attributes = sc_data.get("attributes", {})
            
            currency_id = attributes.get("currencyId")
            print(f"Sales Channel ID: {sc_id}")
            print(f"  Currency ID: {currency_id}")
            
            if currency_id:
                # Пробуем получить валюту через GET
                try:
                    currency_response = client._request("GET", f"/api/currency/{currency_id}")
                    currency_data = currency_response.get("data", {}) if isinstance(currency_response, dict) else {}
                    currency_attrs = currency_data.get("attributes", {})
                    
                    print(f"  Валюта:")
                    print(f"    ID: {currency_id}")
                    print(f"    ISO Code: {currency_attrs.get('isoCode')}")
                    print(f"    Name: {currency_attrs.get('name')}")
                    print(f"    Symbol: {currency_attrs.get('symbol')}")
                    print(f"    Factor: {currency_attrs.get('factor')}")
                    
                    iso_code = currency_attrs.get('isoCode')
                    if iso_code and iso_code.upper() == 'RUB':
                        print(f"    ✓ Это RUB!")
                except Exception as e:
                    print(f"  ⚠ Не удалось получить валюту через GET: {e}")
                    # Пробуем через search
                    try:
                        search_response = client._request(
                            "POST",
                            "/api/search/currency",
                            json={
                                "filter": [{"field": "id", "type": "equals", "value": currency_id}],
                                "includes": {"currency": ["id", "isoCode", "name", "symbol", "factor"]},
                                "limit": 1,
                            }
                        )
                        if search_response.get("total") and search_response.get("data"):
                            curr = search_response["data"][0]
                            print(f"  Валюта (через search):")
                            print(f"    ISO Code: {curr.get('isoCode')}")
                            print(f"    Name: {curr.get('name')}")
                    except Exception as e2:
                        print(f"  ⚠ Не удалось получить валюту через search: {e2}")
            
            print()
        except Exception as e:
            print(f"Ошибка получения деталей для {sc_id}: {e}\n")
            
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()









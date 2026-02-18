"""
Проверка ISO кода системной валюты
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

print("=== Проверка ISO кода системной валюты ===")

system_currency_id = client.get_system_currency_id()
print(f"System Currency ID: {system_currency_id}")

# Пробуем получить ISO код через поиск по ID
try:
    response = client._request(
        "POST",
        "/api/search/currency",
        json={
            "filter": [{"field": "id", "type": "equals", "value": system_currency_id}],
            "includes": {"currency": ["id", "isoCode", "factor", "symbol", "name", "shortName"]},
            "limit": 1,
        },
    )
    
    if response.get("total") and response.get("data"):
        curr = response["data"][0]
        iso_code = curr.get('isoCode')
        print(f"\n✓ Детали системной валюты:")
        print(f"  ID: {curr.get('id')}")
        print(f"  ISO Code: {iso_code}")
        print(f"  Name: {curr.get('name')}")
        print(f"  Short Name: {curr.get('shortName')}")
        print(f"  Symbol: {curr.get('symbol')}")
        print(f"  Factor: {curr.get('factor')}")
        
        if iso_code and iso_code.upper() == 'RUB':
            print(f"\n✓ ISO код правильный: RUB")
        elif iso_code and iso_code.upper() == 'EUR':
            print(f"\n⚠ ПРОБЛЕМА: ISO код всё ещё EUR!")
            print(f"  Shopware может проверять default currency по ISO коду 'EUR'")
            print(f"  Нужно убедиться, что ISO код изменён на 'RUB' в админ-панели")
        else:
            print(f"\n⚠ ISO код: '{iso_code}' (не RUB и не EUR)")
    else:
        print("✗ Не удалось получить детали валюты")
        
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()









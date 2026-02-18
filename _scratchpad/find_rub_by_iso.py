"""
Поиск валюты RUB по ISO коду через search API
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json

ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
config = load_json(ROOT / "config.json")

shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

print("=== Поиск валюты RUB по ISO коду ===")

try:
    # Пробуем найти RUB через поиск по ISO коду
    response = client._request(
        "POST",
        "/api/search/currency",
        json={
            "filter": [
                {"field": "isoCode", "type": "equals", "value": "RUB"}
            ],
            "includes": {"currency": ["id", "isoCode", "factor", "symbol", "name"]},
            "limit": 1
        }
    )
    
    if response.get("total", 0) > 0:
        rub_currency = response["data"][0]
        rub_id = rub_currency.get("id")
        print(f"✓ Найдена валюта RUB: {rub_id}")
        print(f"  ISO: {rub_currency.get('isoCode')}")
        print(f"  Name: {rub_currency.get('name')}")
        print(f"  Symbol: {rub_currency.get('symbol')}")
        print(f"  Factor: {rub_currency.get('factor')}")
        print(f"\n>>> ID валюты RUB для использования: {rub_id}")
    else:
        print("✗ Валюта RUB не найдена по ISO коду")
        print("  Попробуем найти через поиск по имени...")
        
        # Пробуем найти через имя
        response = client._request(
            "POST",
            "/api/search/currency",
            json={
                "filter": [
                    {"field": "name", "type": "contains", "value": "Ruble"}
                ],
                "includes": {"currency": ["id", "isoCode", "factor", "symbol", "name"]},
                "limit": 10
            }
        )
        
        if response.get("total", 0) > 0:
            print(f"Найдено валют с 'Ruble' в имени: {response.get('total')}")
            for curr in response["data"]:
                print(f"  ID: {curr.get('id')}, ISO: {curr.get('isoCode')}, Name: {curr.get('name')}")
                if curr.get('isoCode') == 'RUB' or 'RUB' in (curr.get('name') or '').upper():
                    print(f"  >>> Это RUB: {curr.get('id')}")
        else:
            print("✗ Валюта RUB не найдена")
            print("\nПроверьте в админ-панели Shopware:")
            print("1. Убедитесь, что валюта RUB добавлена")
            print("2. Убедитесь, что ISO код установлен как 'RUB'")
            print("3. Убедитесь, что валюта установлена как системная (default)")
        
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()









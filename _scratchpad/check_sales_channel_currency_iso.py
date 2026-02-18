"""
Проверка ISO кода валюты из Sales Channel
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

print("=== Проверка валюты из Sales Channel ===")

# Валюта из Sales Channel
sales_channel_currency_id = "b7d2554b0ce847cd82f3ac9bd1c0dfca"

try:
    # Получаем детали валюты из Sales Channel
    currency_response = client._request(
        "POST",
        "/api/search/currency",
        json={
            "filter": [{"field": "id", "type": "equals", "value": sales_channel_currency_id}],
            "includes": {"currency": ["id", "isoCode", "name", "symbol", "factor"]},
            "limit": 1,
        }
    )
    
    if currency_response.get("total") and currency_response.get("data"):
        curr = currency_response["data"][0]
        print(f"Валюта из Sales Channel:")
        print(f"  ID: {curr.get('id')}")
        print(f"  ISO Code: {curr.get('isoCode')}")
        print(f"  Name: {curr.get('name')}")
        print(f"  Symbol: {curr.get('symbol')}")
        print(f"  Factor: {curr.get('factor')}")
        
        iso_code = curr.get('isoCode')
        if iso_code and iso_code.upper() == 'RUB':
            print(f"\n✓ Это RUB! Нужно использовать эту валюту: {sales_channel_currency_id}")
        else:
            print(f"\n⚠ ISO код: {iso_code} (не RUB)")
    else:
        print("✗ Не удалось получить детали валюты")
    
    # Сравниваем с валютой, которую мы использовали ранее
    print(f"\n=== Сравнение ===")
    try:
        rub_id_by_iso = client.get_currency_id("RUB")
        print(f"RUB по ISO коду: {rub_id_by_iso}")
        print(f"Валюта из Sales Channel: {sales_channel_currency_id}")
        
        if rub_id_by_iso == sales_channel_currency_id:
            print(f"✓ Они совпадают!")
        else:
            print(f"⚠ Они РАЗЛИЧАЮТСЯ!")
            print(f"  Нужно использовать валюту из Sales Channel: {sales_channel_currency_id}")
    except Exception as e:
        print(f"Ошибка сравнения: {e}")
        
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()









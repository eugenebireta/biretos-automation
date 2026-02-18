"""
Проверка, что RUB установлена как системная валюта
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

print("=== Проверка валюты RUB как системной ===")

try:
    # Ищем RUB по ISO коду
    rub_response = client._request(
        "POST",
        "/api/search/currency",
        json={
            "filter": [{"field": "isoCode", "type": "equals", "value": "RUB"}],
            "includes": {"currency": ["id", "isoCode", "factor", "symbol", "name"]},
            "limit": 1,
        },
    )
    
    if rub_response.get("total") and rub_response.get("data"):
        rub_curr = rub_response["data"][0]
        rub_id = rub_curr.get("id")
        rub_factor = rub_curr.get("factor")
        rub_iso = rub_curr.get("isoCode")
        
        print(f"✓ Найдена валюта RUB:")
        print(f"  ID: {rub_id}")
        print(f"  ISO: {rub_iso}")
        print(f"  Factor: {rub_factor}")
        print(f"  Name: {rub_curr.get('name')}")
        print(f"  Symbol: {rub_curr.get('symbol')}")
        
        if rub_factor == 1.0:
            print(f"\n✓ RUB установлена как системная валюта (factor=1.0)!")
            print(f"  Используем ID: {rub_id}")
        else:
            print(f"\n⚠ RUB найдена, но factor={rub_factor} (не 1.0)")
            print(f"  Нужно установить factor=1.0 в админ-панели")
    else:
        print("✗ Валюта RUB не найдена по ISO коду")
        print("  Проверьте, что ISO код установлен как 'RUB' в админ-панели")
    
    # Проверяем, что get_system_currency_id возвращает RUB
    print(f"\n=== Проверка get_system_currency_id() ===")
    system_currency_id = client.get_system_currency_id()
    print(f"System Currency ID: {system_currency_id}")
    
    if rub_response.get("total") and rub_response.get("data"):
        rub_id = rub_response["data"][0].get("id")
        if system_currency_id == rub_id:
            print(f"✓ get_system_currency_id() возвращает RUB!")
        else:
            print(f"⚠ get_system_currency_id() возвращает другую валюту: {system_currency_id}")
            print(f"  Ожидалось: {rub_id}")
        
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()









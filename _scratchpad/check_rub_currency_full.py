"""
Проверка валюты RUB с полной информацией через search API
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

print("=== Проверка валют через Search API ===")

try:
    # Используем search API с includes для получения полной информации
    response = client._request(
        "POST",
        "/api/search/currency",
        json={
            "includes": {
                "currency": ["id", "isoCode", "factor", "symbol", "name", "shortName", "isSystemDefault"]
            },
            "limit": 100
        }
    )
    
    currencies = response.get("data", []) if isinstance(response, dict) else []
    print(f"Найдено валют: {len(currencies)}")
    
    rub_currency = None
    system_currency = None
    default_currency = None
    
    for curr in currencies:
        curr_id = curr.get('id')
        iso = curr.get('isoCode')
        factor = curr.get('factor')
        symbol = curr.get('symbol')
        name = curr.get('name') or curr.get('shortName') or 'Unknown'
        is_default = curr.get('isSystemDefault')
        
        print(f"\n  ID: {curr_id}")
        print(f"    ISO: {iso}, Name: {name}, Symbol: {symbol}")
        print(f"    Factor: {factor}, IsSystemDefault: {is_default}")
        
        if iso and iso.upper() == 'RUB':
            rub_currency = curr_id
            print(f"    >>> НАЙДЕНА ВАЛЮТА RUB: {curr_id}")
        
        if factor == 1.0:
            system_currency = curr_id
            print(f"    >>> ВАЛЮТА С FACTOR=1.0: {curr_id}")
        
        if is_default:
            default_currency = curr_id
            print(f"    >>> ВАЛЮТА ПО УМОЛЧАНИЮ (isSystemDefault=true): {curr_id}")
    
    print(f"\n=== Итоговые результаты ===")
    print(f"RUB Currency ID: {rub_currency}")
    print(f"System Currency ID (factor=1.0): {system_currency}")
    print(f"Default Currency ID (isSystemDefault): {default_currency}")
    
    # Проверяем текущую системную валюту через get_system_currency_id
    current_system = client.get_system_currency_id()
    print(f"Current System Currency (через get_system_currency_id): {current_system}")
    
    if rub_currency:
        print(f"\n✓ Валюта RUB найдена: {rub_currency}")
        if rub_currency == default_currency or rub_currency == system_currency:
            print("✓ RUB установлена как системная/дефолтная валюта!")
            print(f"  Используем ID: {rub_currency}")
        else:
            print("⚠ RUB найдена, но не установлена как системная")
            print(f"  Системная валюта: {default_currency or system_currency or current_system}")
    else:
        print("\n✗ Валюта RUB не найдена в списке валют")
        print("  Возможно, нужно добавить RUB через админ-панель")
        
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()









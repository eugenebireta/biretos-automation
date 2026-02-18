"""
Проверка валюты RUB в Shopware после настройки в админ-панели
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

print("=== Проверка валют в Shopware ===")

# Получаем все валюты
try:
    response = client._request("GET", "/api/currency")
    currencies = response.get("data", []) if isinstance(response, dict) else []
    print(f"Найдено валют: {len(currencies)}")
    
    rub_currency = None
    system_currency = None
    
    for curr in currencies:
        curr_id = curr.get('id')
        iso = curr.get('isoCode')
        factor = curr.get('factor')
        symbol = curr.get('symbol')
        name = curr.get('name') or curr.get('shortName') or 'Unknown'
        
        print(f"  ID: {curr_id}")
        print(f"    ISO: {iso}, Name: {name}, Symbol: {symbol}, Factor: {factor}")
        
        if iso and iso.upper() == 'RUB':
            rub_currency = curr_id
            print(f"    >>> НАЙДЕНА ВАЛЮТА RUB: {curr_id}")
        
        if factor == 1.0:
            system_currency = curr_id
            print(f"    >>> ВАЛЮТА С FACTOR=1.0 (системная): {curr_id}")
    
    print(f"\n=== Результаты ===")
    print(f"RUB Currency ID: {rub_currency}")
    print(f"System Currency ID (factor=1.0): {system_currency}")
    
    # Проверяем текущую системную валюту через get_system_currency_id
    current_system = client.get_system_currency_id()
    print(f"Current System Currency (через API): {current_system}")
    
    if rub_currency:
        print(f"\n✓ Валюта RUB найдена: {rub_currency}")
        if rub_currency == system_currency or rub_currency == current_system:
            print("✓ RUB установлена как системная валюта!")
        else:
            print("⚠ RUB найдена, но не установлена как системная")
            print(f"  Системная валюта: {system_currency or current_system}")
    else:
        print("✗ Валюта RUB не найдена в списке валют")
        
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()









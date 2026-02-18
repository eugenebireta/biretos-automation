"""
Поиск валюты с factor=1.0 (системная валюта)
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

print("=== Поиск системной валюты (factor=1.0) ===")

try:
    # Получаем все валюты
    response = client._request(
        "POST",
        "/api/search/currency",
        json={
            "includes": {"currency": ["id", "isoCode", "factor", "symbol", "name", "shortName"]},
            "limit": 100,
        },
    )
    
    currencies = response.get("data", []) if isinstance(response, dict) else []
    print(f"Найдено валют: {len(currencies)}")
    
    default_currency = None
    for curr in currencies:
        factor = curr.get("factor")
        if factor == 1.0:
            default_currency = curr
            print(f"\n✓ Найдена системная валюта (factor=1.0):")
            print(f"  ID: {curr.get('id')}")
            print(f"  ISO Code: {curr.get('isoCode')}")
            print(f"  Name: {curr.get('name')}")
            print(f"  Short Name: {curr.get('shortName')}")
            print(f"  Symbol: {curr.get('symbol')}")
            print(f"  Factor: {factor}")
            
            iso_code = curr.get('isoCode')
            if iso_code and iso_code.upper() == 'RUB':
                print(f"\n✓ Это RUB - системная валюта установлена правильно!")
            else:
                print(f"\n⚠ Системная валюта имеет ISO: '{iso_code}' (не RUB)")
            break
    
    if not default_currency:
        print("\n✗ Не найдена валюта с factor=1.0")
        print("  Показываю все валюты:")
        for curr in currencies[:5]:  # Показываем первые 5
            print(f"  ID: {curr.get('id')}, ISO: {curr.get('isoCode')}, Factor: {curr.get('factor')}")
    
    # Проверяем get_system_currency_id
    print(f"\n=== Проверка get_system_currency_id() ===")
    system_id = client.get_system_currency_id()
    print(f"System Currency ID: {system_id}")
    
    if default_currency and system_id == default_currency.get('id'):
        print("✓ get_system_currency_id() возвращает правильную валюту")
    else:
        print(f"⚠ get_system_currency_id() возвращает: {system_id}")
        if default_currency:
            print(f"  Ожидалось: {default_currency.get('id')}")
        
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()









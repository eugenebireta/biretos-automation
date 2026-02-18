"""
Определение реальной default currency в Shopware через System Config и Sales Channel
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

print("=== Step 1: System Config ===")
try:
    response = client._request("GET", "/api/system-config", params={"domain": "core.currency"})
    print(f"System Config (core.currency): {json.dumps(response, indent=2, ensure_ascii=False)}")
except Exception as e:
    print(f"System Config недоступен: {e}")

print("\n=== Step 2: Sales Channels (с includes) ===")
try:
    response = client._request(
        "POST",
        "/api/search/sales-channel",
        json={
            "includes": {"sales_channel": ["id", "name", "currencyId", "currency"]},
            "associations": {"currency": {"associations": {}}},
        }
    )
    sales_channels = response.get("data", []) if isinstance(response, dict) else []
    print(f"Найдено Sales Channels: {len(sales_channels)}")
    for sc in sales_channels:
        currency_id = sc.get('currencyId')
        print(f"  ID: {sc.get('id')}, Name: {sc.get('name')}, CurrencyId: {currency_id}")
        if currency_id:
            print(f"  >>> Default Currency ID из Sales Channel: {currency_id}")
            default_currency_id = currency_id
except Exception as e:
    print(f"Sales Channels недоступны: {e}")

print("\n=== Step 3: Все валюты (с includes) ===")
try:
    response = client._request(
        "POST",
        "/api/search/currency",
        json={
            "includes": {"currency": ["id", "isoCode", "factor", "symbol", "isSystemDefault"]},
            "limit": 100,
        }
    )
    currencies = response.get("data", []) if isinstance(response, dict) else []
    print(f"Найдено валют: {len(currencies)}")
    for curr in currencies:
        curr_id = curr.get('id')
        iso = curr.get('isoCode')
        factor = curr.get('factor')
        symbol = curr.get('symbol')
        is_default = curr.get('isSystemDefault')
        print(f"  ID: {curr_id}, ISO: {iso}, Factor: {factor}, Symbol: {symbol}, IsDefault: {is_default}")
        if is_default:
            print(f"    >>> СИСТЕМНАЯ ВАЛЮТА (isSystemDefault=true): {curr_id}")
        elif factor == 1.0:
            print(f"    >>> Валюта с factor=1.0 (вероятно системная): {curr_id}")
except Exception as e:
    print(f"Валюты недоступны: {e}")

print("\n=== Step 4: Текущая системная валюта (через get_system_currency_id) ===")
try:
    sys_curr = client.get_system_currency_id()
    print(f"System Currency ID: {sys_curr}")
except Exception as e:
    print(f"Ошибка получения системной валюты: {e}")


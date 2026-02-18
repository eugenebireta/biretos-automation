"""
Полная проверка настроек Shopware: языки, валюты, Sales Channels
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

print("=" * 60)
print("ПОЛНАЯ ПРОВЕРКА НАСТРОЕК SHOPWARE")
print("=" * 60)

# 1. Проверка языков
print("\n1. ЯЗЫКИ В СИСТЕМЕ:")
print("-" * 60)
try:
    response = client._request("GET", "/api/language")
    languages = response.get("data", []) if isinstance(response, dict) else []
    print(f"Найдено языков: {len(languages)}")
    
    for lang in languages:
        lang_id = lang.get('id')
        try:
            lang_detail = client._request("GET", f"/api/language/{lang_id}")
            lang_data = lang_detail.get("data", {}) if isinstance(lang_detail, dict) else {}
            lang_attrs = lang_data.get("attributes", {})
            print(f"  - {lang_attrs.get('name')} ({lang_attrs.get('code')}) - ID: {lang_id}")
        except Exception as e:
            print(f"  - Ошибка получения деталей языка {lang_id}: {e}")
except Exception as e:
    print(f"Ошибка получения языков: {e}")

# 2. Проверка валют
print("\n2. ВАЛЮТЫ В СИСТЕМЕ:")
print("-" * 60)
try:
    response = client._request("GET", "/api/currency")
    currencies = response.get("data", []) if isinstance(response, dict) else []
    print(f"Найдено валют: {len(currencies)}")
    
    for curr in currencies:
        curr_id = curr.get('id')
        try:
            curr_detail = client._request("GET", f"/api/currency/{curr_id}")
            curr_data = curr_detail.get("data", {}) if isinstance(curr_detail, dict) else {}
            curr_attrs = curr_data.get("attributes", {})
            iso_code = curr_attrs.get('isoCode')
            factor = curr_attrs.get('factor')
            print(f"  - {curr_attrs.get('name')} ({iso_code}) - Factor: {factor} - ID: {curr_id}")
            if iso_code and iso_code.upper() == 'RUB':
                print(f"    ✓ Это RUB валюта!")
        except Exception as e:
            print(f"  - Ошибка получения деталей валюты {curr_id}: {e}")
except Exception as e:
    print(f"Ошибка получения валют: {e}")

# 3. Проверка Sales Channels
print("\n3. SALES CHANNELS:")
print("-" * 60)
try:
    sc_response = client._request("GET", "/api/sales-channel")
    sales_channels = sc_response.get("data", []) if isinstance(sc_response, dict) else []
    print(f"Найдено Sales Channels: {len(sales_channels)}")
    
    for sc in sales_channels:
        sc_id = sc.get('id')
        try:
            sc_detail = client._request("GET", f"/api/sales-channel/{sc_id}")
            sc_data = sc_detail.get("data", {}) if isinstance(sc_detail, dict) else {}
            sc_attrs = sc_data.get("attributes", {})
            
            currency_id = sc_attrs.get("currencyId")
            language_id = sc_attrs.get("languageId")
            sc_type = sc_attrs.get("typeId")
            
            print(f"\n  Sales Channel ID: {sc_id}")
            print(f"    Type ID: {sc_type}")
            print(f"    Language ID: {language_id}")
            print(f"    Currency ID: {currency_id}")
            
            # Детали языка
            if language_id:
                try:
                    lang_detail = client._request("GET", f"/api/language/{language_id}")
                    lang_data = lang_detail.get("data", {}) if isinstance(lang_detail, dict) else {}
                    lang_attrs = lang_data.get("attributes", {})
                    lang_name = lang_attrs.get('name')
                    lang_code = lang_attrs.get('code')
                    print(f"    Language: {lang_name} ({lang_code})")
                    if lang_code and lang_code.lower() in ['ru', 'ru-ru']:
                        print(f"      ✓ Это Russian язык!")
                except Exception as e:
                    print(f"    ⚠ Ошибка получения языка: {e}")
            
            # Детали валюты
            if currency_id:
                try:
                    curr_detail = client._request("GET", f"/api/currency/{currency_id}")
                    curr_data = curr_detail.get("data", {}) if isinstance(curr_detail, dict) else {}
                    curr_attrs = curr_data.get("attributes", {})
                    curr_name = curr_attrs.get('name')
                    curr_iso = curr_attrs.get('isoCode')
                    print(f"    Currency: {curr_name} ({curr_iso})")
                    if curr_iso and curr_iso.upper() == 'RUB':
                        print(f"      ✓ Это RUB валюта!")
                except Exception as e:
                    print(f"    ⚠ Ошибка получения валюты: {e}")
        except Exception as e:
            print(f"  ⚠ Ошибка получения деталей Sales Channel {sc_id}: {e}")
except Exception as e:
    print(f"Ошибка получения Sales Channels: {e}")

# 4. Проверка метода получения валюты из Sales Channel
print("\n4. ПРОВЕРКА МЕТОДА ПОЛУЧЕНИЯ ВАЛЮТЫ:")
print("-" * 60)
try:
    sales_channel_currency = client.get_sales_channel_currency_id()
    print(f"Валюта из Sales Channel: {sales_channel_currency}")
    
    if sales_channel_currency:
        curr_detail = client._request("GET", f"/api/currency/{sales_channel_currency}")
        curr_data = curr_detail.get("data", {}) if isinstance(curr_detail, dict) else {}
        curr_attrs = curr_data.get("attributes", {})
        print(f"  ISO Code: {curr_attrs.get('isoCode')}")
        print(f"  Name: {curr_attrs.get('name')}")
        if curr_attrs.get('isoCode') and curr_attrs.get('isoCode').upper() == 'RUB':
            print(f"  ✓ Всё правильно - используется RUB!")
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("ПРОВЕРКА ЗАВЕРШЕНА")
print("=" * 60)









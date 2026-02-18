"""
Установка валюты в Sales Channel через API
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

print("=== Установка валюты в Sales Channel ===")

system_currency_id = client.get_system_currency_id()
print(f"System Currency ID: {system_currency_id}")

try:
    # Получаем Sales Channels
    response = client._request("GET", "/api/sales-channel")
    sales_channels = response.get("data", []) if isinstance(response, dict) else []
    print(f"Найдено Sales Channels: {len(sales_channels)}")
    
    for sc in sales_channels:
        sc_id = sc.get('id')
        print(f"\nОбновляю Sales Channel: {sc_id}")
        
        # Пробуем обновить валюту в Sales Channel
        try:
            update_payload = {
                "currencyId": system_currency_id,
            }
            response = client._request("PATCH", f"/api/sales-channel/{sc_id}", json=update_payload)
            print(f"✓ Sales Channel обновлён: {sc_id}")
            print(f"  Response: {json.dumps(response, indent=2, ensure_ascii=False) if response else 'None'}")
        except Exception as e:
            print(f"✗ Ошибка обновления Sales Channel {sc_id}: {e}")
            
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()









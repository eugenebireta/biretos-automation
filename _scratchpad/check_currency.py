"""
Проверка валют в Shopware
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

print("=== System Currency ===")
sys_currency = client.get_system_currency_id()
print(f"System Currency ID: {sys_currency}")

print("\n=== All Currencies ===")
response = client._request("GET", "/api/currency")
if isinstance(response, dict) and "data" in response:
    for curr in response["data"]:
        print(f"ID: {curr.get('id')}, ISO: {curr.get('isoCode')}, Default: {curr.get('isSystemDefault')}")









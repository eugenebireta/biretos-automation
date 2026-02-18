"""
Проверка, может ли Shopware найти валюту по ISO коду EUR
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

print("=== Проверка валюты EUR ===")

try:
    # Пробуем найти EUR
    eur_id = client.get_currency_id("EUR")
    print(f"EUR Currency ID: {eur_id}")
    
    # Пробуем найти RUB
    rub_id = client.get_currency_id("RUB")
    print(f"RUB Currency ID: {rub_id}")
    
    if eur_id == rub_id:
        print(f"\n✓ EUR и RUB указывают на одну и ту же валюту: {eur_id}")
        print(f"  Это означает, что валюта была изменена с EUR на RUB")
    else:
        print(f"\n⚠ EUR и RUB - разные валюты")
        print(f"  EUR: {eur_id}")
        print(f"  RUB: {rub_id}")
        
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()









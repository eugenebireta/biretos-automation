"""
Прямая проверка visibility через GET /api/product-visibility/{id}.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json, ROOT

def main():
    config_path = ROOT / "config.json"
    config = load_json(config_path)
    
    shopware_config = ShopwareConfig(
        url=config["shopware"]["url"],
        access_key_id=config["shopware"]["access_key_id"],
        secret_access_key=config["shopware"]["secret_access_key"],
    )
    client = ShopwareClient(shopware_config)
    
    # Проверяем visibility напрямую
    visibility_id = "019b1384357e71d59e4943afa0d36a71"  # Из предыдущего вывода
    
    try:
        response = client._request("GET", f"/api/product-visibility/{visibility_id}")
        print("Visibility data:")
        import json
        print(json.dumps(response, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    main()









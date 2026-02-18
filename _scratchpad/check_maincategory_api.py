"""Проверка API для mainCategory"""
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

product_number = "498271735"
response = client._request("GET", "/api/product", params={"filter[productNumber]": product_number})
products = response.get("data", []) if isinstance(response, dict) else []

if products:
    product_id = products[0].get("id")
    
    # Проверяем структуру товара
    detail = client._request("GET", f"/api/product/{product_id}")
    detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
    attrs = detail_data.get("attributes", {})
    
    print("Поля товара, связанные с категориями:")
    for key in attrs.keys():
        if "category" in key.lower() or "main" in key.lower():
            print(f"  {key}: {attrs.get(key)}")
    
    # Проверяем relationships
    relationships = detail_data.get("relationships", {})
    print("\nRelationships:")
    for rel_name, rel_data in relationships.items():
        if "category" in rel_name.lower() or "main" in rel_name.lower():
            print(f"  {rel_name}: {rel_data}")
    
    # Пробуем получить main-categories
    try:
        mc_response = client._request("GET", f"/api/product/{product_id}/main-categories")
        print(f"\nMain Categories endpoint: {mc_response}")
    except Exception as e:
        print(f"\nMain Categories endpoint: {e}")









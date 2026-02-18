"""
Отладка: проверка категорий через API.
"""
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json, ROOT

def find_product_by_number(client: ShopwareClient, product_number: str) -> str | None:
    """Находит product ID по productNumber."""
    try:
        response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [{"field": "productNumber", "type": "equals", "value": product_number}],
                "limit": 1
            }
        )
        data = response.get("data", []) if isinstance(response, dict) else []
        if data:
            return data[0].get("id")
    except Exception as e:
        print(f"ERROR: Failed to find product: {e}")
    return None

def main():
    config_path = ROOT / "config.json"
    config = load_json(config_path)
    
    shopware_config = ShopwareConfig(
        url=config["shopware"]["url"],
        access_key_id=config["shopware"]["access_key_id"],
        secret_access_key=config["shopware"]["secret_access_key"],
    )
    client = ShopwareClient(shopware_config)
    
    product_number = "498271720"
    product_id = find_product_by_number(client, product_number)
    
    if not product_id:
        print(f"❌ Товар {product_number} не найден")
        return 1
    
    print(f"Product ID: {product_id}")
    
    # Получаем товар с associations для категорий
    print("\n1. GET /api/product/{id} (обычный запрос):")
    response1 = client._request("GET", f"/api/product/{product_id}")
    print(json.dumps(response1, indent=2, ensure_ascii=False)[:2000])
    
    print("\n2. GET /api/product/{id}?associations[categories][]=categories:")
    response2 = client._request("GET", f"/api/product/{product_id}", params={"associations[categories][]": "categories"})
    print(json.dumps(response2, indent=2, ensure_ascii=False)[:2000])
    
    print("\n3. Проверка через relationships:")
    product_data = response2.get("data", {}) if isinstance(response2, dict) else {}
    relationships = product_data.get("relationships", {})
    categories_rel = relationships.get("categories")
    if categories_rel:
        print(f"  Найдены relationships.categories: {categories_rel}")
        included = response2.get("included", [])
        print(f"  Included items: {len(included)}")
        for item in included:
            if item.get("type") == "category":
                print(f"    - Category: {item.get('id')} - {item.get('attributes', {}).get('name', 'N/A')}")
    else:
        print("  relationships.categories не найдены")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())









"""
Проверка категорий и медиа для созданных товаров.
"""
import sys
from pathlib import Path

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

def check_product(client: ShopwareClient, product_id: str):
    """Проверяет товар на наличие категорий и медиа."""
    try:
        # Получаем информацию о товаре
        product_response = client._request("GET", f"/api/product/{product_id}")
        product_data = product_response.get("data", {}) if isinstance(product_response, dict) else {}
        product_attrs = product_data.get("attributes", {})
        
        product_number = product_attrs.get("productNumber", "N/A")
        product_name = product_attrs.get("name", "N/A")
        
        print(f"\n{'='*60}")
        print(f"Товар: {product_number} - {product_name}")
        print(f"{'='*60}")
        
        # Проверяем категории
        categories = product_attrs.get("categories", [])
        if categories:
            print(f"✅ [OK] Категории найдены: {len(categories)}")
            for cat in categories[:5]:  # Показываем первые 5
                cat_id = cat.get("id", "N/A")
                print(f"   - Category ID: {cat_id}")
        else:
            print(f"❌ [FAIL] Категории отсутствуют")
        
        # Проверяем медиа
        media = product_attrs.get("media", [])
        if media:
            print(f"✅ [OK] Медиа найдено: {len(media)}")
            for m in media[:3]:  # Показываем первые 3
                m_id = m.get("mediaId", "N/A")
                print(f"   - Media ID: {m_id}")
        else:
            print(f"❌ [FAIL] Медиа отсутствует")
        
        # Проверяем cover
        cover_id = product_attrs.get("coverId")
        if cover_id:
            print(f"✅ [OK] Cover установлен: {cover_id}")
        else:
            print(f"⚠️  [WARNING] Cover не установлен")
        
        return True
        
    except Exception as e:
        print(f"❌ [ERROR] Ошибка при проверке: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    config_path = ROOT / "config.json"
    config = load_json(config_path)
    
    shopware_config = ShopwareConfig(
        url=config["shopware"]["url"],
        access_key_id=config["shopware"]["access_key_id"],
        secret_access_key=config["shopware"]["secret_access_key"],
    )
    client = ShopwareClient(shopware_config)
    
    # Проверяем созданные товары
    product_numbers = ["498271720", "498271735", "498271898"]
    
    success_count = 0
    for product_number in product_numbers:
        product_id = find_product_by_number(client, product_number)
        if not product_id:
            print(f"❌ [ERROR] Товар {product_number} не найден")
            continue
        
        if check_product(client, product_id):
            success_count += 1
    
    print(f"\n{'='*60}")
    print(f"Итого: {success_count}/{len(product_numbers)} товаров проверено")
    print(f"{'='*60}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())









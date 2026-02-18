"""
Тестирование привязки медиа к товару с использованием уже созданного медиа
"""
import sys
import json
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

print("=" * 60)
print("ТЕСТИРОВАНИЕ ПРИВЯЗКИ МЕДИА")
print("=" * 60)

# Получаем товар без медиа
print("\n1. Поиск товара без медиа...")
response = client._request("GET", "/api/product", params={"limit": 20})
products = response.get("data", []) if isinstance(response, dict) else []

product_id = None
for p in products:
    p_id = p.get("id")
    detail = client._request("GET", f"/api/product/{p_id}")
    detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
    attrs = detail_data.get("attributes", {})
    media = attrs.get("media", [])
    if not media:
        product_id = p_id
        product_number = attrs.get("productNumber", "N/A")
        print(f"  Найден товар без медиа: {product_number} (ID: {product_id[:16]}...)")
        break

if not product_id:
    print("  Все товары уже имеют медиа!")
    sys.exit(0)

# Получаем список медиа, которые были созданы
print("\n2. Поиск созданного медиа...")
media_response = client._request("GET", "/api/media", params={"limit": 5})
media_list = media_response.get("data", []) if isinstance(media_response, dict) else []

if not media_list:
    print("  Медиа не найдены!")
    sys.exit(0)

test_media_id = media_list[0].get("id")
print(f"  Используем медиа: {test_media_id[:16]}...")

# Тест 1: Формат {"media": [{"mediaId": media_id, "position": 0}]}
print(f"\n3. Тест 1: Формат {{'media': [{{'mediaId': media_id, 'position': 0}}]}}")
try:
    test_payload_1 = {
        "id": product_id,
        "media": [{"mediaId": test_media_id, "position": 0}]
    }
    print(f"  Payload: {json.dumps(test_payload_1, indent=2, ensure_ascii=False)}")
    result = client._request("PATCH", f"/api/product/{product_id}", json=test_payload_1)
    print(f"  ✓ Успешно! Ответ: {json.dumps(result, indent=2, ensure_ascii=False)[:200]}...")
    
    # Проверяем, что медиа привязалось
    detail = client._request("GET", f"/api/product/{product_id}")
    detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
    attrs = detail_data.get("attributes", {})
    media = attrs.get("media", [])
    print(f"  Проверка: медиа в товаре: {len(media)}")
    if media:
        print(f"  ✓ Медиа успешно привязано!")
        
except Exception as e:
    error_str = str(e)
    print(f"  ✗ Ошибка: {error_str[:500]}...")
    if "c1051bb4-d103-4f74-8988-acbcafc7fdc3" in error_str:
        print(f"  ⚠ Это та же ошибка, что и в основном скрипте!")
    # Пытаемся извлечь детали ошибки
    try:
        import re
        error_json = re.search(r'\{.*\}', error_str, re.DOTALL)
        if error_json:
            error_data = json.loads(error_json.group())
            print(f"\n  Детали ошибки:")
            print(json.dumps(error_data, indent=2, ensure_ascii=False))
    except:
        pass

# Если тест 1 не сработал, пробуем другие форматы
if "c1051bb4-d103-4f74-8988-acbcafc7fdc3" in str(e) if 'e' in locals() else False:
    # Тест 2: Формат {"productMedia": [{"mediaId": media_id}]}
    print(f"\n4. Тест 2: Формат {{'productMedia': [{{'mediaId': media_id}}]}}")
    try:
        test_payload_2 = {
            "id": product_id,
            "productMedia": [{"mediaId": test_media_id, "position": 0}]
        }
        print(f"  Payload: {json.dumps(test_payload_2, indent=2, ensure_ascii=False)}")
        result = client._request("PATCH", f"/api/product/{product_id}", json=test_payload_2)
        print(f"  ✓ Успешно!")
    except Exception as e2:
        error_str = str(e2)
        print(f"  ✗ Ошибка: {error_str[:500]}...")

print("\n" + "=" * 60)
print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
print("=" * 60)


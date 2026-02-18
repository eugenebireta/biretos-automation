"""
Диагностика проблемы с привязкой медиа к товарам
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
print("ДИАГНОСТИКА ПРОБЛЕМЫ С ПРИВЯЗКОЙ МЕДИА")
print("=" * 60)

# Получаем один товар для анализа
print("\n1. Получение товара для анализа...")
response = client._request("GET", "/api/product", params={"limit": 1})
products = response.get("data", []) if isinstance(response, dict) else []

if not products:
    print("Товары не найдены!")
    sys.exit(1)

product_id = products[0].get("id")
print(f"Товар ID: {product_id}")

# Получаем полную структуру товара
print("\n2. Получение полной структуры товара...")
try:
    detail = client._request("GET", f"/api/product/{product_id}")
    detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
    attrs = detail_data.get("attributes", {})
    
    print(f"\nСтруктура товара:")
    print(f"  - ID: {detail_data.get('id')}")
    print(f"  - Product Number: {attrs.get('productNumber')}")
    print(f"  - Name: {attrs.get('name', '')[:50]}...")
    
    # Проверяем медиа
    print(f"\n3. Анализ медиа:")
    media = attrs.get("media", [])
    print(f"  - Количество медиа: {len(media)}")
    
    if media:
        print(f"  - Формат первого медиа:")
        first_media = media[0] if isinstance(media, list) else {}
        print(json.dumps(first_media, indent=4, ensure_ascii=False))
    
    # Проверяем cover
    cover = attrs.get("cover")
    print(f"\n4. Анализ cover:")
    if cover:
        print(f"  - Cover есть: {json.dumps(cover, indent=4, ensure_ascii=False)}")
    else:
        print(f"  - Cover отсутствует")
    
    # Проверяем productMedia (если есть)
    product_media = attrs.get("productMedia", [])
    print(f"\n5. Анализ productMedia:")
    print(f"  - Количество productMedia: {len(product_media)}")
    if product_media:
        print(f"  - Формат первого productMedia:")
        first_pm = product_media[0] if isinstance(product_media, list) else {}
        print(json.dumps(first_pm, indent=4, ensure_ascii=False))
    
    # Сохраняем полную структуру для анализа
    output_file = Path(__file__).parent / "product_structure.json"
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(detail_data, f, indent=2, ensure_ascii=False)
    print(f"\n6. Полная структура сохранена в: {output_file}")
    
except Exception as e:
    print(f"Ошибка получения структуры товара: {e}")
    import traceback
    traceback.print_exc()

# Тестируем привязку медиа с разными форматами
print("\n" + "=" * 60)
print("ТЕСТИРОВАНИЕ РАЗНЫХ ФОРМАТОВ ПРИВЯЗКИ МЕДИА")
print("=" * 60)

# Создаем тестовое медиа
print("\n7. Создание тестового медиа...")
from uuid import uuid4
test_media_id = uuid4().hex

try:
    # Создаем медиа
    client._request("POST", "/api/media", json={"id": test_media_id})
    print(f"  ✓ Медиа создано: {test_media_id[:16]}...")
    
    # Загружаем тестовое изображение
    test_url = "https://via.placeholder.com/150"
    client._request("POST", f"/api/_action/media/{test_media_id}/upload", json={"url": test_url})
    print(f"  ✓ Медиа загружено")
    
    # Тест 1: Формат {"media": [{"id": media_id}]}
    print(f"\n8. Тест 1: Формат {{'media': [{{'id': media_id}}]}}")
    try:
        test_payload_1 = {
            "id": product_id,
            "media": [{"id": test_media_id}]
        }
        client._request("PATCH", f"/api/product/{product_id}", json=test_payload_1)
        print(f"  ✓ Успешно!")
    except Exception as e:
        error_str = str(e)
        print(f"  ✗ Ошибка: {error_str[:200]}...")
        if "c1051bb4-d103-4f74-8988-acbcafc7fdc3" in error_str:
            print(f"  ⚠ Это та же ошибка, что и в основном скрипте!")
            # Пытаемся получить полный текст
            if hasattr(e, '__dict__'):
                print(f"  Полный текст ошибки:")
                print(json.dumps(e.__dict__, indent=2, ensure_ascii=False, default=str))
    
    # Тест 2: Формат {"productMedia": [{"mediaId": media_id}]}
    print(f"\n9. Тест 2: Формат {{'productMedia': [{{'mediaId': media_id}}]}}")
    try:
        test_payload_2 = {
            "id": product_id,
            "productMedia": [{"mediaId": test_media_id, "position": 0}]
        }
        client._request("PATCH", f"/api/product/{product_id}", json=test_payload_2)
        print(f"  ✓ Успешно!")
    except Exception as e:
        error_str = str(e)
        print(f"  ✗ Ошибка: {error_str[:200]}...")
    
    # Тест 3: Формат с coverId отдельно
    print(f"\n10. Тест 3: Формат с coverId")
    try:
        test_payload_3 = {
            "id": product_id,
            "coverId": test_media_id
        }
        client._request("PATCH", f"/api/product/{product_id}", json=test_payload_3)
        print(f"  ✓ Успешно!")
    except Exception as e:
        error_str = str(e)
        print(f"  ✗ Ошибка: {error_str[:200]}...")
    
    # Удаляем тестовое медиа
    print(f"\n11. Удаление тестового медиа...")
    try:
        client._request("DELETE", f"/api/media/{test_media_id}")
        print(f"  ✓ Медиа удалено")
    except:
        pass
    
except Exception as e:
    print(f"Ошибка тестирования: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("ДИАГНОСТИКА ЗАВЕРШЕНА")
print("=" * 60)









"""Отладка mainCategoryId - проверка ответа API"""
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json
import requests

ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
config = load_json(ROOT / "config.json")

shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

product_number = "498271735"
main_category_id = "67c46b54a5944429ab54e64707dd6418"

print("=" * 60)
print("ОТЛАДКА mainCategoryId - ПРОВЕРКА ОТВЕТА API")
print("=" * 60)

# Получаем товар
response = client._request("GET", "/api/product", params={"filter[productNumber]": product_number})
products = response.get("data", []) if isinstance(response, dict) else []
product_id = products[0].get("id")

# Получаем текущие категории
detail = client._request("GET", f"/api/product/{product_id}", params={
    "associations[categories][]": "categories"
})
detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
relationships = detail_data.get("relationships", {})
categories_rel = relationships.get("categories", {})
categories_data = categories_rel.get("data", []) if isinstance(categories_rel, dict) else []
category_ids = [cat.get("id") for cat in categories_data]

# Пробуем обновить напрямую через requests для получения полного ответа
print(f"\n1. Прямой запрос к API...")
url = f"{config['shopware']['url']}/api/product/{product_id}"
headers = {
    "Authorization": f"Bearer {config['shopware']['access_key_id']}:{config['shopware']['secret_access_key']}",
    "Content-Type": "application/json"
}
payload = {
    "id": product_id,
    "categories": [{"id": cid} for cid in category_ids],
    "mainCategoryId": main_category_id
}

print(f"   URL: {url}")
print(f"   Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")

try:
    response = requests.patch(url, json=payload, headers=headers, verify=False, timeout=30)
    print(f"\n2. Ответ API:")
    print(f"   Status: {response.status_code}")
    print(f"   Headers: {dict(response.headers)}")
    
    if response.status_code == 204:
        print(f"   ✅ 204 No Content (успешно)")
    elif response.status_code == 200:
        print(f"   ✅ 200 OK")
        print(f"   Body: {response.text[:500]}")
    else:
        print(f"   ❌ Ошибка: {response.status_code}")
        print(f"   Body: {response.text[:1000]}")
    
    # Проверяем результат
    print(f"\n3. Проверка результата...")
    detail2 = client._request("GET", f"/api/product/{product_id}")
    detail_data2 = detail2.get("data", {}) if isinstance(detail2, dict) else {}
    attrs2 = detail_data2.get("attributes", {})
    new_main = attrs2.get("mainCategoryId")
    print(f"   mainCategoryId после обновления: {new_main if new_main else '❌ НЕТ'}")
    
except Exception as e:
    print(f"   ❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("=" * 60)









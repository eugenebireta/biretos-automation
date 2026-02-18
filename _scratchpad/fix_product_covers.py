"""
Проверка и установка cover images для товаров.
"""
import sys
from pathlib import Path
import time

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
print("ПРОВЕРКА И УСТАНОВКА COVER IMAGES")
print("=" * 60)

# Получаем все товары
print("\nПолучение товаров...")
all_products = []
limit = 100
offset = 0

while True:
    response = client._request("GET", "/api/product", params={"limit": limit, "offset": offset})
    products = response.get("data", []) if isinstance(response, dict) else []
    if not products:
        break
    all_products.extend(products)
    offset += limit
    if len(products) < limit:
        break

print(f"Найдено товаров: {len(all_products)}\n")

fixed = 0
skipped = 0
errors = 0

for idx, product in enumerate(all_products):
    product_id = product.get("id")
    attrs = product.get("attributes", {})
    product_number = attrs.get("productNumber", "N/A")
    
    cover_id = attrs.get("coverId")
    media = attrs.get("media", [])
    
    if cover_id:
        skipped += 1
        if idx < 5:  # Показываем первые 5 для примера
            print(f"[SKIP] {product_number}: cover уже установлен")
        continue
    
    if not media:
        skipped += 1
        if idx < 5:
            print(f"[SKIP] {product_number}: нет медиа")
        continue
    
    # Устанавливаем первый media как cover
    first_media = media[0]
    media_id = first_media.get("mediaId") or first_media.get("id")
    
    if not media_id:
        errors += 1
        print(f"[FAIL] {product_number}: не удалось получить mediaId")
        continue
    
    try:
        client._request("PATCH", f"/api/product/{product_id}", json={
            "coverId": media_id
        })
        fixed += 1
        print(f"[OK] {product_number}: cover установлен")
        
        # Небольшая задержка для избежания rate limiting
        if idx % 10 == 0:
            time.sleep(0.5)
    except Exception as e:
        errors += 1
        error_msg = str(e)[:100]
        print(f"[FAIL] {product_number}: {error_msg}")

print(f"\n" + "=" * 60)
print(f"✅ Исправлено: {fixed}")
print(f"⏭️  Пропущено: {skipped}")
print(f"❌ Ошибок: {errors}")
print("=" * 60)








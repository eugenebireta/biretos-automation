"""
Принудительное пересоздание связей товаров с медиа для отображения превьюшек.
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
print("ПРИНУДИТЕЛЬНОЕ ПЕРЕСОЗДАНИЕ СВЯЗЕЙ ТОВАРОВ С МЕДИА")
print("=" * 60)

# Получаем товары с медиа
print("\n1. Получение товаров с медиа...")
response = client._request("GET", "/api/product", params={
    "limit": 100,
    "associations[media][]": "media"
})
products = response.get("data", []) if isinstance(response, dict) else []
included = response.get("included", []) if isinstance(response, dict) else []

print(f"   Найдено товаров: {len(products)}")

# Создаём словарь медиа из included
media_dict = {}
for item in included:
    if item.get("type") == "media":
        media_id = item.get("id")
        media_dict[media_id] = item

updated = 0
skipped = 0
errors = 0

print("\n2. Обновление товаров...")
for idx, product in enumerate(products):
    product_id = product.get("id")
    attrs = product.get("attributes", {})
    product_number = attrs.get("productNumber", "N/A")
    
    # Получаем медиа из relationships
    relationships = product.get("relationships", {})
    media_rel = relationships.get("media")
    
    if not media_rel:
        skipped += 1
        continue
    
    media_data = media_rel.get("data", [])
    if not media_data:
        skipped += 1
        continue
    
    # Собираем медиа для обновления
    media_payload = []
    cover_id = attrs.get("coverId")
    first_media_id = None
    
    for m in media_data:
        media_id = m.get("id")
        if media_id:
            # Получаем position из included или используем индекс
            position = len(media_payload)
            media_payload.append({
                "mediaId": media_id,
                "position": position
            })
            if not first_media_id:
                first_media_id = media_id
    
    if not media_payload:
        skipped += 1
        continue
    
    # Убеждаемся, что cover установлен
    if not cover_id and first_media_id:
        cover_id = first_media_id
    
    # Обновляем товар с медиа
    try:
        update_payload = {
            "id": product_id,
            "media": media_payload
        }
        
        if cover_id:
            update_payload["coverId"] = cover_id
        
        client._request("PATCH", f"/api/product/{product_id}", json=update_payload)
        updated += 1
        print(f"   [OK] {product_number}: обновлено {len(media_payload)} медиа, cover: {cover_id[:16] if cover_id else 'N/A'}...")
        
        if (idx + 1) % 10 == 0:
            time.sleep(0.5)  # Небольшая задержка
            
    except Exception as e:
        errors += 1
        error_msg = str(e)[:100]
        print(f"   [FAIL] {product_number}: {error_msg}")

print(f"\n" + "=" * 60)
print(f"✅ Обновлено: {updated}")
print(f"⏭️  Пропущено: {skipped}")
print(f"❌ Ошибок: {errors}")
print("=" * 60)

# Очищаем кеш
print("\n3. Очистка кеша...")
import paramiko

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=ssh_username, password=ssh_password, timeout=10)
    
    command = f"docker exec {container_name} php bin/console cache:clear"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
    exit_status = stdout.channel.recv_exit_status()
    if exit_status == 0:
        print("   ✅ Кеш очищен")
    
    ssh.close()
except Exception as e:
    print(f"   ⚠️  Ошибка очистки кеша: {e}")

print("\n" + "=" * 60)
print("ОБНОВЛЕНИЕ ЗАВЕРШЕНО")
print("=" * 60)
print("\n💡 Проверьте каталог на сайте - превьюшки должны появиться.")
print("   Если нет - возможно, проблема в шаблоне каталога или настройках темы.")








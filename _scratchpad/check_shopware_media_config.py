"""
Проверка настроек медиа в Shopware и альтернативные способы генерации
"""
import paramiko
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json

host = "77.233.222.214"
username = "root"
password = "HuPtNj39"

print("=" * 60)
print("ПРОВЕРКА НАСТРОЕК МЕДИА В SHOPWARE")
print("=" * 60)

# Проверяем через API
ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
config = load_json(ROOT / "config.json")

shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

# Проверяем настройки через system-config
print("\n1. Проверка настроек медиа через API...")
try:
    # Пробуем получить настройки медиа
    config_response = client._request("GET", "/api/system-config", params={
        "domain": "core.media"
    })
    print(f"   Настройки медиа: {config_response}")
except Exception as e:
    print(f"   Ошибка получения настроек: {str(e)[:100]}")

# Проверяем через SSH
try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    print("\n[OK] Подключено к серверу")
    
    container_name = "shopware"
    
    # Проверяем настройки remote thumbnails
    print("\n2. Проверка настройки remote thumbnails...")
    command = "docker exec shopware php bin/console system:config:get core.media.enableRemoteThumbnails"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    output = stdout.read().decode()
    print(f"   Remote thumbnails: {output.strip() if output else 'не найдено'}")
    
    # Проверяем другие настройки медиа
    print("\n3. Проверка других настроек медиа...")
    command = "docker exec shopware php bin/console system:config:get core.media"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    output = stdout.read().decode()
    if output:
        print("   Настройки:")
        for line in output.split('\n')[:20]:
            if line.strip():
                print(f"     {line}")
    
    # Пробуем сгенерировать для конкретного медиа напрямую
    print("\n4. Попытка генерации для конкретного медиа...")
    # Получаем ID медиа
    media_response = client._request("GET", "/api/media", params={"limit": 1})
    media_list = media_response.get("data", []) if isinstance(media_response, dict) else []
    
    if media_list:
        test_media_id = media_list[0].get("id")
        print(f"   Тестовое медиа: {test_media_id[:16]}...")
        
        # Пробуем через консоль для конкретного медиа
        # Но команды для конкретного медиа может не быть, пробуем общий подход
        
        # Может быть нужно обновить медиа, чтобы Shopware пересоздал thumbnails
        print("\n5. Попытка обновления медиа для триггера генерации...")
        try:
            # Получаем детали медиа
            media_detail = client._request("GET", f"/api/media/{test_media_id}")
            media_data = media_detail.get("data", {}) if isinstance(media_detail, dict) else {}
            media_attrs = media_data.get("attributes", {})
            
            # Обновляем медиа (без изменений, просто триггер)
            update_payload = {
                "id": test_media_id,
                "alt": media_attrs.get("alt") or "Updated"
            }
            client._request("PATCH", f"/api/media/{test_media_id}", json=update_payload)
            print(f"   [OK] Медиа обновлено")
            
            # Проверяем thumbnails после обновления
            media_detail_after = client._request("GET", f"/api/media/{test_media_id}")
            media_data_after = media_detail_after.get("data", {}) if isinstance(media_detail_after, dict) else {}
            media_attrs_after = media_data_after.get("attributes", {})
            thumbnails_after = media_attrs_after.get("thumbnails", [])
            print(f"   Thumbnails после обновления: {len(thumbnails_after)}")
            
        except Exception as e:
            print(f"   [ERROR] Ошибка обновления: {str(e)[:100]}")
    
    ssh.close()
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)









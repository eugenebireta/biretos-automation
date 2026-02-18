"""
Проверка настроек thumbnail и альтернативная генерация
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
print("ПРОВЕРКА НАСТРОЕК THUMBNAIL")
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

# Получаем одно медиа для проверки
print("\n1. Получение медиа для проверки...")
media_response = client._request("GET", "/api/media", params={"limit": 1})
media_list = media_response.get("data", []) if isinstance(media_response, dict) else []

if media_list:
    media_id = media_list[0].get("id")
    print(f"   Медиа ID: {media_id[:16]}...")
    
    # Получаем детали медиа
    media_detail = client._request("GET", f"/api/media/{media_id}")
    media_detail_data = media_detail.get("data", {}) if isinstance(media_detail, dict) else {}
    media_attrs = media_detail_data.get("attributes", {})
    
    print(f"   File extension: {media_attrs.get('fileExtension', 'N/A')}")
    print(f"   MIME type: {media_attrs.get('mimeType', 'N/A')}")
    print(f"   Thumbnails: {len(media_attrs.get('thumbnails', []))}")
    
    # Пробуем сгенерировать thumbnail через API
    print(f"\n2. Попытка генерации thumbnail через API...")
    try:
        # Shopware может иметь endpoint для генерации thumbnail
        # Пробуем через _action endpoint
        result = client._request("POST", f"/api/_action/media/{media_id}/generate-thumbnails")
        print(f"   ✓ Генерация запущена: {result}")
    except Exception as e:
        error_str = str(e)
        print(f"   [ERROR] {error_str[:200]}...")
        
        # Пробуем через SSH с детальной информацией
        print(f"\n3. Генерация через SSH с детальным выводом...")
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host, username=username, password=password, timeout=10)
            
            # Проверяем настройки thumbnail
            print("   Проверка настроек thumbnail...")
            command = "docker exec shopware php bin/console system:config:get core.media"
            stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
            config_output = stdout.read().decode()
            if config_output:
                print(f"   Настройки медиа:")
                for line in config_output.split('\n')[:20]:
                    if line.strip():
                        print(f"     {line}")
            
            # Пробуем сгенерировать для конкретного медиа
            print(f"\n   Генерация для медиа {media_id}...")
            command = f"docker exec shopware php bin/console media:thumbnail:generate {media_id}"
            stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
            
            output = stdout.read().decode()
            errors = stderr.read().decode()
            
            if output:
                print(f"   Вывод: {output[:200]}...")
            if errors:
                print(f"   Ошибки: {errors[:200]}...")
            
            ssh.close()
            
        except Exception as e2:
            print(f"   ✗ Ошибка SSH: {e2}")

print("\n" + "=" * 60)


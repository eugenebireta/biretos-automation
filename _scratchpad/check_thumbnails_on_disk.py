"""
Проверка наличия thumbnails на диске
"""
import paramiko

host = "77.233.222.214"
username = "root"
password = "HuPtNj39"

print("=" * 60)
print("ПРОВЕРКА THUMBNAILS НА ДИСКЕ")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    print("[OK] Подключено")
    
    container_name = "shopware"
    
    # Проверяем директорию с thumbnails
    print("\n1. Проверка директории thumbnails...")
    command = "docker exec shopware ls -la /var/www/html/public/media/thumbnail/ 2>/dev/null | head -20"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    output = stdout.read().decode()
    
    if output:
        print("   Содержимое директории thumbnails:")
        for line in output.split('\n')[:15]:
            if line.strip():
                print(f"     {line}")
    else:
        print("   Директория пуста или не существует")
    
    # Проверяем количество файлов thumbnails
    print("\n2. Подсчёт файлов thumbnails...")
    command = "docker exec shopware find /var/www/html/public/media/thumbnail -type f 2>/dev/null | wc -l"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    count = stdout.read().decode().strip()
    print(f"   Найдено файлов thumbnails: {count}")
    
    # Проверяем конкретный медиа файл
    print("\n3. Проверка конкретного медиа...")
    # Получаем ID медиа через API
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
    
    media_response = client._request("GET", "/api/media", params={"limit": 1})
    media_list = media_response.get("data", []) if isinstance(media_response, dict) else []
    
    if media_list:
        test_media_id = media_list[0].get("id")
        print(f"   Тестовое медиа: {test_media_id}")
        
        # Ищем thumbnails для этого медиа
        command = f"docker exec shopware find /var/www/html/public/media/thumbnail -name '*{test_media_id}*' 2>/dev/null"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        thumbnails = stdout.read().decode()
        
        if thumbnails.strip():
            print(f"   Найдено thumbnails для этого медиа:")
            for line in thumbnails.split('\n'):
                if line.strip():
                    print(f"     {line}")
        else:
            print(f"   Thumbnails для этого медиа не найдены на диске")
    
    ssh.close()
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)









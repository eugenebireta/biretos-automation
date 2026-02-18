"""
Проверка состояния media в базе данных
"""
import paramiko

host = "77.233.222.214"
username = "root"
password = "HuPtNj39"

print("=" * 60)
print("ПРОВЕРКА MEDIA В БАЗЕ ДАННЫХ")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    print("[OK] Подключено")
    
    container_name = "shopware"
    
    # Получаем информацию о базе данных
    print("\n1. Проверка подключения к БД...")
    command = "docker exec shopware php bin/console debug:container | grep -i database"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    db_info = stdout.read().decode()
    
    # Пробуем получить данные из media_thumbnail
    print("\n2. Проверка таблицы media_thumbnail...")
    command = "docker exec shopware mysql -u shopware -pshopware shopware -e 'SELECT COUNT(*) as count FROM media_thumbnail;' 2>&1"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    output = stdout.read().decode()
    errors = stderr.read().decode()
    
    if output:
        print(f"   Записей в media_thumbnail: {output.strip()}")
    if errors and "Warning" not in errors:
        print(f"   Ошибки: {errors[:200]}")
    
    # Проверяем конкретные медиа
    print("\n3. Проверка конкретных медиа...")
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
    
    media_response = client._request("GET", "/api/media", params={"limit": 3})
    media_list = media_response.get("data", []) if isinstance(media_response, dict) else []
    
    for media in media_list:
        media_id = media.get("id")
        attrs = media.get("attributes", {})
        file_name = attrs.get("fileName", "N/A")
        
        print(f"\n   Медиа: {file_name} ({media_id[:16]}...)")
        
        # Проверяем thumbnails в БД
        command = f"docker exec shopware mysql -u shopware -pshopware shopware -e \"SELECT id, media_id, width, height FROM media_thumbnail WHERE media_id = '{media_id}' LIMIT 5;\" 2>&1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        thumbnails = stdout.read().decode()
        
        if thumbnails.strip() and "id" in thumbnails:
            print(f"     Thumbnails в БД:")
            for line in thumbnails.split('\n'):
                if line.strip() and "id" not in line.lower():
                    print(f"       {line}")
        else:
            print(f"     [WARNING] Нет thumbnails в БД!")
        
        # Проверяем состояние media
        command = f"docker exec shopware mysql -u shopware -pshopware shopware -e \"SELECT id, file_name, mime_type, file_size, uploaded_at FROM media WHERE id = '{media_id}';\" 2>&1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        media_info = stdout.read().decode()
        
        if media_info.strip():
            print(f"     Информация о медиа:")
            for line in media_info.split('\n'):
                if line.strip():
                    print(f"       {line}")
    
    # Проверяем, есть ли записи в media_thumbnail_size
    print("\n4. Проверка thumbnail sizes в БД...")
    command = "docker exec shopware mysql -u shopware -pshopware shopware -e 'SELECT id, width, height FROM media_thumbnail_size;' 2>&1"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    sizes = stdout.read().decode()
    
    if sizes.strip():
        print("   Thumbnail sizes:")
        for line in sizes.split('\n'):
            if line.strip():
                print(f"     {line}")
    
    ssh.close()
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)









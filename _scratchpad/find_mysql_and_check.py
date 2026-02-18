"""
Поиск MySQL контейнера и проверка media
"""
import paramiko

host = "77.233.222.214"
username = "root"
password = "HuPtNj39"

print("=" * 60)
print("ПОИСК MYSQL И ПРОВЕРКА MEDIA")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    print("[OK] Подключено")
    
    # Ищем MySQL контейнер
    print("\n1. Поиск MySQL контейнера...")
    command = "docker ps --format '{{.Names}}' | grep -i mysql"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    mysql_containers = stdout.read().decode().strip().split('\n')
    
    if mysql_containers and mysql_containers[0]:
        mysql_container = mysql_containers[0].strip()
        print(f"   Найден контейнер: {mysql_container}")
    else:
        # Пробуем найти через docker-compose или проверить, может MySQL в том же контейнере
        print("   MySQL контейнер не найден отдельно, проверяем shopware контейнер...")
        mysql_container = None
    
    # Проверяем через shopware контейнер с правильными параметрами
    print("\n2. Проверка через shopware контейнер...")
    
    # Получаем credentials из .env или используем стандартные
    # Пробуем стандартные credentials
    db_commands = [
        ("shopware", "shopware", "shopware"),
        ("root", "root", "shopware"),
        ("shopware", "shopware", "shopware"),
    ]
    
    for db_user, db_pass, db_name in db_commands:
        print(f"\n   Пробуем: user={db_user}, db={db_name}")
        command = f"docker exec shopware mysql -h 127.0.0.1 -u {db_user} -p{db_pass} {db_name} -e 'SELECT COUNT(*) FROM media_thumbnail;' 2>&1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        output = stdout.read().decode()
        errors = stderr.read().decode()
        
        if "ERROR" not in output and "count" in output.lower():
            print(f"   [SUCCESS] Подключение работает!")
            print(f"   Результат: {output.strip()}")
            
            # Теперь проверяем конкретные медиа
            print("\n3. Проверка thumbnails для конкретных медиа...")
            
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
            
            media_response = client._request("GET", "/api/media", params={"limit": 2})
            media_list = media_response.get("data", []) if isinstance(media_response, dict) else []
            
            for media in media_list:
                media_id = media.get("id")
                attrs = media.get("attributes", {})
                file_name = attrs.get("fileName", "N/A")
                
                print(f"\n   Медиа: {file_name}")
                
                # Проверяем thumbnails
                command = f"docker exec shopware mysql -h 127.0.0.1 -u {db_user} -p{db_pass} {db_name} -e \"SELECT id, width, height FROM media_thumbnail WHERE media_id = '{media_id}' LIMIT 3;\" 2>&1"
                stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
                thumbnails = stdout.read().decode()
                
                if thumbnails.strip() and "id" in thumbnails.lower():
                    print(f"     Thumbnails в БД:")
                    for line in thumbnails.split('\n'):
                        if line.strip() and "id" not in line.lower() and "width" not in line.lower():
                            print(f"       {line}")
                else:
                    print(f"     [WARNING] Нет thumbnails в БД!")
            
            break
        elif "Access denied" in errors or "Access denied" in output:
            print(f"   [SKIP] Неверные credentials")
        else:
            print(f"   [ERROR] {errors[:100] if errors else output[:100]}")
    
    ssh.close()
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)









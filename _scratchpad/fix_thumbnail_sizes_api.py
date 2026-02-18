"""Исправление проблемы с thumbnail sizes через Shopware API"""
import sys
from pathlib import Path
import paramiko
import uuid

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

# Параметры SSH
host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

print("=" * 60)
print("ИСПРАВЛЕНИЕ THUMBNAIL SIZES ЧЕРЕЗ API")
print("=" * 60)

# ШАГ 1: Проверка существования thumbnail sizes
print("\n1. Проверка существования thumbnail sizes...")
try:
    # Пробуем получить через API
    response = client._request("GET", "/api/thumbnail-size")
    sizes_data = response.get("data", []) if isinstance(response, dict) else []
    
    if sizes_data:
        print(f"   ✅ Найдено thumbnail sizes: {len(sizes_data)}")
        print("   Существующие размеры:")
        for size in sizes_data:
            attrs = size.get("attributes", {})
            width = attrs.get("width", "N/A")
            height = attrs.get("height", "N/A")
            print(f"     {width}x{height}")
        skip_creation = True
    else:
        print("   ⚠️ Thumbnail sizes отсутствуют, нужно создать")
        skip_creation = False
except Exception as e:
    print(f"   ⚠️ Ошибка проверки через API: {e}")
    print("   Пробуем через БД...")
    
    # Fallback: проверка через БД
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=ssh_username, password=ssh_password, timeout=30)
    
    try:
        command = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(*) FROM thumbnail_size;\" 2>&1 | grep -v Warning | tail -1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        output = stdout.read().decode().strip()
        
        if output and output.isdigit():
            count = int(output)
            if count > 0:
                print(f"   ✅ Найдено thumbnail sizes в БД: {count}")
                skip_creation = True
            else:
                print("   ⚠️ Thumbnail sizes отсутствуют")
                skip_creation = False
        else:
            skip_creation = False
    except Exception as e2:
        print(f"   ⚠️ Ошибка проверки БД: {e2}")
        skip_creation = False
    finally:
        ssh.close()

# ШАГ 2: Создание стандартных thumbnail sizes
if not skip_creation:
    print("\n2. Создание стандартных thumbnail sizes...")
    
    thumbnail_sizes = [
        {"width": 192, "height": 192, "keepAspect": True, "description": "catalog preview"},
        {"width": 400, "height": 400, "keepAspect": True, "description": "small listing"},
        {"width": 800, "height": 800, "keepAspect": True, "description": "product detail"},
        {"width": 1920, "height": 1920, "keepAspect": True, "description": "zoom / fullscreen"},
    ]
    
    print(f"   Создаём {len(thumbnail_sizes)} размеров через Sync API...")
    
    created_count = 0
    for size in thumbnail_sizes:
        try:
            # Создаём через Sync API
            size_id = str(uuid.uuid4()).replace('-', '')
            
            sync_body = {
                "thumbnail_size": {
                    "entity": "thumbnail_size",
                    "action": "upsert",
                    "payload": [
                        {
                            "id": size_id,
                            "width": size["width"],
                            "height": size["height"],
                        }
                    ]
                }
            }
            
            response = client._request("POST", "/api/_action/sync", json=sync_body)
            
            if response:
                print(f"   ✅ Создан размер: {size['width']}x{size['height']} ({size['description']})")
                created_count += 1
            else:
                print(f"   ⚠️ Не удалось создать {size['width']}x{size['height']}")
                
        except Exception as e:
            error_msg = str(e)
            if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
                print(f"   [SKIP] Размер {size['width']}x{size['height']} уже существует")
            else:
                print(f"   ❌ Ошибка создания {size['width']}x{size['height']}: {error_msg[:100]}")
    
    print(f"\n   Итого создано: {created_count} из {len(thumbnail_sizes)}")

# ШАГ 3: Очистка кеша
print("\n3. Очистка кеша...")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=ssh_username, password=ssh_password, timeout=30)

try:
    commands = [
        ("cache:clear", "Очистка кеша"),
    ]
    
    for cmd, desc in commands:
        print(f"   {desc}...")
        command = f"docker exec {container_name} php bin/console {cmd} 2>&1"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
        output = stdout.read().decode()
        
        if "ERROR" not in output and "Exception" not in output:
            print(f"   ✅ {desc} выполнено")
        else:
            # Показываем только первые строки ошибки
            error_lines = [line for line in output.split('\n') if 'ERROR' in line or 'Exception' in line][:3]
            if error_lines:
                print(f"   ⚠️ Предупреждения: {error_lines[0][:100]}")
    
    # Пробуем обновить индексы DAL (если команда доступна)
    try:
        command_dal = f"docker exec {container_name} php bin/console dal:refresh:index 2>&1"
        stdin_dal, stdout_dal, stderr_dal = ssh.exec_command(command_dal, timeout=60)
        output_dal = stdout_dal.read().decode()
        if "ERROR" not in output_dal and "Exception" not in output_dal:
            print(f"   ✅ Обновление индексов DAL выполнено")
    except:
        print(f"   ⚠️ Команда dal:refresh:index недоступна, пропускаем")
        
except Exception as e:
    print(f"   ⚠️ Ошибка очистки кеша: {e}")

# ШАГ 4: Генерация thumbnails
print("\n4. Генерация thumbnails...")
try:
    command = f"docker exec {container_name} php bin/console media:generate-thumbnails 2>&1"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=600)
    
    output_lines = []
    for line in iter(stdout.readline, ""):
        if line:
            line = line.rstrip()
            if "Generated" in line or "Skipped" in line or "Errors" in line or "Action" in line or "Number" in line or "---" in line or "%" in line:
                print(f"   {line}")
            output_lines.append(line)
    
    exit_status = stdout.channel.recv_exit_status()
    
    if exit_status == 0:
        output_text = "\n".join(output_lines)
        if "Generated" in output_text:
            for line in output_lines:
                if "Generated" in line and "Number" not in line:
                    print(f"   ✅ {line.strip()}")
        if "Skipped" in output_text:
            for line in output_lines:
                if "Skipped" in line and "Number" not in line:
                    print(f"   ⚠️ {line.strip()}")
    else:
        print(f"   ⚠️ Команда завершилась с кодом: {exit_status}")
        
except Exception as e:
    print(f"   ❌ Ошибка генерации: {e}")

# ШАГ 5: Проверка результата
print("\n5. Проверка результата...")

# 5.1 Проверка через API
print("   5.1. Проверка thumbnail sizes через API...")
try:
    response = client._request("GET", "/api/thumbnail-size")
    sizes_data = response.get("data", []) if isinstance(response, dict) else []
    
    if sizes_data:
        print(f"   ✅ Найдено thumbnail sizes: {len(sizes_data)}")
        print("   Размеры:")
        for size in sizes_data:
            attrs = size.get("attributes", {})
            width = attrs.get("width", "N/A")
            height = attrs.get("height", "N/A")
            print(f"     {width}x{height}")
    else:
        print("   ⚠️ Thumbnail sizes не найдены через API")
        
except Exception as e:
    print(f"   ⚠️ Ошибка проверки API: {e}")

# 5.2 Проверка файлов на диске
print("   5.2. Проверка файлов thumbnails на диске...")
try:
    command = f"docker exec {container_name} find public/media -type f \\( -name '*.jpg' -o -name '*.png' \\) 2>/dev/null | grep thumbnail | wc -l"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
    output = stdout.read().decode().strip()
    
    if output and output.isdigit():
        count = int(output)
        if count > 0:
            print(f"   ✅ Найдено thumbnail файлов: {count}")
            
            # Показываем примеры
            command_examples = f"docker exec {container_name} find public/media -type f \\( -name '*.jpg' -o -name '*.png' \\) 2>/dev/null | grep thumbnail | head -5"
            stdin_ex, stdout_ex, stderr_ex = ssh.exec_command(command_examples, timeout=30)
            examples = [line.rstrip() for line in stdout_ex if line.rstrip()]
            if examples:
                print("   Примеры файлов:")
                for ex in examples:
                    print(f"     {ex}")
        else:
            print("   ⚠️ Thumbnail файлы не найдены на диске")
    else:
        print("   ⚠️ Не удалось подсчитать thumbnail файлы")
        
except Exception as e:
    print(f"   ⚠️ Ошибка проверки: {e}")

ssh.close()

print("\n" + "=" * 60)
print("ИСПРАВЛЕНИЕ ЗАВЕРШЕНО")
print("=" * 60)









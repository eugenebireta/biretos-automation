"""
Добавление медиа (фото) к товарам через Media API
Использует золотой стандарт Shopware: POST /api/media → POST /api/_action/media/{id}/upload

КРИТИЧНО: coverId должен указывать на product_media.id, а НЕ на media.id!
Иначе category listing не покажет превью (будет серый placeholder).
Карточка товара может работать, но листинг - нет.
"""
import sys
from pathlib import Path
from uuid import uuid4
from typing import Optional, List, Dict
import time

sys.path.insert(0, str(Path(__file__).parent.parent / "insales_to_shopware_migration" / "src"))

from clients import ShopwareClient, ShopwareConfig
from import_utils import load_json, split_pipe, save_json
import csv

ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
config = load_json(ROOT / "config.json")

shop_cfg = ShopwareConfig(
    url=config["shopware"]["url"],
    access_key_id=config["shopware"]["access_key_id"],
    secret_access_key=config["shopware"]["secret_access_key"],
)
client = ShopwareClient(shop_cfg)

print("=" * 60)
print("ДОБАВЛЕНИЕ МЕДИА К ТОВАРАМ")
print("=" * 60)

def create_media_from_url(url: str, max_retries: int = 3) -> Optional[str]:
    """
    Создает медиа из URL с retry (золотой стандарт Shopware)
    
    Шаги:
    1. POST /api/media - создание media
    2. POST /api/_action/media/{id}/upload - загрузка по URL
    3. Возврат mediaId или None при ошибке
    """
    media_id = uuid4().hex
    
    for attempt in range(max_retries):
        try:
            # 1. Создаем media
            client._request("POST", "/api/media", json={"id": media_id})
            
            # 2. Загружаем через URL (Shopware сам скачает)
            client._request("POST", f"/api/_action/media/{media_id}/upload", json={"url": url})
            
            return media_id
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 1 * (attempt + 1)  # Exponential backoff: 1s, 2s, 3s
                time.sleep(wait_time)
                continue
            # Все попытки исчерпаны
            return None
    return None

# Читаем CSV
print("\nЧтение CSV...")
csv_data = {}
csv_path = ROOT / "output" / "products_import.csv"
with csv_path.open("r", encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        product_number = row.get("productNumber")
        if product_number:
            csv_data[product_number] = row

print(f"Загружено из CSV: {len(csv_data)} товаров")

# Получаем товары через пагинацию
print("\nПолучение товаров из Shopware...")
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

print(f"Всего товаров: {len(all_products)}")

# Обрабатываем товары
print("\n" + "=" * 60)
print("НАЧАЛО ДОБАВЛЕНИЯ МЕДИА")
print("=" * 60)

added = 0
skipped = 0
errors = []
failed_urls: List[Dict[str, str]] = []
media_success = 0
media_failed = 0
start_time = time.time()

for idx, product in enumerate(all_products, 1):
    product_id = product.get("id")
    
    try:
        # Получаем детали товара
        detail = client._request("GET", f"/api/product/{product_id}")
        detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
        attrs = detail_data.get("attributes", {})
        
        product_number = attrs.get("productNumber")
        if not product_number:
            skipped += 1
            continue
        
        # Проверяем, есть ли уже медиа
        existing_media = attrs.get("media", [])
        if existing_media:
            skipped += 1
            if idx % 100 == 0:
                print(f"[{idx}/{len(all_products)}] Пропущен (уже есть медиа): {product_number}")
            continue
        
        # Получаем данные из CSV
        csv_row = csv_data.get(product_number)
        if not csv_row:
            skipped += 1
            continue
        
        # Получаем URL изображений
        image_urls = split_pipe(csv_row.get("imageUrls") or "")
        if not image_urls:
            skipped += 1
            continue
        
        # Создаем медиа и привязываем к товару (золотой стандарт Shopware)
        media_items = []
        for idx, url in enumerate(image_urls[:5]):  # Максимум 5 изображений
            media_id = create_media_from_url(url)
            if media_id:
                # Shopware требует "mediaId", а не "id" для привязки медиа к товару
                media_items.append({
                    "mediaId": media_id,
                    "position": idx
                })
                media_success += 1
                print(f"      [OK] {product_number} -> {url[:60]}... -> mediaId: {media_id[:16]}...")
            else:
                media_failed += 1
                failed_urls.append({"product": product_number, "url": url})
                print(f"      [FAIL] {product_number} -> {url[:60]}... -> ошибка загрузки")
        
        if media_items:
            # Обновляем товар с медиа (БЕЗ coverId - установим после получения product_media.id)
            update_payload = {
                "id": product_id,
                "media": media_items
            }
            client._request("PATCH", f"/api/product/{product_id}", json=update_payload)
            
            # КРИТИЧНО: coverId должен указывать на product_media.id, а НЕ на media.id!
            # Получаем созданные product_media записи через GET с ассоциацией
            try:
                product_detail = client._request("GET", f"/api/product/{product_id}", params={
                    "associations[media][]": ""
                })
                product_data = product_detail.get("data", {}) if isinstance(product_detail, dict) else {}
                product_attrs = product_data.get("attributes", {})
                
                # Извлекаем коллекцию media (это product_media записи)
                media_collection = product_attrs.get("media", [])
                if media_collection and len(media_collection) > 0:
                    # Первая запись product_media - её id используем для coverId
                    first_product_media = media_collection[0]
                    product_media_id = first_product_media.get("id")
                    
                    if product_media_id:
                        # Устанавливаем coverId = product_media.id (НЕ media.id!)
                        cover_payload = {
                            "id": product_id,
                            "coverId": product_media_id
                        }
                        client._request("PATCH", f"/api/product/{product_id}", json=cover_payload)
                        print(f"      [OK] {product_number}: coverId установлен (product_media.id = {product_media_id[:16]}...)")
                    else:
                        print(f"      [WARNING] {product_number}: не удалось получить product_media.id")
                else:
                    print(f"      [WARNING] {product_number}: коллекция media пуста после привязки")
            except Exception as e:
                error_msg = str(e)[:100]
                print(f"      [WARNING] {product_number}: ошибка установки coverId: {error_msg}")
            
            added += 1
            
            if idx % 50 == 0:
                elapsed = time.time() - start_time
                rate = idx / elapsed if elapsed > 0 else 0
                remaining = (len(all_products) - idx) / rate if rate > 0 else 0
                print(f"[{idx}/{len(all_products)}] Добавлено медиа: {added}, Пропущено: {skipped}, Ошибок: {len(errors)} | "
                      f"Медиа: успешно {media_success}, ошибок {media_failed} | "
                      f"Скорость: {rate:.1f} товаров/сек | Осталось: {remaining:.0f} сек")
        else:
            skipped += 1
    
    except Exception as e:
        error_msg = f"Ошибка обработки {product_id}: {str(e)[:100]}"
        errors.append(error_msg)
        if idx % 100 == 0:
            print(f"[{idx}/{len(all_products)}] ERROR: {error_msg}")

elapsed = time.time() - start_time
print("\n" + "=" * 60)
print("ДОБАВЛЕНИЕ МЕДИА ЗАВЕРШЕНО")
print("=" * 60)
print(f"Всего обработано: {len(all_products)}")
print(f"Добавлено медиа: {added}")
print(f"Пропущено: {skipped}")
print(f"Ошибок: {len(errors)}")
print(f"Время выполнения: {elapsed:.1f} сек")
print(f"\nСтатистика медиа:")
print(f"  Успешно загружено: {media_success}")
print(f"  Ошибок загрузки: {media_failed}")
if media_success + media_failed > 0:
    success_rate = (media_success / (media_success + media_failed)) * 100
    print(f"  Процент успешности: {success_rate:.1f}%")

# Сохраняем лог битых URL для повторной обработки
if failed_urls:
    failed_path = ROOT.parent / "_scratchpad" / "failed_media_urls.json"
    save_json(failed_path, {
        "failed_count": len(failed_urls),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "failed_urls": failed_urls
    })
    print(f"\nБитые URL сохранены в: {failed_path}")
    print(f"Всего битых URL: {len(failed_urls)}")

if errors:
    print(f"\nПервые 10 ошибок:")
    for error in errors[:10]:
        print(f"  - {error}")

# ============================================================================
# ПОСТ-ШАГИ: Инициализация media types и генерация thumbnails
# ============================================================================
print("\n" + "=" * 60)
print("ПОСТ-ШАГИ: ИНИЦИАЛИЗАЦИЯ MEDIA TYPES И ГЕНЕРАЦИЯ THUMBNAILS")
print("=" * 60)

import paramiko

# Параметры SSH подключения
host = config.get("shopware", {}).get("ssh_host") or "77.233.222.214"
ssh_username = config.get("shopware", {}).get("ssh_username") or "root"
ssh_password = config.get("shopware", {}).get("ssh_password") or "HuPtNj39"
container_name = config.get("shopware", {}).get("container_name") or "shopware"

def check_media_without_type(ssh_client, container: str) -> int:
    """Проверяет количество медиа с media_type IS NULL"""
    try:
        command = f"docker exec {container} mysql -h 127.0.0.1 -u root -proot shopware -e \"SELECT COUNT(*) as count FROM media WHERE media_type IS NULL AND mime_type LIKE 'image/%';\" 2>&1 | grep -v Warning | tail -1"
        stdin, stdout, stderr = ssh_client.exec_command(command, timeout=30)
        output = stdout.read().decode().strip()
        
        if output and output.isdigit():
            return int(output)
        return 0
    except Exception as e:
        print(f"  [WARNING] Ошибка проверки media_type: {e}")
        return -1

def run_shopware_command(ssh_client, container: str, command: str, description: str, timeout: int = 600) -> tuple[bool, list[str]]:
    """Выполняет консольную команду Shopware через SSH и возвращает (успех, вывод)"""
    print(f"\n{description}...")
    print(f"  Команда: {command}")
    
    try:
        full_command = f"docker exec {container} php bin/console {command}"
        stdin, stdout, stderr = ssh_client.exec_command(full_command, timeout=timeout)
        
        # Читаем вывод в реальном времени
        output_lines = []
        error_lines = []
        
        for line in stdout:
            try:
                line_str = line.decode('utf-8', errors='ignore').strip()
                if line_str:
                    output_lines.append(line_str)
                    print(f"    {line_str}")
            except:
                pass
        
        for line in stderr:
            try:
                line_str = line.decode('utf-8', errors='ignore').strip()
                if line_str and "Warning" not in line_str:
                    error_lines.append(line_str)
            except:
                pass
        
        exit_status = stdout.channel.recv_exit_status()
        
        if exit_status == 0:
            print(f"  [OK] {description} завершена успешно")
            return True, output_lines
        else:
            print(f"  [ERROR] {description} завершилась с кодом {exit_status}")
            if error_lines:
                print(f"  Ошибки:")
                for err in error_lines[:5]:
                    print(f"    {err}")
            return False, output_lines
            
    except Exception as e:
        print(f"  [ERROR] Ошибка выполнения команды: {e}")
        return False, []

try:
    # Подключаемся к серверу
    print("\nПодключение к серверу...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=ssh_username, password=ssh_password, timeout=10)
    print(f"  [OK] Подключено к {host}")
    
    # ШАГ 1: Защитная проверка (guard)
    print("\n" + "-" * 60)
    print("ШАГ 1: ЗАЩИТНАЯ ПРОВЕРКА (GUARD)")
    print("-" * 60)
    
    media_without_type = check_media_without_type(ssh, container_name)
    
    if media_without_type > 0:
        print(f"  [WARNING] Найдено {media_without_type} медиа с media_type IS NULL")
        print(f"  [WARNING] Это нормально для медиа, загруженных через API")
        print(f"  [WARNING] Будет выполнена инициализация media types")
    elif media_without_type == 0:
        print(f"  [OK] Все медиа имеют установленный media_type")
    else:
        print(f"  [WARNING] Не удалось проверить media_type, продолжаем...")
    
    # ШАГ 2: Генерация media types
    print("\n" + "-" * 60)
    print("ШАГ 2: ГЕНЕРАЦИЯ MEDIA TYPES")
    print("-" * 60)
    
    media_types_success, _ = run_shopware_command(
        ssh, 
        container_name, 
        "media:generate-media-types",
        "Генерация media types",
        timeout=120
    )
    
    if not media_types_success:
        print("\n" + "=" * 60)
        print("[ERROR] Генерация media types не удалась!")
        print("Генерация thumbnails пропущена из-за ошибки.")
        print("=" * 60)
        ssh.close()
        exit(1)
    
    # ШАГ 3: Генерация thumbnails (только если media types успешно)
    print("\n" + "-" * 60)
    print("ШАГ 3: ГЕНЕРАЦИЯ THUMBNAILS")
    print("-" * 60)
    
    thumbnails_success, thumbnails_output = run_shopware_command(
        ssh,
        container_name,
        "media:generate-thumbnails",
        "Генерация thumbnails",
        timeout=600
    )
    
    if thumbnails_success:
        # Парсим вывод команды для статистики
        generated_count = 0
        skipped_count = 0
        errors_count = 0
        
        for line in thumbnails_output:
            # Ищем строки типа "Generated: 5", "Skipped: 10", "Errors: 0"
            line_lower = line.lower()
            if "generated:" in line_lower:
                try:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        generated_count = int(parts[1].strip().split()[0])
                except:
                    pass
            if "skipped:" in line_lower:
                try:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        skipped_count = int(parts[1].strip().split()[0])
                except:
                    pass
            if "errors:" in line_lower:
                try:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        errors_count = int(parts[1].strip().split()[0])
                except:
                    pass
        
        print(f"\n  Статистика генерации thumbnails:")
        print(f"    Generated: {generated_count}")
        print(f"    Skipped: {skipped_count}")
        print(f"    Errors: {errors_count}")
        
        if skipped_count > 0:
            print(f"  [INFO] {skipped_count} медиа пропущено - Shopware использует fallback (оригинальные изображения)")
        
        if errors_count > 0:
            print(f"  [WARNING] {errors_count} ошибок при генерации thumbnails")
        
        # Проверяем результат
        print("\nПроверка результата...")
        media_without_type_after = check_media_without_type(ssh, container_name)
        
        if media_without_type_after == 0:
            print(f"  [OK] Все медиа теперь имеют media_type")
        elif media_without_type_after > 0:
            print(f"  [WARNING] Осталось {media_without_type_after} медиа без media_type")
        else:
            print(f"  [INFO] Проверка результата не удалась")
        
        # Проверяем thumbnails на диске (правильный путь)
        print("\nПроверка thumbnails на диске...")
        # Shopware хранит thumbnails в структуре: /var/www/html/public/media/{folder1}/{folder2}/{folder3}/thumbnail/{size}/
        check_command = f"docker exec {container_name} find /var/www/html/public/media -type d -name thumbnail -exec find {{}} -type f \\; 2>/dev/null | wc -l"
        stdin, stdout, stderr = ssh.exec_command(check_command, timeout=30)
        thumb_count = stdout.read().decode().strip()
        if thumb_count.isdigit():
            thumb_count_int = int(thumb_count)
            if thumb_count_int > 0:
                print(f"  [OK] Найдено {thumb_count_int} файлов thumbnails на диске")
            else:
                print(f"  [INFO] Thumbnails не найдены на диске - Shopware использует fallback (оригинальные изображения)")
        else:
            print(f"  [INFO] Не удалось проверить количество thumbnails")
    
    # Очистка кеша
    print("\nОчистка кеша Shopware...")
    cache_success, _ = run_shopware_command(
        ssh,
        container_name,
        "cache:clear",
        "Очистка кеша",
        timeout=60
    )
    
    ssh.close()
    
    print("\n" + "=" * 60)
    print("ПОСТ-ШАГИ ЗАВЕРШЕНЫ")
    print("=" * 60)
    if media_types_success:
        # НЕ считаем Skipped ошибкой - Shopware использует fallback
        print("[SUCCESS] Media types инициализированы")
        if thumbnails_success:
            print("[INFO] Thumbnails: команда выполнена (Skipped не является ошибкой, используется fallback)")
        else:
            print("[WARNING] Thumbnails: команда не выполнена успешно")
    else:
        print("[ERROR] Пост-шаги не выполнены успешно")
        exit(1)
        
except Exception as e:
    print(f"\n[ERROR] Критическая ошибка при выполнении пост-шагов: {e}")
    import traceback
    traceback.print_exc()
    exit(1)


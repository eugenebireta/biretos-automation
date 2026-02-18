"""
Массовое исправление cover_id для товаров.
Восстанавливает корректные связи product.cover_id -> product_media.id
"""
import sys
import os
from pathlib import Path
import paramiko
import csv
import time

# Загружаем конфиг
ROOT = Path(__file__).parent.parent / "insales_to_shopware_migration"
sys.path.insert(0, str(ROOT / "src"))

from import_utils import load_json

config = load_json(ROOT / "config.json")

# Параметры подключения (из config.json или .env, с fallback)
host = config.get("shopware", {}).get("ssh_host") or os.getenv("SHOPWARE_SSH_HOST") or "77.233.222.214"
ssh_username = config.get("shopware", {}).get("ssh_username") or os.getenv("SHOPWARE_SSH_USER") or "root"
ssh_password = config.get("shopware", {}).get("ssh_password") or os.getenv("SHOPWARE_SSH_PASSWORD") or "HuPtNj39"
container_name = config.get("shopware", {}).get("container_name") or os.getenv("SHOPWARE_CONTAINER") or "shopware"

mysql_user = config.get("shopware", {}).get("mysql_user") or os.getenv("SHOPWARE_MYSQL_USER") or "root"
mysql_password = config.get("shopware", {}).get("mysql_password") or os.getenv("SHOPWARE_MYSQL_PASSWORD") or "root"

BATCH_SIZE = 50  # Обрабатываем батчами

print("=" * 60)
print("ИСПРАВЛЕНИЕ COVER_ID ДЛЯ ТОВАРОВ")
print("=" * 60)
print(f"Host: {host}")
print(f"Container: {container_name}")
print(f"Batch size: {BATCH_SIZE}")
print()

def run_sql(ssh_client, query: str) -> list:
    """Выполняет SQL запрос и возвращает список строк результатов"""
    # Экранируем только двойные кавычки, одинарные оставляем как есть
    escaped_query = query.replace('"', '\\"')
    cmd = f'docker exec {container_name} mysql -h 127.0.0.1 -u {mysql_user} -p{mysql_password} shopware -e "{escaped_query}" 2>&1 | grep -v Warning'
    
    try:
        stdin, stdout, stderr = ssh_client.exec_command(cmd, timeout=60)
        output = stdout.read().decode('utf-8', errors='ignore').strip()
        error = stderr.read().decode('utf-8', errors='ignore').strip()
        
        if error and "ERROR" in error:
            print(f"   ❌ SQL ошибка: {error}")
            return []
        
        if not output:
            return []
        
        lines = output.split('\n')
        if len(lines) <= 1:
            return []
        
        # Пропускаем заголовок, возвращаем данные
        # Разделяем по табуляции или множественным пробелам
        result = []
        for line in lines[1:]:
            if line.strip():
                # Разделяем по табуляции, если нет - по множественным пробелам
                parts = line.split('\t') if '\t' in line else line.split()
                if len(parts) >= 2:  # Минимум product_id и current_cover
                    result.append(parts)
        
        return result
    except Exception as e:
        print(f"   ❌ Исключение: {e}")
        return []

def update_cover_id(ssh_client, product_id: str, new_cover_id: str) -> bool:
    """Обновляет cover для товара через SQL (в Shopware 6 поле называется cover, не cover_id)"""
    # Конвертируем hex ID в binary для MySQL
    query = f"UPDATE product SET cover = UNHEX(REPLACE('{new_cover_id}', '-', '')) WHERE id = UNHEX(REPLACE('{product_id}', '-', ''));"
    
    try:
        escaped_query = query.replace('"', '\\"')
        cmd = f'docker exec {container_name} mysql -h 127.0.0.1 -u {mysql_user} -p{mysql_password} shopware -e "{escaped_query}" 2>&1 | grep -v Warning'
        stdin, stdout, stderr = ssh_client.exec_command(cmd, timeout=30)
        output = stdout.read().decode('utf-8', errors='ignore').strip()
        error = stderr.read().decode('utf-8', errors='ignore').strip()
        
        if error and "ERROR" in error:
            return False
        
        # UPDATE успешен, если нет ошибок
        return True
    except:
        return False

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=ssh_username, password=ssh_password, timeout=10)
    print(f"✅ Подключено к {host}\n")

    # ШАГ 1: Находим проблемные товары
    print("ШАГ 1: Поиск проблемных товаров...")
    
    # Товары, где cover указывает на media.id вместо product_media.id
    # Условия: p.cover IS NOT NULL AND pm.id IS NULL AND m.id IS NOT NULL
    find_problems_sql = "SELECT HEX(p.id) as product_id, HEX(p.cover) as current_cover, 'WRONG_MEDIA_ID' as problem_type FROM product p LEFT JOIN product_media pm ON pm.id = p.cover INNER JOIN media m ON m.id = p.cover WHERE p.cover IS NOT NULL AND pm.id IS NULL AND m.id IS NOT NULL ORDER BY HEX(p.id);"
    
    problem_products = run_sql(ssh, find_problems_sql)
    print(f"   Найдено проблемных товаров: {len(problem_products)}")
    
    if not problem_products:
        print("\n✅ Проблемных товаров не найдено!")
        ssh.close()
        sys.exit(0)
    
    # ШАГ 2: Для каждого проблемного товара ищем первую product_media
    print("\nШАГ 2: Поиск корректных product_media для каждого товара...")
    
    backup_data = []
    fixed_count = 0
    skipped_count = 0
    
    for idx, row in enumerate(problem_products, 1):
        if len(row) < 3:
            continue
            
        product_id = row[0].strip()
        current_cover_id = row[1].strip() if row[1].strip() != 'NULL' else None
        problem_type = row[2].strip()
        
        # Ищем первую product_media для этого товара (по position, затем created_at)
        find_pm_sql = f"""
        SELECT HEX(id) as product_media_id, position, HEX(media_id) as media_id
        FROM product_media
        WHERE product_id = UNHEX(REPLACE('{product_id}', '-', ''))
        ORDER BY position ASC, created_at ASC
        LIMIT 1;
        """
        
        pm_result = run_sql(ssh, find_pm_sql)
        
        if pm_result and len(pm_result[0]) >= 1:
            new_cover_id = pm_result[0][0].strip()
            
            # Обновляем cover
            if update_cover_id(ssh, product_id, new_cover_id):
                backup_data.append({
                    'product_id': product_id,
                    'old_cover': current_cover_id or 'NULL',
                    'new_cover': new_cover_id,
                    'problem_type': problem_type
                })
                fixed_count += 1
                
                if idx % 10 == 0:
                    print(f"   Обработано: {idx}/{len(problem_products)}, исправлено: {fixed_count}")
            else:
                print(f"   ⚠️  Не удалось обновить товар {product_id[:16]}...")
                skipped_count += 1
        else:
            # Нет product_media для этого товара - пропускаем
            backup_data.append({
                'product_id': product_id,
                'old_cover': current_cover_id or 'NULL',
                'new_cover': 'NOT_FOUND',
                'problem_type': problem_type
            })
            skipped_count += 1
            
            if idx % 10 == 0:
                print(f"   Обработано: {idx}/{len(problem_products)}, исправлено: {fixed_count}, пропущено: {skipped_count}")
        
        # Небольшая задержка между обновлениями
        if idx % BATCH_SIZE == 0:
            time.sleep(0.5)
    
    # ШАГ 3: Сохраняем бэкап
    print("\nШАГ 3: Сохранение бэкапа...")
    backup_path = Path(__file__).parent / "cover_fix_backup.csv"
    with backup_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=['product_id', 'old_cover', 'new_cover', 'problem_type'])
        writer.writeheader()
        writer.writerows(backup_data)
    print(f"   ✅ Бэкап сохранен: {backup_path}")
    print(f"   Всего записей: {len(backup_data)}")
    
    # ШАГ 4: Повторная диагностика
    print("\nШАГ 4: Повторная диагностика...")
    
    check_sql = """
    SELECT 
      COUNT(*) AS products_with_cover,
      SUM(pm.id IS NOT NULL) AS cover_points_to_product_media,
      SUM(pm.id IS NULL) AS cover_broken
    FROM product p
    LEFT JOIN product_media pm ON pm.id = p.cover
    WHERE p.cover IS NOT NULL;
    """
    
    check_result = run_sql(ssh, check_sql)
    
    if check_result and len(check_result[0]) >= 3:
        with_cover = check_result[0][0].strip()
        correct = check_result[0][1].strip()
        broken = check_result[0][2].strip()
        
        print(f"\n   Товары с cover_id: {with_cover}")
        print(f"   ✅ Корректные: {correct}")
        print(f"   ❌ Битые: {broken}")
    
    ssh.close()
    
    print("\n" + "=" * 60)
    print("ИТОГИ")
    print("=" * 60)
    print(f"Обработано товаров: {len(problem_products)}")
    print(f"Исправлено: {fixed_count}")
    print(f"Пропущено (нет product_media): {skipped_count}")
    print(f"Бэкап: {backup_path}")
    print("=" * 60)

except Exception as e:
    print(f"\n❌ Критическая ошибка: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


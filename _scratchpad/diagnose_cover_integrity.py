"""
Диагностика целостности связей coverId -> product_media.
Проверяет, правильно ли установлены coverId для товаров.
"""
import sys
import os
from pathlib import Path
import paramiko

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

print("=" * 60)
print("ДИАГНОСТИКА ЦЕЛОСТНОСТИ COVER ID")
print("=" * 60)
print(f"Host: {host}")
print(f"Container: {container_name}")
print()

def run_sql(query: str, description: str) -> str:
    """Выполняет SQL запрос и возвращает результат"""
    print(f"🔍 {description}")
    # Экранируем кавычки в SQL для shell
    escaped_query = query.replace('"', '\\"')
    cmd = f'docker exec {container_name} mysql -h 127.0.0.1 -u {mysql_user} -p{mysql_password} shopware -e "{escaped_query}" 2>&1 | grep -v Warning'
    
    try:
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
        output = stdout.read().decode('utf-8', errors='ignore').strip()
        error = stderr.read().decode('utf-8', errors='ignore').strip()
        
        if error and "ERROR" in error:
            print(f"   ❌ Ошибка: {error}")
            return ""
        
        # Убираем заголовки таблицы MySQL
        lines = output.split('\n')
        if len(lines) > 1:
            # Берем последнюю строку (результат)
            result = lines[-1].strip()
            print(f"   Результат: {result}")
            return result
        else:
            print(f"   Результат: {output}")
            return output
    except Exception as e:
        print(f"   ❌ Исключение: {e}")
        return ""

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=ssh_username, password=ssh_password, timeout=10)
    print(f"✅ Подключено к {host}\n")

    # 1. Статистика cover (в Shopware 6 поле называется cover, не cover_id)
    sql1 = """
    SELECT 
      COUNT(*) AS total,
      SUM(cover IS NOT NULL) AS with_cover,
      SUM(cover IS NULL) AS without_cover
    FROM product;
    """
    result1 = run_sql(sql1, "1. Статистика cover (total / with_cover / without_cover):")
    
    # 2. Целостность связи cover -> product_media
    sql2 = """
    SELECT 
      COUNT(*) AS products_with_cover,
      SUM(pm.id IS NOT NULL) AS cover_points_to_product_media,
      SUM(pm.id IS NULL) AS cover_broken
    FROM product p
    LEFT JOIN product_media pm ON pm.id = p.cover
    WHERE p.cover IS NOT NULL;
    """
    result2 = run_sql(sql2, "2. Целостность cover -> product_media (with_cover / correct / broken):")
    
    # 3. Общее количество product_media
    sql3 = "SELECT COUNT(*) AS total_product_media FROM product_media;"
    result3 = run_sql(sql3, "3. Общее количество записей в product_media:")
    
    # 4. Проверка: указывает ли cover ошибочно на media.id
    sql4 = """
    SELECT COUNT(*) AS wrong_link_to_media
    FROM product p
    JOIN media m ON m.id = p.cover
    WHERE p.cover IS NOT NULL;
    """
    result4 = run_sql(sql4, "4. Ошибочная связь cover -> media.id (вместо product_media.id):")

    ssh.close()
    
    print("\n" + "=" * 60)
    print("ИТОГОВАЯ ДИАГНОСТИКА")
    print("=" * 60)
    
    # Парсим результаты
    try:
        if result1:
            parts1 = result1.split('\t')
            if len(parts1) >= 3:
                total = parts1[0].strip()
                with_cover = parts1[1].strip()
                without_cover = parts1[2].strip()
                print(f"Всего товаров: {total}")
                print(f"  С cover_id: {with_cover}")
                print(f"  Без cover_id: {without_cover}")
    except:
        pass
    
    try:
        if result2:
            parts2 = result2.split('\t')
            if len(parts2) >= 3:
                with_cover = parts2[0].strip()
                correct = parts2[1].strip()
                broken = parts2[2].strip()
                print(f"\nТовары с cover_id: {with_cover}")
                print(f"  ✅ Корректные (cover -> product_media.id): {correct}")
                print(f"  ❌ Битые (cover не найден в product_media): {broken}")
                
                if broken and int(broken) > 0:
                    print(f"\n⚠️  ОБНАРУЖЕНА ПРОБЛЕМА: {broken} товаров с битым cover_id!")
    except:
        pass
    
    try:
        if result3:
            print(f"\nВсего записей в product_media: {result3}")
    except:
        pass
    
    try:
        if result4:
            wrong_count = result4.strip()
            if wrong_count and int(wrong_count) > 0:
                print(f"\n⚠️  КРИТИЧНО: {wrong_count} товаров имеют cover, указывающий на media.id вместо product_media.id!")
    except:
        pass
    
    print("\n" + "=" * 60)
    print("Для фикса запустите: python _scratchpad/fix_cover_ids.py")
    print("=" * 60)

except Exception as e:
    print(f"\n❌ Критическая ошибка: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


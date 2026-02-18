"""
Принудительная генерация thumbnails с различными параметрами
"""
import paramiko

host = "77.233.222.214"
username = "root"
password = "HuPtNj39"

print("=" * 60)
print("ПРИНУДИТЕЛЬНАЯ ГЕНЕРАЦИЯ THUMBNAILS")
print("=" * 60)

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password, timeout=10)
    print("[OK] Подключено")
    
    container_name = "shopware"
    
    # Пробуем с параметром --keep-existing=false (если есть)
    print("\n1. Генерация thumbnails (пробуем разные варианты)...")
    
    # Вариант 1: Обычная генерация
    print("\n   Вариант 1: Обычная генерация...")
    command = "docker exec shopware php bin/console media:generate-thumbnails"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=300)
    
    output_lines = []
    for line in stdout:
        line = line.strip()
        if line:
            output_lines.append(line)
            print(f"     {line}")
    
    # Проверяем результат
    generated = 0
    skipped = 0
    for line in output_lines:
        if "Generated" in line:
            try:
                generated = int(line.split()[-1])
            except:
                pass
        if "Skipped" in line:
            try:
                skipped = int(line.split()[-1])
            except:
                pass
    
    print(f"\n   Результат: Generated={generated}, Skipped={skipped}")
    
    # Если все пропущены, пробуем удалить существующие thumbnails и создать заново
    if skipped > 0 and generated == 0:
        print("\n   Все медиа пропущены. Пробуем удалить существующие thumbnails...")
        command = "docker exec shopware php bin/console media:delete-local-thumbnails"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
        
        delete_output = stdout.read().decode()
        if delete_output:
            print(f"     {delete_output[:200]}")
        
        # Теперь генерируем заново
        print("\n   Генерация thumbnails после удаления...")
        command = "docker exec shopware php bin/console media:generate-thumbnails"
        stdin, stdout, stderr = ssh.exec_command(command, timeout=300)
        
        for line in stdout:
            line = line.strip()
            if line:
                print(f"     {line}")
                if "Generated" in line:
                    try:
                        generated = int(line.split()[-1])
                        print(f"\n   [OK] Сгенерировано: {generated}")
                    except:
                        pass
    
    # Очищаем кеш
    print("\n2. Очистка кеша...")
    command = "docker exec shopware php bin/console cache:clear"
    stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
    stdout.read()
    print("   [OK] Кеш очищен")
    
    ssh.close()
    
    print("\n" + "=" * 60)
    print("ГЕНЕРАЦИЯ ЗАВЕРШЕНА")
    print("=" * 60)
    
except Exception as e:
    print(f"[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()









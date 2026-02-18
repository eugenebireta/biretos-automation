"""Генерация thumbnails для Shopware media"""
import paramiko
import sys
from pathlib import Path

# Параметры подключения
host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"  # Пароль из памяти
container_name = "shopware"

print("=" * 60)
print("ГЕНЕРАЦИЯ THUMBNAILS ДЛЯ SHOPWARE MEDIA")
print("=" * 60)

# Подключаемся к серверу
print(f"\n1. Подключение к серверу {host}...")
try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=ssh_username, password=ssh_password, timeout=30)
    print("   ✅ Подключение установлено")
except Exception as e:
    print(f"   ❌ Ошибка подключения: {e}")
    sys.exit(1)

# Выполняем команду генерации thumbnails
print(f"\n2. Запуск генерации thumbnails...")
print(f"   Команда: docker exec {container_name} php bin/console media:generate-thumbnails")
print(f"   Ожидание завершения...")

try:
    stdin, stdout, stderr = ssh.exec_command(
        f"docker exec {container_name} php bin/console media:generate-thumbnails",
        timeout=600  # 10 минут максимум
    )
    
    # Выводим вывод в реальном времени
    output_lines = []
    error_lines = []
    
    # Читаем stdout
    for line in iter(stdout.readline, ""):
        if line:
            line = line.rstrip()
            print(f"   {line}")
            output_lines.append(line)
    
    # Читаем stderr
    for line in iter(stderr.readline, ""):
        if line:
            line = line.rstrip()
            print(f"   [ERROR] {line}")
            error_lines.append(line)
    
    # Ждём завершения
    exit_status = stdout.channel.recv_exit_status()
    
    if exit_status == 0:
        print(f"\n   ✅ Команда выполнена успешно (exit code: {exit_status})")
    else:
        print(f"\n   ⚠️ Команда завершилась с кодом: {exit_status}")
    
    # Анализируем вывод
    output_text = "\n".join(output_lines)
    if "Skipped" in output_text or "skipped" in output_text:
        skipped_count = output_text.count("Skipped") + output_text.count("skipped")
        print(f"   ⚠️ Пропущено медиа: {skipped_count}")
    
    if "Generated" in output_text or "generated" in output_text:
        print(f"   ✅ Thumbnails генерируются")
    
except Exception as e:
    print(f"   ❌ Ошибка выполнения команды: {e}")
    ssh.close()
    sys.exit(1)

# Проверяем наличие thumbnails на диске
print(f"\n3. Проверка thumbnails на диске...")
try:
    stdin, stdout, stderr = ssh.exec_command(
        f"docker exec {container_name} find public/media -type d -name thumbnail 2>/dev/null | head -5"
    )
    
    thumbnail_dirs = []
    for line in stdout:
        line = line.rstrip()
        if line:
            thumbnail_dirs.append(line)
            print(f"   Найдена директория: {line}")
    
    if thumbnail_dirs:
        # Проверяем файлы в первой директории
        stdin2, stdout2, stderr2 = ssh.exec_command(
            f"docker exec {container_name} ls -la {thumbnail_dirs[0]} 2>/dev/null | head -10"
        )
        
        file_count = 0
        for line in stdout2:
            line = line.rstrip()
            if line and not line.startswith("total") and not line.startswith("d"):
                file_count += 1
                if file_count <= 5:
                    print(f"   Файл: {line.split()[-1] if line.split() else 'N/A'}")
        
        if file_count > 0:
            print(f"   ✅ Найдено минимум {file_count} thumbnail файлов")
        else:
            print(f"   ⚠️ Директории найдены, но файлы отсутствуют")
    else:
        print(f"   ⚠️ Директории thumbnails не найдены")
        
except Exception as e:
    print(f"   ⚠️ Ошибка проверки: {e}")

# Закрываем соединение
ssh.close()

print("\n" + "=" * 60)
print("ГЕНЕРАЦИЯ ЗАВЕРШЕНА")
print("=" * 60)
print("\nСледующие шаги:")
print("1. Проверьте превьюшки в админке Shopware")
print("2. Проверьте превьюшки на сайте (листинги и карточки товаров)")
print("3. Если thumbnails не появились, проверьте:")
print("   - Настройки thumbnail sizes в Shopware")
print("   - Права доступа к директории public/media")
print("   - Логи Shopware на наличие ошибок")
print("=" * 60)

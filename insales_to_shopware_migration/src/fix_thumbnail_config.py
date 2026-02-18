#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import subprocess
import os

# Читаем пароль из .env
env_path = "/var/www/shopware/.env"
db_password = None
with open(env_path) as f:
    for line in f:
        if line.startswith("DATABASE_PASSWORD="):
            db_password = line.split("=", 1)[1].strip()
            break

print("=" * 80)
print("ДИАГНОСТИКА И ИСПРАВЛЕНИЕ КОНФИГУРАЦИИ THUMBNAILS")
print("=" * 80)
print()

# Шаг 1: Находим конфигурацию корневой папки
root_folder_id = "00000000000000000000000000000000"
result = subprocess.run(
    ["mysql", "-u", "root", f"-p{db_password}", "shopware", "-N", "-e", 
     f"SELECT HEX(media_folder_configuration_id) FROM media_folder WHERE id = UNHEX('{root_folder_id}');"],
    capture_output=True,
    text=True
)
config_id_hex = result.stdout.strip()
print(f"[1] Конфигурация корневой папки: {config_id_hex}")
print()

# Шаг 2: Проверяем настройки конфигурации
result = subprocess.run(
    ["mysql", "-u", "root", f"-p{db_password}", "shopware", "-N", "-e",
     f"SELECT HEX(id), create_thumbnails, thumbnail_quality FROM media_folder_configuration WHERE id = UNHEX('{config_id_hex}');"],
    capture_output=True,
    text=True
)
print(f"[2] Настройки конфигурации:")
print(result.stdout)
parts = result.stdout.strip().split('\t')
if len(parts) >= 2:
    create_thumbnails = parts[1]
    print(f"    create_thumbnails = {create_thumbnails}")
    print()

    # Шаг 3: Исправляем, если create_thumbnails = 0
    if create_thumbnails == "0":
        print(f"[3] ИСПРАВЛЕНИЕ: create_thumbnails = 0, устанавливаем в 1")
        sql = f"UPDATE media_folder_configuration SET create_thumbnails = 1 WHERE id = UNHEX('{config_id_hex}');"
        result = subprocess.run(
            ["mysql", "-u", "root", f"-p{db_password}", "shopware", "-e", sql],
            capture_output=True,
            text=True
        )
        print(f"    Update result: {result.returncode}")
        if result.stderr:
            print(f"    Error: {result.stderr}")
        print()

        # Шаг 4: Проверяем результат
        result = subprocess.run(
            ["mysql", "-u", "root", f"-p{db_password}", "shopware", "-N", "-e",
             f"SELECT create_thumbnails FROM media_folder_configuration WHERE id = UNHEX('{config_id_hex}');"],
            capture_output=True,
            text=True
        )
        print(f"[4] Проверка после исправления:")
        print(f"    create_thumbnails = {result.stdout.strip()}")
    else:
        print(f"[3] create_thumbnails уже = 1, исправление не требуется")
else:
    print(f"[ERROR] Не удалось получить настройки конфигурации")

print()
print("=" * 80)





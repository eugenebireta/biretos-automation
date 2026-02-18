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

config_id_hex = "019A0C73E2A9739DAE82E8A78764D4EA"

print("=" * 80)
print("ОБНОВЛЕНИЕ ВСЕХ ПАПОК С МЕДИА")
print("=" * 80)
print()

# Находим все папки, где есть медиа
result = subprocess.run(
    ["mysql", "-u", "root", f"-p{db_password}", "shopware", "-N", "-e",
     "SELECT HEX(media_folder_id), COUNT(*) FROM media WHERE media_folder_id IS NOT NULL GROUP BY media_folder_id ORDER BY COUNT(*) DESC;"],
    capture_output=True,
    text=True
)
print("Папки с медиа:")
print(result.stdout)
print()

# Получаем список папок
folder_ids = []
for line in result.stdout.strip().split('\n'):
    if line:
        folder_id = line.split('\t')[0]
        folder_ids.append(folder_id)

print(f"Найдено папок: {len(folder_ids)}")
print()

# Обновляем каждую папку
for folder_id in folder_ids:
    sql = f"UPDATE media_folder SET media_folder_configuration_id = UNHEX('{config_id_hex}') WHERE id = UNHEX('{folder_id}');"
    result = subprocess.run(
        ["mysql", "-u", "root", f"-p{db_password}", "shopware", "-e", sql],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        print(f"✓ Обновлена папка: {folder_id}")
    else:
        print(f"✗ Ошибка для папки {folder_id}: {result.stderr}")

print()
print("Проверка результата:")
result = subprocess.run(
    ["mysql", "-u", "root", f"-p{db_password}", "shopware", "-N", "-e",
     f"SELECT HEX(id), name, HEX(media_folder_configuration_id) FROM media_folder WHERE id IN (SELECT DISTINCT media_folder_id FROM media WHERE media_folder_id IS NOT NULL);"],
    capture_output=True,
    text=True
)
print(result.stdout)
print()
print("=" * 80)





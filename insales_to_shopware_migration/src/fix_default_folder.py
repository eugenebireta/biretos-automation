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

# Находим конфигурацию
result = subprocess.run(
    ["mysql", "-u", "root", f"-p{db_password}", "shopware", "-N", "-e", "SELECT HEX(id) FROM media_folder_configuration LIMIT 1"],
    capture_output=True,
    text=True
)
config_id_hex = result.stdout.strip()
print(f"Configuration ID: {config_id_hex}")

# Обновляем корневую папку (id = 00000000000000000000000000000000) - туда попадают медиа с NULL mediaFolderId
root_folder_id = "00000000000000000000000000000000"
sql = f"UPDATE media_folder SET media_folder_configuration_id = UNHEX('{config_id_hex}') WHERE id = UNHEX('{root_folder_id}');"
result = subprocess.run(
    ["mysql", "-u", "root", f"-p{db_password}", "shopware", "-e", sql],
    capture_output=True,
    text=True
)
print(f"Update result: {result.returncode}")
if result.stderr:
    print(f"Error: {result.stderr}")

# Проверяем результат
result = subprocess.run(
    ["mysql", "-u", "root", f"-p{db_password}", "shopware", "-N", "-e", f"SELECT HEX(id), name, HEX(media_folder_configuration_id) FROM media_folder WHERE id = UNHEX('{root_folder_id}');"],
    capture_output=True,
    text=True
)
print("Verification (Root folder):")
print(result.stdout)


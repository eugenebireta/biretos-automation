#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import subprocess
import os
import json

# Читаем пароль из .env
env_path = "/var/www/shopware/.env"
db_password = None
with open(env_path) as f:
    for line in f:
        if line.startswith("DATABASE_PASSWORD="):
            db_password = line.split("=", 1)[1].strip()
            break

config_id_hex = "019A0C73E2A9739DAE82E8A78764D4EA"

print("Проверка thumbnail sizes в конфигурации:")
print(f"Config ID: {config_id_hex}")
print()

# Проверяем media_thumbnail_sizes_ro (BLOB поле)
result = subprocess.run(
    ["mysql", "-u", "root", f"-p{db_password}", "shopware", "-N", "-e",
     f"SELECT HEX(id), create_thumbnails, thumbnail_quality, LENGTH(media_thumbnail_sizes_ro) as sizes_length FROM media_folder_configuration WHERE id = UNHEX('{config_id_hex}');"],
    capture_output=True,
    text=True
)
print("Настройки конфигурации:")
print(result.stdout)
print()

# Проверяем, есть ли связанные thumbnail sizes через таблицу media_thumbnail_size
result = subprocess.run(
    ["mysql", "-u", "root", f"-p{db_password}", "shopware", "-N", "-e",
     f"SELECT COUNT(*) FROM media_thumbnail_size WHERE media_folder_configuration_id = UNHEX('{config_id_hex}');"],
    capture_output=True,
    text=True
)
print(f"Количество thumbnail sizes в media_thumbnail_size: {result.stdout.strip()}")





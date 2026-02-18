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
print("ДИАГНОСТИКА ПРОПУСКА THUMBNAILS")
print("=" * 80)
print()

# Проверяем медиа в корневой папке
result = subprocess.run(
    ["mysql", "-u", "root", f"-p{db_password}", "shopware", "-N", "-e",
     "SELECT HEX(id), mime_type, file_extension, has_file FROM media WHERE media_folder_id IS NULL LIMIT 5;"],
    capture_output=True,
    text=True
)
print("Медиа в корневой папке (media_folder_id IS NULL):")
print(result.stdout)
print()

# Проверяем настройки конфигурации подробнее
result = subprocess.run(
    ["mysql", "-u", "root", f"-p{db_password}", "shopware", "-N", "-e",
     f"SELECT HEX(id), create_thumbnails, thumbnail_quality, keep_aspect_ratio, private FROM media_folder_configuration WHERE id = UNHEX('{config_id_hex}');"],
    capture_output=True,
    text=True
)
print("Настройки конфигурации:")
print(result.stdout)
print()

# Проверяем, есть ли thumbnail sizes в BLOB
result = subprocess.run(
    ["mysql", "-u", "root", f"-p{db_password}", "shopware", "-N", "-e",
     f"SELECT HEX(id), LENGTH(media_thumbnail_sizes_ro) as sizes_length, SUBSTRING(media_thumbnail_sizes_ro, 1, 100) as sizes_preview FROM media_folder_configuration WHERE id = UNHEX('{config_id_hex}');"],
    capture_output=True,
    text=True
)
print("Thumbnail sizes (BLOB preview):")
print(result.stdout)
print()

print("=" * 80)





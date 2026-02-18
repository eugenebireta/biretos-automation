#!/usr/bin/env python3
import os
import pymysql

# Читаем пароль из .env
env_path = "/var/www/shopware/.env"
db_password = None
with open(env_path) as f:
    for line in f:
        if line.startswith("DATABASE_PASSWORD="):
            db_password = line.split("=", 1)[1].strip()
            break

# Подключаемся к БД
connection = pymysql.connect(
    host='localhost',
    user='root',
    password=db_password,
    database='shopware',
    charset='utf8mb4'
)

try:
    with connection.cursor() as cursor:
        # SQL команда
        sql = "UPDATE media_folder SET configuration_id = UNHEX('616401b99bee440c8333087ecc4ce4e8') WHERE id = UNHEX('01994d23ada87207aa7d8cb9994f5198');"
        cursor.execute(sql)
        connection.commit()
        print("SQL executed successfully")
        print(f"Rows affected: {cursor.rowcount}")
finally:
    connection.close()

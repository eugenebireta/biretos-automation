#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Non-interactive MySQL запросы для Shopware через SSH
Использование:
    python shopware_mysql_query.py "SELECT * FROM product LIMIT 1;"
    python shopware_mysql_query.py --file query.sql
"""
import subprocess
import sys
import os
import argparse

SSH_HOST = "root@216.9.227.124"
ENV_PATH = "/var/www/shopware/.env"
DB_NAME = "shopware"
DB_USER = "root"

def get_db_password():
    """Получает пароль БД с сервера (поддержка DATABASE_PASSWORD и DATABASE_URL)"""
    # Сначала пробуем DATABASE_PASSWORD
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", SSH_HOST,
         f"if grep -q '^DATABASE_PASSWORD=' {ENV_PATH}; then grep '^DATABASE_PASSWORD=' {ENV_PATH} | head -1 | cut -d= -f2 | tr -d '\"' | tr -d \"'\" | xargs; elif grep -q '^DATABASE_URL=' {ENV_PATH}; then DB_URL=$(grep '^DATABASE_URL=' {ENV_PATH} | cut -d= -f2- | tr -d '\"' | tr -d \"'\" | xargs); echo \"$DB_URL\" | sed -n 's|.*://[^:]*:\\([^@]*\\)@.*|\\1|p'; fi"],
        capture_output=True,
        text=True,
        timeout=10
    )
    
    if result.returncode != 0:
        print(f"[ERROR] Не удалось получить пароль БД: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    
    password = result.stdout.strip()
    if not password:
        print("[ERROR] Пароль БД пустой (проверьте DATABASE_PASSWORD или DATABASE_URL в .env)", file=sys.stderr)
        sys.exit(1)
    
    return password

def execute_query(sql_query, flags=""):
    """Выполняет MySQL запрос через SSH (non-interactive)"""
    db_password = get_db_password()
    
    # Экранируем SQL для bash
    sql_escaped = sql_query.replace("'", "'\"'\"'")
    
    # Команда для выполнения через SSH
    cmd = f"""export MYSQL_PWD='{db_password}' && mysql -u {DB_USER} {DB_NAME} {flags} -e '{sql_escaped}' 2>&1 | grep -v 'Warning:'"""
    
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", SSH_HOST, cmd],
        capture_output=True,
        text=True,
        timeout=30
    )
    
    if result.returncode != 0:
        print(f"[ERROR] Ошибка выполнения запроса: {result.stderr}", file=sys.stderr)
        return None
    
    return result.stdout

def main():
    parser = argparse.ArgumentParser(description="Non-interactive MySQL запросы для Shopware")
    parser.add_argument("query", nargs="?", help="SQL запрос")
    parser.add_argument("--file", "-f", help="Файл с SQL запросом")
    parser.add_argument("--no-headers", "-N", action="store_true", help="Без заголовков (табуляция)")
    parser.add_argument("--batch", "-B", action="store_true", help="Batch mode")
    
    args = parser.parse_args()
    
    if args.file:
        if not os.path.exists(args.file):
            print(f"[ERROR] Файл не найден: {args.file}", file=sys.stderr)
            sys.exit(1)
        with open(args.file, 'r', encoding='utf-8') as f:
            sql_query = f.read()
    elif args.query:
        sql_query = args.query
    else:
        parser.print_help()
        sys.exit(1)
    
    flags = ""
    if args.no_headers:
        flags += "-N "
    if args.batch:
        flags += "-B "
    
    output = execute_query(sql_query, flags)
    if output is not None:
        print(output, end="")

if __name__ == "__main__":
    main()


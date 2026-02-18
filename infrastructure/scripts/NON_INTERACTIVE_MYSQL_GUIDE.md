# Non-Interactive MySQL для Shopware

## ✅ Реализовано

Все SSH и MySQL команды теперь выполняются **без интерактивного ввода паролей**.

### 1. SSH Key-Based Access

- ✅ SSH ключ ed25519 сгенерирован: `~/.ssh/id_ed25519`
- ✅ Публичный ключ добавлен на сервер: `root@216.9.227.124`
- ✅ SSH подключение работает без пароля

**Проверка:**
```bash
ssh -o BatchMode=yes root@216.9.227.124 "echo OK"
```

### 2. Non-Interactive MySQL

Все MySQL команды используют переменную окружения `MYSQL_PWD` вместо интерактивного ввода.

**Поддержка форматов .env:**
- `DATABASE_PASSWORD=password` (прямой пароль)
- `DATABASE_URL=mysql://user:password@host:port/database` (URL формат)

## 📋 Использование

### Вариант 1: Универсальный скрипт (рекомендуется)

```bash
# Локально (через SSH)
./infrastructure/scripts/ssh_mysql_query.sh "SELECT COUNT(*) FROM product;"

# На сервере
./infrastructure/scripts/non_interactive_mysql.sh "SELECT COUNT(*) FROM product;"
```

### Вариант 2: Python утилита

```bash
python infrastructure/scripts/shopware_mysql_query.py "SELECT * FROM product LIMIT 1;"
python infrastructure/scripts/shopware_mysql_query.py --file query.sql
```

### Вариант 3: Прямая команда через SSH

```bash
ssh -o BatchMode=yes root@216.9.227.124 'ENV_PATH="/var/www/shopware/.env" && DB_PASSWORD="" && if grep -q "^DATABASE_PASSWORD=" "$ENV_PATH"; then DB_PASSWORD=$(grep "^DATABASE_PASSWORD=" "$ENV_PATH" | cut -d= -f2 | tr -d "\"" | tr -d "\047" | xargs); elif grep -q "^DATABASE_URL=" "$ENV_PATH"; then DB_URL=$(grep "^DATABASE_URL=" "$ENV_PATH" | cut -d= -f2- | tr -d "\"" | tr -d "\047" | xargs); DB_PASSWORD=$(echo "$DB_URL" | sed -n "s|.*://[^:]*:\\([^@]*\\)@.*|\\1|p"); fi && export MYSQL_PWD="$DB_PASSWORD" && mysql -u root shopware -N -e "SELECT COUNT(*) FROM product;" 2>&1 | grep -v "Warning:"'
```

## 🔧 Обновленные скрипты

Все скрипты диагностики Shopware обновлены для non-interactive режима:

- ✅ `insales_to_shopware_migration/src/execute_sql_fix.py`
- ✅ `insales_to_shopware_migration/src/check_listing_sql.py`
- ✅ `insales_to_shopware_migration/src/diagnose_listing_images.py`
- ✅ `insales_to_shopware_migration/src/check_listing_sql_server.py`

**Изменения:**
- Все SSH команды используют `-o BatchMode=yes` (запрет интерактивного ввода)
- Все MySQL команды используют `MYSQL_PWD` вместо `-p{password}`
- Поддержка парсинга `DATABASE_URL` из .env

## 🧪 Тестирование

```bash
# Тест SSH
ssh -o BatchMode=yes root@216.9.227.124 "echo OK"

# Тест MySQL
python _scratchpad/test_mysql_final.py
```

## ⚠️ Важно

1. **НЕ используйте `sshpass`** - все команды работают через SSH ключи
2. **НЕ храните пароли в скриптах** - пароль читается из .env на сервере
3. **Всегда используйте `-o BatchMode=yes`** для SSH команд в скриптах
4. **Используйте `MYSQL_PWD`** вместо `-p{password}` для безопасности

## 📝 Пример финальной команды диагностики

```bash
# Полная диагностика Shopware (non-interactive)
ssh -o BatchMode=yes root@216.9.227.124 'ENV_PATH="/var/www/shopware/.env" && DB_PASSWORD="" && if grep -q "^DATABASE_PASSWORD=" "$ENV_PATH"; then DB_PASSWORD=$(grep "^DATABASE_PASSWORD=" "$ENV_PATH" | cut -d= -f2 | tr -d "\"" | tr -d "\047" | xargs); elif grep -q "^DATABASE_URL=" "$ENV_PATH"; then DB_URL=$(grep "^DATABASE_URL=" "$ENV_PATH" | cut -d= -f2- | tr -d "\"" | tr -d "\047" | xargs); DB_PASSWORD=$(echo "$DB_URL" | sed -n "s|.*://[^:]*:\\([^@]*\\)@.*|\\1|p"); fi && export MYSQL_PWD="$DB_PASSWORD" && mysql -u root shopware -N -e "SELECT COUNT(*) as products, (SELECT COUNT(*) FROM product_media) as media, (SELECT COUNT(*) FROM media) as total_media FROM product;" 2>&1 | grep -v "Warning:"'
```

**Результат:** Команда выполняется полностью автоматически, без запросов паролей.




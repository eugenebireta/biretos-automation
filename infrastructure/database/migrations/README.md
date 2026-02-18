# Database Migrations

SQL миграции для PostgreSQL базы данных `biretos_automation`.

## Применение миграций

### На USA-VPS

```bash
# Подключение к PostgreSQL
psql -U postgres -d biretos_automation

# Применить миграцию
\i infrastructure/database/migrations/001_create_invoice_orders_table.sql

# Проверка
\d invoice_orders
SELECT * FROM invoice_orders LIMIT 5;
```

### Через SSH

```bash
ssh root@216.9.227.124 "psql -U postgres -d biretos_automation -f -" < infrastructure/database/migrations/001_create_invoice_orders_table.sql
```

## Миграции

- `001_create_invoice_orders_table.sql` - Создание таблицы для связи invoice_id ↔ order_id









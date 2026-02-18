# T-Bank Webhook Capture v0.1

Временный receiver для получения и логирования реального payload от Т-Банка.

## Статус

- **Версия**: v0.1 (микро-правки надёжности)
- **Назначение**: Payload discovery
- **Жизненный цикл**: Временный, удаляется после получения payload

## Функции

- ✅ Принимает только POST (405 на другие методы)
- ✅ Логирует headers (с fallback если `getallheaders()` недоступна)
- ✅ Fail-safe логирование (fallback на `error_log()`)
- ✅ Сохраняет raw payload в JSONL формат

## Установка

### 1. Создание директории

```bash
mkdir -p /var/www/tbank-webhook-capture
cp webhook.php /var/www/tbank-webhook-capture/
chmod 755 /var/www/tbank-webhook-capture/webhook.php
```

### 2. Создание директории для логов

```bash
mkdir -p /var/log/tbank-webhook-capture
chmod 755 /var/log/tbank-webhook-capture
```

### 3. Настройка nginx

Добавить в конфигурацию nginx:

```nginx
server {
    listen 80;
    server_name webhook-capture.your-domain.ru;

    root /var/www/tbank-webhook-capture;
    index webhook.php;

    location /webhook {
        try_files $uri $uri/ /webhook.php;
    }

    location ~ \.php$ {
        fastcgi_pass unix:/var/run/php/php8.1-fpm.sock;
        fastcgi_index webhook.php;
        include fastcgi_params;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
    }
}
```

### 4. Регистрация в Т-Банке

URL: `https://webhook-capture.your-domain.ru/webhook`
Method: POST
Format: JSON

## Логи

### Формат лога

Файлы: `/var/log/tbank-webhook-capture/payload_YYYY-MM-DD.jsonl`

Формат: JSON Lines (одна запись на строку)

Пример:
```json
{
  "timestamp": "2025-01-15T10:30:00+03:00",
  "headers": {
    "Host": "webhook-capture.example.ru",
    "Content-Type": "application/json",
    "Authorization": "Bearer ..."
  },
  "body": {
    "invoice_id": "INV-12345",
    "status": "PAID"
  },
  "raw_body": "{\"invoice_id\":\"INV-12345\",...}",
  "method": "POST",
  "uri": "/webhook",
  "remote_addr": "192.0.2.100"
}
```

### Просмотр логов

```bash
# Последние записи
tail -f /var/log/tbank-webhook-capture/payload_*.jsonl | jq

# Все записи за день
cat /var/log/tbank-webhook-capture/payload_2025-01-15.jsonl | jq

# Поиск по invoice_id
cat /var/log/tbank-webhook-capture/payload_*.jsonl | jq 'select(.body.invoice_id == "INV-12345")'
```

### Fallback логирование

Если запись в файл не удалась, payload записывается в `error_log()` (syslog/journald):

```bash
# Просмотр через journald
journalctl -f | grep TBANK-WEBHOOK

# Просмотр через syslog
tail -f /var/log/syslog | grep TBANK-WEBHOOK
```

## Тестирование

### Проверка method guard

```bash
curl -X GET http://webhook-capture.example.ru/webhook
# Ожидаем: 405 {"error":"Method not allowed"}

curl -X POST http://webhook-capture.example.ru/webhook \
  -H "Content-Type: application/json" \
  -d '{"test": "payload"}'
# Ожидаем: 200 {"status":"ok","received_at":"..."}
```

### Проверка работы

```bash
# Отправить тестовый payload
curl -X POST http://webhook-capture.example.ru/webhook \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-token" \
  -d '{
    "invoice_id": "INV-TEST-001",
    "status": "PAID",
    "amount": 15000
  }'

# Проверить лог
tail -1 /var/log/tbank-webhook-capture/payload_*.jsonl | jq
```

## Удаление после discovery

После получения реального payload:

1. Сохранить пример payload для анализа
2. Удалить v0 receiver:
   ```bash
   rm -rf /var/www/tbank-webhook-capture/
   rm -rf /var/log/tbank-webhook-capture/
   ```
3. Остановить nginx конфиг
4. Развернуть v2 gateway (см. `../tbank-webhook-gateway/DEPLOYMENT.md`)

## Связанные компоненты

- **v2 Gateway**: `../tbank-webhook-gateway/` (production решение, НЕ ТРОГАТЬ)
- **n8n Workflow**: `../n8n-workflows/tbank-invoice-paid-webhook.json`









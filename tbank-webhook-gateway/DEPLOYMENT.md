# Развёртывание T-Bank Webhook Gateway

## Обзор

Gateway развёртывается на **RU-VPS** (Ubuntu) и принимает webhook от Т-Банка, проксируя их в n8n на USA-VPS.

## Предварительные требования

- Ubuntu 22.04+ или аналогичный Linux
- Python 3.11+
- nginx (для reverse proxy)
- systemd
- Доступ к серверу от root

## Шаги развёртывания

### 1. Загрузка кода на сервер

```bash
# На локальной машине (Windows)
scp -r tbank-webhook-gateway root@<RU-VPS-IP>:/opt/
```

### 2. Запуск скрипта развёртывания

```bash
# На RU-VPS
cd /opt/tbank-webhook-gateway
chmod +x infrastructure/scripts/deploy-gateway.sh
./infrastructure/scripts/deploy-gateway.sh
```

Или вручную:

```bash
# Создание директорий
mkdir -p /opt/tbank-webhook-gateway/{app,config}
mkdir -p /var/log/tbank-gateway

# Установка Python зависимостей
cd /opt/tbank-webhook-gateway
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Копирование service
cp gateway.service /etc/systemd/system/
systemctl daemon-reload
```

### 3. Настройка конфигурации

```bash
# Создание конфигурации
cp config/gateway.env.template config/gateway.env
nano config/gateway.env
```

Заполните переменные:
- `N8N_WEBHOOK_URL`: URL webhook n8n (получите после активации workflow)
- `N8N_WEBHOOK_SECRET`: Секрет для HMAC подписи (установите в n8n webhook настройках)

### 4. Настройка nginx

Добавьте в `/etc/nginx/sites-available/default` (или отдельный конфиг):

```nginx
# Rate limiting (в блоке http {})
limit_req_zone $binary_remote_addr zone=webhook_limit:10m rate=100r/m;

# В блоке server {
location /webhook/tbank {
    limit_req zone=webhook_limit burst=10 nodelay;
    
    proxy_pass http://127.0.0.1:8080/webhook/tbank;
    proxy_http_version 1.1;
    
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    proxy_connect_timeout 5s;
    proxy_send_timeout 5s;
    proxy_read_timeout 5s;
    
    client_max_body_size 1M;
}

location /health {
    proxy_pass http://127.0.0.1:8080/health;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
}
```

Перезапустите nginx:
```bash
nginx -t
systemctl reload nginx
```

### 5. Запуск gateway

```bash
# Запуск service
systemctl start tbank-webhook-gateway
systemctl enable tbank-webhook-gateway

# Проверка статуса
systemctl status tbank-webhook-gateway

# Просмотр логов
journalctl -u tbank-webhook-gateway -f
tail -f /var/log/tbank-gateway/webhook.log | jq
```

### 6. Регистрация webhook в Т-Банке

1. Получите публичный URL: `https://<RU-VPS-DOMAIN>/webhook/tbank`
2. Зарегистрируйте в личном кабинете Т-Банка:
   - URL: `https://<RU-VPS-DOMAIN>/webhook/tbank`
   - Method: POST
   - Format: JSON

### 7. Активация n8n workflow

1. Откройте n8n: `https://n8n.biretos.ae`
2. Импортируйте workflow: `n8n-workflows/tbank-invoice-paid-webhook.json`
3. Активируйте workflow
4. Скопируйте Production URL из узла "T-Bank Invoice Paid Webhook"
5. Обновите `N8N_WEBHOOK_URL` в `config/gateway.env`
6. Перезапустите gateway:
   ```bash
   systemctl restart tbank-webhook-gateway
   ```

## Проверка работы

### Health check

```bash
curl http://localhost:8080/health
# или через nginx
curl https://<RU-VPS-DOMAIN>/health
```

### Тестовый webhook

```bash
curl -X POST http://localhost:8080/webhook/tbank \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "INV-TEST-001",
    "status": "PAID",
    "amount": 15000,
    "currency": "RUB"
  }'
```

### Просмотр логов

```bash
# systemd logs
journalctl -u tbank-webhook-gateway -f --since "1 hour ago"

# Файловые логи
tail -f /var/log/tbank-gateway/webhook.log | jq

# Только ошибки
journalctl -u tbank-webhook-gateway -p err -f
```

## Устранение проблем

### Gateway не запускается

1. Проверьте логи: `journalctl -u tbank-webhook-gateway -n 50`
2. Проверьте конфигурацию: `cat config/gateway.env`
3. Проверьте Python: `source venv/bin/activate && python --version`

### Webhook не доходят до n8n

1. Проверьте `N8N_WEBHOOK_URL` в конфигурации
2. Проверьте доступность n8n: `curl https://n8n.biretos.ae/webhook/tbank-invoice-paid`
3. Проверьте логи gateway на ошибки forward

### nginx возвращает 502

1. Проверьте что gateway запущен: `systemctl status tbank-webhook-gateway`
2. Проверьте порт: `netstat -tlnp | grep 8080`
3. Проверьте логи nginx: `tail -f /var/log/nginx/error.log`

## Обновление

```bash
cd /opt/tbank-webhook-gateway
git pull  # или scp новых файлов
source venv/bin/activate
pip install -r requirements.txt
systemctl restart tbank-webhook-gateway
```

## Масштабирование

Для горизонтального масштабирования:

1. Запустите несколько инстансов gateway на разных портах (8080, 8081, ...)
2. Настройте nginx load balancer перед ними
3. Используйте единую очередь логов (syslog server)









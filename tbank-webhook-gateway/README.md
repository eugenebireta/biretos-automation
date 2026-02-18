# T-Bank Webhook Gateway

Lightweight webhook receiver для приёма событий от Т-Банка и проксирования в n8n.

## Описание

Gateway принимает webhook от Т-Банка, валидирует payload, логирует события и проксирует в n8n на USA-VPS. Stateless приложение без бизнес-логики.

## Требования

- Python 3.11+
- systemd (для запуска как service)
- nginx (для reverse proxy и SSL termination)

## Установка

### 1. Установка зависимостей

```bash
cd /opt/tbank-webhook-gateway
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Настройка окружения

```bash
cp config/gateway.env.template config/gateway.env
# Отредактируйте config/gateway.env
```

### 3. Создание директории для логов

```bash
sudo mkdir -p /var/log/tbank-gateway
sudo chown $USER:$USER /var/log/tbank-gateway
```

### 4. Запуск через systemd

```bash
sudo cp gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tbank-webhook-gateway
sudo systemctl start tbank-webhook-gateway
```

### 5. Настройка nginx

См. `config/nginx.conf` для примера конфигурации.

## Endpoints

- `GET /health` - Health check
- `POST /webhook/tbank` - Приём webhook от Т-Банка

## Логирование

Логи в формате JSON:
- Console (stdout)
- Файл: `/var/log/tbank-gateway/webhook.log`
- syslog (опционально)

Просмотр логов:
```bash
journalctl -u tbank-webhook-gateway -f
tail -f /var/log/tbank-gateway/webhook.log | jq
```

## Тестирование

### Локальный запуск

```bash
source venv/bin/activate
export N8N_WEBHOOK_URL=https://n8n.biretos.ae/webhook/tbank-invoice-paid
export N8N_WEBHOOK_SECRET=your_secret
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### Тестовый webhook

```bash
curl -X POST http://localhost:8080/webhook/tbank \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "INV-TEST-123",
    "status": "PAID",
    "amount": 15000,
    "currency": "RUB"
  }'
```

## Архитектура

- **Stateless**: нет состояния между запросами
- **Async**: не блокирует ответ Т-Банку
- **Idempotent**: поддерживает retry на стороне n8n
- **Observable**: структурированное логирование для трейсинга

## Масштабирование

Gateway можно запустить в нескольких инстансах за nginx load balancer.









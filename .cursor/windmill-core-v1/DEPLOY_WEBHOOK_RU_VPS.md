# Инструкция по развертыванию Telegram Webhook на RU VPS

## Проблема
- Webhook настроен на USA VPS (biretos.ae), а должен быть на RU VPS (77.233.222.214)
- Telegram API требует HTTPS для webhook
- webhook_service должен быть доступен снаружи

## Решение

### Вариант 1: Прямой доступ через IP (HTTP) - НЕ РАБОТАЕТ
Telegram API не принимает HTTP без SSL для webhook. Нужен HTTPS.

### Вариант 2: Nginx с SSL (рекомендуется)

#### Шаг 1: Установить SSL сертификат (Let's Encrypt)

```bash
# На RU VPS
sudo apt update
sudo apt install certbot python3-certbot-nginx

# Если есть домен, указывающий на 77.233.222.214:
sudo certbot --nginx -d your-domain.com

# Если нет домена, можно использовать самоподписанный сертификат:
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/nginx-selfsigned.key \
  -out /etc/ssl/certs/nginx-selfsigned.crt
```

#### Шаг 2: Настроить Nginx

Создайте `/etc/nginx/sites-available/telegram-webhook`:

```nginx
server {
    listen 80;
    server_name 77.233.222.214;
    
    # Редирект на HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name 77.233.222.214;

    ssl_certificate /etc/ssl/certs/nginx-selfsigned.crt;
    ssl_certificate_key /etc/ssl/private/nginx-selfsigned.key;

    location /webhook/telegram {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Активируйте конфигурацию:
```bash
sudo ln -s /etc/nginx/sites-available/telegram-webhook /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### Шаг 3: Установить webhook

```bash
curl "https://api.telegram.org/bot8498388416:AAGXJ1Lgdyprvy8gytJnj5V6KmTcCXxXNXk/setWebhook?url=https://77.233.222.214/webhook/telegram"
```

### Вариант 3: Использовать существующий домен (если есть)

Если у вас есть домен, указывающий на RU VPS:
1. Настройте SSL для домена
2. Установите webhook на `https://your-domain.com/webhook/telegram`

### Вариант 4: Временное решение - использовать USA VPS как прокси

Если срочно нужно запустить, можно временно:
1. Настроить USA VPS (biretos.ae) для проксирования на RU VPS
2. Webhook остается на biretos.ae, но запросы идут на RU VPS

## Автоматизация

### На RU VPS выполните:

```bash
# 1. Запустить webhook_service
cd /path/to/windmill-core-v1
chmod +x start_webhook_service.sh
./start_webhook_service.sh

# 2. Настроить webhook (после настройки SSL)
chmod +x setup_webhook_ru_vps.sh
./setup_webhook_ru_vps.sh
```

## Проверка

```bash
# Проверить webhook
curl "https://api.telegram.org/bot8498388416:AAGXJ1Lgdyprvy8gytJnj5V6KmTcCXxXNXk/getWebhookInfo"

# Отправить /start боту
# Проверить логи webhook_service
tail -f /path/to/windmill-core-v1/webhook_service/webhook_service.log
```
















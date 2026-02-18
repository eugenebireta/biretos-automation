# Инструкция по настройке Telegram Webhook на RU VPS

## Проблема
Webhook настроен на `https://biretos.ae/webhook/telegram` (USA VPS), а должен быть на RU VPS (77.233.222.214).

## Шаги настройки

### 1. Проверить, что webhook_service запущен на RU VPS

Подключитесь к RU VPS по SSH:
```bash
ssh user@77.233.222.214
```

Проверьте процесс:
```bash
ps aux | grep webhook_service
# или
ps aux | grep "main.py"
```

Если не запущен, запустите:
```bash
cd /path/to/windmill-core-v1/webhook_service
python3 main.py
# или через systemd/supervisor
```

### 2. Проверить, что порт 8001 открыт

```bash
# Проверить firewall
sudo ufw status
# или
sudo iptables -L -n | grep 8001

# Если порт закрыт, откройте:
sudo ufw allow 8001/tcp
# или
sudo iptables -A INPUT -p tcp --dport 8001 -j ACCEPT
```

### 3. Проверить доступность webhook_service

С локального компьютера:
```bash
curl http://77.233.222.214:8001/health
```

Должен вернуть: `{"status":"healthy","service":"webhook-queue"}`

### 4. Настроить nginx (опционально, но рекомендуется)

Если хотите использовать nginx для проксирования:

1. Добавьте конфигурацию в `/etc/nginx/sites-available/default` или создайте новый файл:
```nginx
server {
    listen 80;
    server_name 77.233.222.214;

    location /webhook/telegram {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

2. Перезагрузите nginx:
```bash
sudo nginx -t  # Проверка конфигурации
sudo systemctl reload nginx
```

### 5. Установить webhook через Telegram API

**Вариант A: Прямой доступ к порту 8001**
```bash
curl "https://api.telegram.org/bot8498388416:AAGXJ1Lgdyprvy8gytJnj5V6KmTcCXxXNXk/setWebhook?url=http://77.233.222.214:8001/webhook/telegram"
```

**Вариант B: Через nginx (если настроен)**
```bash
curl "https://api.telegram.org/bot8498388416:AAGXJ1Lgdyprvy8gytJnj5V6KmTcCXxXNXk/setWebhook?url=http://77.233.222.214/webhook/telegram"
```

### 6. Проверить установку webhook

```bash
curl "https://api.telegram.org/bot8498388416:AAGXJ1Lgdyprvy8gytJnj5V6KmTcCXxXNXk/getWebhookInfo"
```

Должен вернуть:
```json
{
  "ok": true,
  "result": {
    "url": "http://77.233.222.214:8001/webhook/telegram",
    "pending_update_count": 0,
    "last_error_date": null,
    "last_error_message": null
  }
}
```

### 7. Протестировать

Отправьте `/start` боту в Telegram. Проверьте логи:
```bash
# Логи webhook_service
tail -f /path/to/webhook_service/logs/*.log

# Или если логи в stdout:
# Смотрите вывод процесса webhook_service
```

## Автоматизация

После настройки можно запустить скрипт:
```bash
python3 set_webhook_ru_vps.py
```

Но сначала убедитесь, что webhook_service доступен снаружи!
















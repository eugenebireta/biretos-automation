# ВЫПОЛНИТЬ СЕЙЧАС НА RU VPS

## Быстрая команда (скопируй и выполни на RU VPS):

```bash
# Подключись к RU VPS
ssh user@77.233.222.214

# Выполни эти команды:
cd /path/to/windmill-core-v1

# 1. Запусти webhook_service
cd webhook_service
nohup python3 main.py > webhook_service.log 2>&1 &
sleep 2
curl http://localhost:8001/health

# 2. Открой порт (если нужно)
sudo ufw allow 8001/tcp
# или
sudo iptables -A INPUT -p tcp --dport 8001 -j ACCEPT

# 3. Установи webhook (HTTP - может не работать без SSL)
curl "https://api.telegram.org/bot8498388416:AAGXJ1Lgdyprvy8gytJnj5V6KmTcCXxXNXk/setWebhook?url=http://77.233.222.214:8001/webhook/telegram"

# 4. Проверь
curl "https://api.telegram.org/bot8498388416:AAGXJ1Lgdyprvy8gytJnj5V6KmTcCXxXNXk/getWebhookInfo"
```

## Если HTTP не работает (Telegram требует HTTPS):

Настрой nginx с SSL или используй домен с SSL.

См. полную инструкцию: `DEPLOY_WEBHOOK_RU_VPS.md`
















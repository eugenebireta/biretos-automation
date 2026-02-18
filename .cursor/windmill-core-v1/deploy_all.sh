#!/bin/bash
# Скрипт оставлен для совместимости. Используйте модульные deploy.sh (ru_worker/, webhook_service/).

set -e
echo "⚠️ deploy_all.sh отключён. Запускайте: cd windmill-core-v1/<module> && bash deploy.sh"
exit 1

echo "=========================================="
echo "  НАСТРОЙКА TELEGRAM WEBHOOK НА RU VPS"
echo "=========================================="
echo ""

# 1. Запуск webhook_service
echo "[1/5] Запуск webhook_service..."
cd "$SCRIPT_DIR"
if [ -f "start_webhook_service.sh" ]; then
    chmod +x start_webhook_service.sh
    ./start_webhook_service.sh
else
    echo "   [WARNING] start_webhook_service.sh не найден, запускаем вручную..."
    cd webhook_service
    nohup python3 main.py > webhook_service.log 2>&1 &
    sleep 2
    if curl -s -f "http://localhost:8001/health" > /dev/null; then
        echo "   [OK] webhook_service запущен"
    else
        echo "   [ERROR] webhook_service не запустился"
        exit 1
    fi
fi

# 2. Открытие порта в firewall
echo ""
echo "[2/5] Настройка firewall..."
if command -v ufw > /dev/null; then
    if ! ufw status | grep -q "8001"; then
        echo "   Открываем порт 8001..."
        ufw allow 8001/tcp
    fi
    echo "   [OK] Порт 8001 открыт"
elif command -v iptables > /dev/null; then
    if ! iptables -L -n | grep -q "8001"; then
        echo "   Открываем порт 8001..."
        iptables -A INPUT -p tcp --dport 8001 -j ACCEPT
    fi
    echo "   [OK] Порт 8001 открыт"
else
    echo "   [WARNING] Не найден ufw/iptables, проверьте firewall вручную"
fi

# 3. Настройка nginx (если установлен)
echo ""
echo "[3/5] Настройка nginx..."
if command -v nginx > /dev/null; then
    NGINX_CONFIG="/etc/nginx/sites-available/telegram-webhook"
    
    if [ ! -f "$NGINX_CONFIG" ]; then
        echo "   Создаем конфигурацию nginx..."
        sudo tee "$NGINX_CONFIG" > /dev/null <<EOF
server {
    listen 80;
    server_name ${RU_VPS_IP};
    
    location /webhook/telegram {
        proxy_pass http://localhost:8001;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
        
        # Активируем конфигурацию
        sudo ln -sf "$NGINX_CONFIG" /etc/nginx/sites-enabled/telegram-webhook
        
        # Проверяем конфигурацию
        if sudo nginx -t; then
            sudo systemctl reload nginx
            echo "   [OK] nginx настроен (HTTP)"
        else
            echo "   [ERROR] Ошибка в конфигурации nginx"
        fi
    else
        echo "   [OK] Конфигурация nginx уже существует"
    fi
else
    echo "   [INFO] nginx не установлен, используем прямой доступ к порту 8001"
fi

# 4. Проверка доступности
echo ""
echo "[4/5] Проверка доступности..."
if curl -s -f --max-time 5 "http://${RU_VPS_IP}:8001/health" > /dev/null 2>&1; then
    echo "   [OK] webhook_service доступен снаружи (порт 8001)"
    USE_DIRECT_PORT=true
elif curl -s -f --max-time 5 "http://${RU_VPS_IP}/webhook/telegram" > /dev/null 2>&1; then
    echo "   [OK] webhook доступен через nginx"
    USE_DIRECT_PORT=false
else
    echo "   [WARNING] webhook_service недоступен снаружи"
    echo "   Проверьте firewall и сетевые настройки"
    USE_DIRECT_PORT=true
fi

# 5. Установка webhook
echo ""
echo "[5/5] Установка Telegram webhook..."

if [ "$USE_DIRECT_PORT" = true ]; then
    WEBHOOK_URL="http://${RU_VPS_IP}:8001/webhook/telegram"
    echo "   [WARNING] Используем HTTP (без SSL)"
    echo "   Telegram API может не принять HTTP webhook!"
    echo "   Рекомендуется настроить SSL (см. DEPLOY_WEBHOOK_RU_VPS.md)"
else
    WEBHOOK_URL="http://${RU_VPS_IP}/webhook/telegram"
fi

echo "   URL: ${WEBHOOK_URL}"

RESPONSE=$(curl -s "https://api.telegram.org/bot${TOKEN}/setWebhook?url=${WEBHOOK_URL}")

if echo "$RESPONSE" | grep -q '"ok":true'; then
    echo "   [OK] Webhook установлен успешно!"
    
    # Проверка
    echo ""
    echo "Проверка webhook:"
    WEBHOOK_INFO=$(curl -s "https://api.telegram.org/bot${TOKEN}/getWebhookInfo")
    echo "$WEBHOOK_INFO" | python3 -m json.tool 2>/dev/null || echo "$WEBHOOK_INFO"
else
    ERROR_MSG=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('description', 'Unknown error'))" 2>/dev/null || echo "Unknown error")
    echo "   [ERROR] Не удалось установить webhook: $ERROR_MSG"
    
    if echo "$ERROR_MSG" | grep -qi "ssl\|certificate"; then
        echo ""
        echo "   РЕШЕНИЕ: Настройте SSL сертификат"
        echo "   См. инструкцию: DEPLOY_WEBHOOK_RU_VPS.md"
    fi
    
    exit 1
fi

echo ""
echo "=========================================="
echo "  ГОТОВО!"
echo "=========================================="
echo "Webhook настроен на: ${WEBHOOK_URL}"
echo ""
echo "Следующие шаги:"
echo "1. Отправьте /start боту в Telegram"
echo "2. Проверьте логи: tail -f ${SCRIPT_DIR}/webhook_service/webhook_service.log"
echo "3. Если webhook не работает, настройте SSL (см. DEPLOY_WEBHOOK_RU_VPS.md)"









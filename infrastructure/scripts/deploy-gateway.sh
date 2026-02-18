#!/bin/bash
# Скрипт развёртывания T-Bank Webhook Gateway на RU-VPS
# Использование: ./deploy-gateway.sh

set -euo pipefail

GATEWAY_DIR="/opt/tbank-webhook-gateway"
SERVICE_NAME="tbank-webhook-gateway"
USER="root"

echo "=== T-Bank Webhook Gateway Deployment ==="

# Проверка что скрипт запущен от root или с sudo
if [ "$EUID" -ne 0 ]; then
    echo "Ошибка: скрипт должен быть запущен от root или с sudo"
    exit 1
fi

# Создание директории
echo "1. Создание директории $GATEWAY_DIR..."
mkdir -p "$GATEWAY_DIR"/{app,config}
mkdir -p /var/log/tbank-gateway
chown -R "$USER:$USER" "$GATEWAY_DIR" /var/log/tbank-gateway

# Проверка Python
echo "2. Проверка Python..."
if ! command -v python3 &> /dev/null; then
    echo "Установка Python 3..."
    apt-get update
    apt-get install -y python3 python3-venv python3-pip
fi

# Создание виртуального окружения
echo "3. Создание виртуального окружения..."
if [ ! -d "$GATEWAY_DIR/venv" ]; then
    python3 -m venv "$GATEWAY_DIR/venv"
fi

# Активация и установка зависимостей
echo "4. Установка зависимостей..."
source "$GATEWAY_DIR/venv/bin/activate"
pip install --upgrade pip
pip install -r "$GATEWAY_DIR/requirements.txt"

# Копирование конфигурации (если не существует)
if [ ! -f "$GATEWAY_DIR/config/gateway.env" ]; then
    echo "5. Создание конфигурации..."
    cp "$GATEWAY_DIR/config/gateway.env.template" "$GATEWAY_DIR/config/gateway.env"
    echo "⚠️  ВНИМАНИЕ: Отредактируйте $GATEWAY_DIR/config/gateway.env перед запуском!"
fi

# Установка systemd service
echo "6. Установка systemd service..."
cp "$GATEWAY_DIR/gateway.service" "/etc/systemd/system/$SERVICE_NAME.service"
systemctl daemon-reload

echo ""
echo "=== Развёртывание завершено ==="
echo ""
echo "Следующие шаги:"
echo "1. Отредактируйте конфигурацию:"
echo "   nano $GATEWAY_DIR/config/gateway.env"
echo ""
echo "2. Запустите service:"
echo "   systemctl start $SERVICE_NAME"
echo "   systemctl enable $SERVICE_NAME"
echo ""
echo "3. Проверьте статус:"
echo "   systemctl status $SERVICE_NAME"
echo "   journalctl -u $SERVICE_NAME -f"
echo ""
echo "4. Настройте nginx (см. $GATEWAY_DIR/config/nginx.conf)"









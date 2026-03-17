#!/bin/bash
# Установка systemd-сервисов biretos-ru-worker и biretos-webhook на VPS
# Использование: sudo ./install-biretos-services.sh
# Запускать из каталога infrastructure/scripts/ или из корня репозитория.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="$(dirname "$SCRIPT_DIR")/systemd"

if [ "$EUID" -ne 0 ]; then
    echo "Ошибка: скрипт должен быть запущен от root или с sudo"
    exit 1
fi

if [ ! -f "$SYSTEMD_DIR/biretos-ru-worker.service" ] || [ ! -f "$SYSTEMD_DIR/biretos-webhook.service" ]; then
    echo "Ошибка: unit-файлы не найдены в $SYSTEMD_DIR"
    exit 1
fi

echo "=== Установка Biretos systemd-сервисов ==="

echo "1. Копирование unit-файлов в /etc/systemd/system/..."
cp "$SYSTEMD_DIR/biretos-ru-worker.service" /etc/systemd/system/
cp "$SYSTEMD_DIR/biretos-webhook.service" /etc/systemd/system/

echo "2. systemctl daemon-reload..."
systemctl daemon-reload

echo "3. Включение автозапуска (enable)..."
systemctl enable biretos-ru-worker.service
systemctl enable biretos-webhook.service

echo "4. Остановка старых nohup-процессов (если есть)..."
pkill -f 'python.*ru_worker.py' 2>/dev/null || true
pkill -f 'python.*main.py.*webhook_service' 2>/dev/null || true
sleep 2

echo "5. Запуск сервисов..."
systemctl start biretos-ru-worker.service
systemctl start biretos-webhook.service

echo ""
echo "=== Установка завершена ==="
echo ""
echo "Проверка статуса:"
echo "  systemctl status biretos-ru-worker"
echo "  systemctl status biretos-webhook"
echo ""
echo "Логи:"
echo "  journalctl -u biretos-ru-worker -f"
echo "  journalctl -u biretos-webhook -f"
echo ""
echo "Перезапуск (после деплоя):"
echo "  systemctl restart biretos-ru-worker"
echo "  systemctl restart biretos-webhook"

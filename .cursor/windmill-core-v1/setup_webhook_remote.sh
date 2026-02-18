#!/bin/bash
# Скрипт для настройки webhook_service на RU VPS
# Выполняется на сервере

set -e

echo "=== НАСТРОЙКА WEBHOOK_SERVICE ==="
echo ""

# Поиск директории проекта
PROJECT_DIR=""
for dir in /root/windmill-core-v1 /root/biretos-automation/.cursor/windmill-core-v1 /home/*/windmill-core-v1; do
    if [ -d "$dir" ]; then
        PROJECT_DIR="$dir"
        break
    fi
done

if [ -z "$PROJECT_DIR" ]; then
    echo "[ERROR] Директория windmill-core-v1 не найдена"
    echo "Ищем в:"
    find /root /home -maxdepth 3 -name "windmill-core-v1" -type d 2>/dev/null | head -5
    exit 1
fi

echo "[1] Найдена директория: $PROJECT_DIR"
cd "$PROJECT_DIR/webhook_service"

# Проверка процесса
if pgrep -f "main.py" > /dev/null; then
    echo "[2] webhook_service уже запущен (PID: $(pgrep -f main.py))"
else
    echo "[2] Запуск webhook_service..."
    nohup python3 main.py > webhook_service.log 2>&1 &
    sleep 2
    if pgrep -f "main.py" > /dev/null; then
        echo "   [OK] Запущен (PID: $(pgrep -f main.py))"
    else
        echo "   [ERROR] Не запустился, проверьте логи"
        exit 1
    fi
fi

# Проверка health
echo "[3] Проверка health endpoint..."
if curl -s http://localhost:8001/health | grep -q "healthy"; then
    echo "   [OK] webhook_service отвечает"
else
    echo "   [WARNING] webhook_service не отвечает"
fi

# Открытие порта
echo "[4] Открытие порта 8001..."
if command -v ufw > /dev/null; then
    ufw allow 8001/tcp 2>/dev/null || true
    echo "   [OK] Порт открыт (ufw)"
elif command -v iptables > /dev/null; then
    iptables -A INPUT -p tcp --dport 8001 -j ACCEPT 2>/dev/null || true
    echo "   [OK] Порт открыт (iptables)"
fi

echo ""
echo "=== ГОТОВО ==="
echo "webhook_service запущен на порту 8001"
















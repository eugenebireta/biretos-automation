#!/bin/bash
# Скрипт отключён. Для запуска используйте webhook_service/deploy.sh

set -e
echo "⚠️ start_webhook_service.sh устарел. Выполните: cd windmill-core-v1/webhook_service && bash deploy.sh"
exit 1

# Проверка, что директория существует
if [ ! -d "$WEBHOOK_DIR" ]; then
    echo "[ERROR] Директория webhook_service не найдена: $WEBHOOK_DIR"
    exit 1
fi

cd "$WEBHOOK_DIR"

# Проверка, что файл main.py существует
if [ ! -f "main.py" ]; then
    echo "[ERROR] Файл main.py не найден в $WEBHOOK_DIR"
    exit 1
fi

# Проверка, не запущен ли уже webhook_service
if pgrep -f "webhook_service.*main.py" > /dev/null; then
    echo "[WARNING] webhook_service уже запущен"
    echo "PID: $(pgrep -f 'webhook_service.*main.py')"
    read -p "Остановить и перезапустить? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pkill -f "webhook_service.*main.py"
        sleep 2
    else
        echo "Выход без изменений"
        exit 0
    fi
fi

# Проверка Python
if ! command -v python3 > /dev/null; then
    echo "[ERROR] python3 не найден"
    exit 1
fi

# Проверка зависимостей
echo "[1] Проверка зависимостей..."
if [ -f "requirements.txt" ]; then
    python3 -m pip install -q -r requirements.txt
    echo "   [OK] Зависимости установлены"
else
    echo "   [WARNING] requirements.txt не найден"
fi

# Запуск webhook_service
echo ""
echo "[2] Запуск webhook_service..."
echo "   Директория: $WEBHOOK_DIR"
echo "   Порт: 8001"

# Запуск в фоне с перенаправлением вывода
nohup python3 main.py > webhook_service.log 2>&1 &
WEBHOOK_PID=$!

sleep 2

# Проверка, что процесс запустился
if ps -p $WEBHOOK_PID > /dev/null; then
    echo "   [OK] webhook_service запущен (PID: $WEBHOOK_PID)"
    echo "   Логи: $WEBHOOK_DIR/webhook_service.log"
else
    echo "   [ERROR] webhook_service не запустился"
    echo "   Проверьте логи: $WEBHOOK_DIR/webhook_service.log"
    exit 1
fi

# Проверка health endpoint
echo ""
echo "[3] Проверка health endpoint..."
sleep 1
if curl -s -f "http://localhost:8001/health" > /dev/null; then
    echo "   [OK] webhook_service отвечает"
else
    echo "   [WARNING] webhook_service не отвечает на health endpoint"
    echo "   Проверьте логи: $WEBHOOK_DIR/webhook_service.log"
fi

echo ""
echo "=== ГОТОВО ==="
echo "webhook_service запущен на порту 8001"
echo "Для остановки: pkill -f 'webhook_service.*main.py'"









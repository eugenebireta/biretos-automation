#!/bin/bash
# Скрипт оставлен только для совместимости. Автодеплой выполнит ru_worker/deploy.sh

set -e
echo "⚠️ Скрипт устарел. Используйте: cd windmill-core-v1/ru_worker && bash deploy.sh"
exit 1

echo "=========================================="
echo "  ДЕПЛОЙ RU WORKER (Telegram Bot)"
echo "=========================================="
echo ""

# Этап 1: Разведка
echo "[1/6] Разведка..."

# Поиск ru_worker.py
RU_WORKER_PATH=$(find /opt /root /home -name "ru_worker.py" 2>/dev/null | head -1)

if [ -z "$RU_WORKER_PATH" ]; then
    echo "   [ERROR] ru_worker.py не найден!"
    echo "   Укажите путь вручную:"
    read -p "   Путь к ru_worker: " RU_WORKER_PATH
    if [ ! -f "$RU_WORKER_PATH" ]; then
        echo "   [ERROR] Файл не существует: $RU_WORKER_PATH"
        exit 1
    fi
fi

RU_WORKER_DIR=$(dirname "$RU_WORKER_PATH")
echo "   [OK] Найден ru_worker в: $RU_WORKER_DIR"

# Проверка процессов
echo ""
echo "[2/6] Проверка текущих процессов..."
if pgrep -f "python.*ru_worker.py" > /dev/null; then
    echo "   [INFO] ru_worker уже запущен (PID: $(pgrep -f 'python.*ru_worker.py'))"
    RUNNING=true
else
    echo "   [INFO] ru_worker не запущен"
    RUNNING=false
fi

# Этап 2: Бэкап
echo ""
echo "[3/6] Создание бэкапа..."
BACKUP_DIR="../ru_worker_backup_$(date +%Y%m%d_%H%M%S)"
cd "$RU_WORKER_DIR"
cp -r . "$BACKUP_DIR"
echo "   [OK] Бэкап создан: $BACKUP_DIR"

# Этап 3: Подготовка файлов
echo ""
echo "[4/6] Подготовка файлов для деплоя..."
echo "   [INFO] Убедитесь, что вы скопировали следующие файлы:"
echo "   - ru_worker.py"
echo "   - telegram_router.py"
echo "   - dispatch_action.py"
echo "   - lib_integrations.py"
echo "   - requirements.txt"
echo ""
read -p "   Файлы скопированы? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "   [ERROR] Сначала скопируйте файлы!"
    echo ""
    echo "   Команда для копирования с локальной машины:"
    echo "   scp windmill-core-v1/ru_worker/*.py root@77.233.222.214:$RU_WORKER_DIR/"
    echo "   scp windmill-core-v1/ru_worker/requirements.txt root@77.233.222.214:$RU_WORKER_DIR/"
    exit 1
fi

# Проверка наличия файлов
MISSING_FILES=()
for file in ru_worker.py telegram_router.py dispatch_action.py lib_integrations.py requirements.txt; do
    if [ ! -f "$file" ]; then
        MISSING_FILES+=("$file")
    fi
done

if [ ${#MISSING_FILES[@]} -ne 0 ]; then
    echo "   [ERROR] Отсутствуют файлы: ${MISSING_FILES[*]}"
    exit 1
fi

echo "   [OK] Все файлы на месте"

# Этап 4: Обновление зависимостей
echo ""
echo "[5/6] Обновление зависимостей..."
python3 -m pip install -q -r requirements.txt
echo "   [OK] Зависимости обновлены"

# Проверка синтаксиса
echo ""
echo "   Проверка синтаксиса..."
python3 -m py_compile ru_worker.py telegram_router.py dispatch_action.py lib_integrations.py
echo "   [OK] Синтаксис корректен"

# Этап 5: Перезапуск
echo ""
echo "[6/6] Перезапуск ru_worker..."

if [ "$RUNNING" = true ]; then
    echo "   Остановка старого процесса..."
    pkill -f "python.*ru_worker.py"
    sleep 2
    echo "   [OK] Процесс остановлен"
fi

echo "   Запуск нового процесса..."
nohup python3 ru_worker.py > ru_worker.log 2>&1 &
NEW_PID=$!
echo $NEW_PID > ru_worker.pid

sleep 2

# Проверка запуска
if ps -p $NEW_PID > /dev/null; then
    echo "   [OK] ru_worker запущен (PID: $NEW_PID)"
else
    echo "   [ERROR] ru_worker не запустился!"
    echo "   Проверьте логи: tail -50 ru_worker.log"
    exit 1
fi

# Проверка логов
echo ""
echo "   Первые строки логов:"
tail -20 ru_worker.log

echo ""
echo "=========================================="
echo "  ДЕПЛОЙ ЗАВЕРШЕН"
echo "=========================================="
echo ""
echo "Следующие шаги:"
echo "1. Проверьте логи: tail -f $RU_WORKER_DIR/ru_worker.log"
echo "2. Протестируйте бота в Telegram: /invoices"
echo "3. Если что-то пошло не так, откатитесь:"
echo "   cd $RU_WORKER_DIR"
echo "   pkill -f 'python.*ru_worker.py'"
echo "   rm -rf ."
echo "   cp -r $BACKUP_DIR ."
echo "   nohup python3 ru_worker.py > ru_worker.log 2>&1 &"


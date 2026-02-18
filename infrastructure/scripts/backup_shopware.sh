#!/bin/bash
# backup_shopware.sh - Полный бэкап Shopware 6 перед обновлением

set -euo pipefail

# Конфигурация
SHOPWARE_DIR="/var/www/shopware"
OUTPUT_DIR="${PWD}"
BACKUP_DB_FILE="backup_before_update.sql"
BACKUP_FILES_ARCHIVE="backup_before_update.tar.gz"
BACKUP_METADATA="backup_metadata.txt"
LOG_FILE="/var/log/shopware-backup.log"
PHP_USER="www-data"
MIN_FREE_SPACE_GB=2

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Функции логирования
log_info() {
    local message="$1"
    echo -e "${GREEN}[INFO]${NC} $message" | tee -a "$LOG_FILE"
}

log_warn() {
    local message="$1"
    echo -e "${YELLOW}[WARN]${NC} $message" | tee -a "$LOG_FILE"
}

log_error() {
    local message="$1"
    echo -e "${RED}[ERROR]${NC} $message" | tee -a "$LOG_FILE"
}

log_step() {
    local message="$1"
    echo -e "${BLUE}[STEP]${NC} $message" | tee -a "$LOG_FILE"
}

# Функция очистки при ошибке
cleanup_on_error() {
    log_error "Ошибка при создании бэкапа. Выполняется очистка..."
    [ -f "$OUTPUT_DIR/$BACKUP_DB_FILE" ] && rm -f "$OUTPUT_DIR/$BACKUP_DB_FILE"
    [ -f "$OUTPUT_DIR/$BACKUP_FILES_ARCHIVE" ] && rm -f "$OUTPUT_DIR/$BACKUP_FILES_ARCHIVE"
    [ -f "$OUTPUT_DIR/$BACKUP_METADATA" ] && rm -f "$OUTPUT_DIR/$BACKUP_METADATA"
    exit 1
}

trap cleanup_on_error ERR

# Проверка прав root
if [ "$EUID" -ne 0 ]; then 
    log_error "Скрипт должен запускаться от root"
    exit 1
fi

log_info "Начало создания бэкапа Shopware 6"
log_info "Время начала: $(date '+%Y-%m-%d %H:%M:%S')"

# Проверка существования директории Shopware
if [ ! -d "$SHOPWARE_DIR" ]; then
    log_error "Директория Shopware не найдена: $SHOPWARE_DIR"
    exit 1
fi

# Проверка наличия файла .env
if [ ! -f "$SHOPWARE_DIR/.env" ]; then
    log_error "Файл .env не найден в $SHOPWARE_DIR"
    exit 1
fi

# Проверка свободного места на диске
log_step "Проверка свободного места на диске..."
AVAILABLE_SPACE_GB=$(df -BG "$OUTPUT_DIR" | tail -1 | awk '{print $4}' | sed 's/G//')
if [ "$AVAILABLE_SPACE_GB" -lt "$MIN_FREE_SPACE_GB" ]; then
    log_error "Недостаточно свободного места. Требуется: ${MIN_FREE_SPACE_GB}GB, доступно: ${AVAILABLE_SPACE_GB}GB"
    exit 1
fi
log_info "Свободное место: ${AVAILABLE_SPACE_GB}GB"

# Проверка доступности MySQL
log_step "Проверка доступности MySQL..."
if ! command -v mysql &> /dev/null; then
    log_error "MySQL клиент не установлен"
    exit 1
fi
if ! command -v mysqldump &> /dev/null; then
    log_error "mysqldump не установлен"
    exit 1
fi
log_info "MySQL доступен"

# Извлечение параметров БД из .env
log_step "Извлечение параметров базы данных из .env..."
DATABASE_URL=$(grep -E "^DATABASE_URL=" "$SHOPWARE_DIR/.env" | cut -d'=' -f2- | tr -d ' ' || echo "")

if [ -z "$DATABASE_URL" ]; then
    log_error "Не удалось найти DATABASE_URL в .env"
    exit 1
fi

# Парсинг DATABASE_URL (формат: mysql://user:password@host:port/database)
DB_USER=$(echo "$DATABASE_URL" | sed -E 's|.*://([^:]+):.*|\1|')
DB_PASS=$(echo "$DATABASE_URL" | sed -E 's|.*://[^:]+:([^@]+)@.*|\1|')
DB_HOST=$(echo "$DATABASE_URL" | sed -E 's|.*@([^:]+):.*|\1|' || echo "$DATABASE_URL" | sed -E 's|.*@([^/]+)/.*|\1|')
DB_PORT=$(echo "$DATABASE_URL" | sed -E 's|.*@[^:]+:([0-9]+)/.*|\1|' || echo "3306")
DB_NAME=$(echo "$DATABASE_URL" | sed -E 's|.*/([^?]+).*|\1|')

# Валидация параметров
if [ -z "$DB_NAME" ] || [ "$DB_NAME" = "$DATABASE_URL" ]; then
    log_warn "Не удалось определить имя БД из DATABASE_URL, пробуем альтернативный метод..."
    DB_NAME=$(grep -E "^DATABASE_NAME=" "$SHOPWARE_DIR/.env" | cut -d'=' -f2- | tr -d ' ' || echo "shopware")
fi

if [ -z "$DB_USER" ] || [ "$DB_USER" = "$DATABASE_URL" ]; then
    DB_USER=$(grep -E "^DATABASE_USER=" "$SHOPWARE_DIR/.env" | cut -d'=' -f2- | tr -d ' ' || echo "root")
fi

if [ -z "$DB_PASS" ] || [ "$DB_PASS" = "$DATABASE_URL" ]; then
    DB_PASS=$(grep -E "^DATABASE_PASSWORD=" "$SHOPWARE_DIR/.env" | cut -d'=' -f2- | tr -d ' ' || echo "")
fi

if [ -z "$DB_HOST" ] || [ "$DB_HOST" = "$DATABASE_URL" ]; then
    DB_HOST=$(grep -E "^DATABASE_HOST=" "$SHOPWARE_DIR/.env" | cut -d'=' -f2- | tr -d ' ' || echo "localhost")
fi

log_info "Параметры БД:"
log_info "  - Хост: $DB_HOST"
log_info "  - Порт: $DB_PORT"
log_info "  - База данных: $DB_NAME"
log_info "  - Пользователь: $DB_USER"

# Проверка подключения к БД
log_step "Проверка подключения к базе данных..."
if [ -n "$DB_PASS" ]; then
    if ! mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" -e "USE $DB_NAME;" 2>/dev/null; then
        log_error "Не удалось подключиться к базе данных"
        exit 1
    fi
else
    if ! mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -e "USE $DB_NAME;" 2>/dev/null; then
        log_error "Не удалось подключиться к базе данных"
        exit 1
    fi
fi
log_info "Подключение к БД успешно"

# Получение версии Shopware
log_step "Получение версии Shopware..."
SHOPWARE_VERSION=$(cd "$SHOPWARE_DIR" && sudo -u "$PHP_USER" php bin/console system:info 2>/dev/null | grep -i "version" | head -1 | awk '{print $NF}' || echo "не удалось определить")
log_info "Версия Shopware: $SHOPWARE_VERSION"

# Создание бэкапа базы данных
log_step "Создание бэкапа базы данных..."
BACKUP_START_TIME=$(date +%s)

if [ -n "$DB_PASS" ]; then
    mysqldump -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" \
        --single-transaction \
        --routines \
        --triggers \
        --quick \
        --lock-tables=false \
        "$DB_NAME" > "$OUTPUT_DIR/$BACKUP_DB_FILE"
else
    mysqldump -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" \
        --single-transaction \
        --routines \
        --triggers \
        --quick \
        --lock-tables=false \
        "$DB_NAME" > "$OUTPUT_DIR/$BACKUP_DB_FILE"
fi

if [ $? -eq 0 ] && [ -f "$OUTPUT_DIR/$BACKUP_DB_FILE" ] && [ -s "$OUTPUT_DIR/$BACKUP_DB_FILE" ]; then
    DB_BACKUP_SIZE=$(du -h "$OUTPUT_DIR/$BACKUP_DB_FILE" | cut -f1)
    log_info "Бэкап базы данных создан: $OUTPUT_DIR/$BACKUP_DB_FILE ($DB_BACKUP_SIZE)"
else
    log_error "Ошибка при создании бэкапа базы данных"
    exit 1
fi

# Проверка целостности дампа
log_step "Проверка целостности дампа БД..."
if grep -q "CREATE TABLE" "$OUTPUT_DIR/$BACKUP_DB_FILE" && grep -q "Dump completed" "$OUTPUT_DIR/$BACKUP_DB_FILE" 2>/dev/null || tail -1 "$OUTPUT_DIR/$BACKUP_DB_FILE" | grep -q "Dump completed" 2>/dev/null; then
    log_info "Целостность дампа БД подтверждена"
else
    log_warn "Не удалось автоматически проверить целостность дампа, но файл создан"
fi

# Создание бэкапа файлов
log_step "Создание бэкапа файлов Shopware..."
cd "$SHOPWARE_DIR" || exit 1

# Исключаем временные файлы и кеш
tar -czf "$OUTPUT_DIR/$BACKUP_FILES_ARCHIVE" \
    --exclude='var/cache/*' \
    --exclude='var/log/*' \
    --exclude='var/sessions/*' \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='vendor/.cache' \
    . 2>/dev/null

if [ $? -eq 0 ] && [ -f "$OUTPUT_DIR/$BACKUP_FILES_ARCHIVE" ]; then
    FILES_BACKUP_SIZE=$(du -h "$OUTPUT_DIR/$BACKUP_FILES_ARCHIVE" | cut -f1)
    log_info "Бэкап файлов создан: $OUTPUT_DIR/$BACKUP_FILES_ARCHIVE ($FILES_BACKUP_SIZE)"
else
    log_error "Ошибка при создании бэкапа файлов"
    exit 1
fi

# Создание метаданных
log_step "Создание файла метаданных..."
BACKUP_END_TIME=$(date +%s)
BACKUP_DURATION=$((BACKUP_END_TIME - BACKUP_START_TIME))

DB_BACKUP_SIZE_BYTES=$(stat -f%z "$OUTPUT_DIR/$BACKUP_DB_FILE" 2>/dev/null || stat -c%s "$OUTPUT_DIR/$BACKUP_DB_FILE" 2>/dev/null)
FILES_BACKUP_SIZE_BYTES=$(stat -f%z "$OUTPUT_DIR/$BACKUP_FILES_ARCHIVE" 2>/dev/null || stat -c%s "$OUTPUT_DIR/$BACKUP_FILES_ARCHIVE" 2>/dev/null)

DB_HASH=$(sha256sum "$OUTPUT_DIR/$BACKUP_DB_FILE" | cut -d' ' -f1)
FILES_HASH=$(sha256sum "$OUTPUT_DIR/$BACKUP_FILES_ARCHIVE" | cut -d' ' -f1)

cat > "$OUTPUT_DIR/$BACKUP_METADATA" << EOF
Shopware Backup Metadata
========================
Backup Date: $(date '+%Y-%m-%d %H:%M:%S')
Shopware Version: $SHOPWARE_VERSION
Shopware Directory: $SHOPWARE_DIR
Database: $DB_NAME
Database Host: $DB_HOST:$DB_PORT

Backup Files:
-------------
Database: $BACKUP_DB_FILE
  Size: $DB_BACKUP_SIZE ($DB_BACKUP_SIZE_BYTES bytes)
  SHA256: $DB_HASH

Files Archive: $BACKUP_FILES_ARCHIVE
  Size: $FILES_BACKUP_SIZE ($FILES_BACKUP_SIZE_BYTES bytes)
  SHA256: $FILES_HASH

Backup Duration: ${BACKUP_DURATION} seconds
Backup Location: $OUTPUT_DIR

Restore Command:
---------------
To restore this backup, use:
  sudo ./rollback_shopware.sh

Make sure both backup files are in the same directory as rollback_shopware.sh
EOF

log_info "Метаданные сохранены: $OUTPUT_DIR/$BACKUP_METADATA"

# Опционально: копирование в системную директорию бэкапов
if [ -d "/root/backups/shopware" ]; then
    log_step "Копирование бэкапа в системную директорию..."
    BACKUP_SUBDIR="/root/backups/shopware/backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_SUBDIR"
    cp "$OUTPUT_DIR/$BACKUP_DB_FILE" "$BACKUP_SUBDIR/"
    cp "$OUTPUT_DIR/$BACKUP_FILES_ARCHIVE" "$BACKUP_SUBDIR/"
    cp "$OUTPUT_DIR/$BACKUP_METADATA" "$BACKUP_SUBDIR/"
    log_info "Бэкап скопирован в: $BACKUP_SUBDIR"
fi

# Итоговая информация
echo ""
echo "=========================================="
log_info "БЭКАП УСПЕШНО СОЗДАН"
echo "=========================================="
echo ""
log_info "Файлы бэкапа:"
log_info "  - База данных: $OUTPUT_DIR/$BACKUP_DB_FILE ($DB_BACKUP_SIZE)"
log_info "  - Файлы: $OUTPUT_DIR/$BACKUP_FILES_ARCHIVE ($FILES_BACKUP_SIZE)"
log_info "  - Метаданные: $OUTPUT_DIR/$BACKUP_METADATA"
echo ""
log_info "Версия Shopware: $SHOPWARE_VERSION"
log_info "Время выполнения: ${BACKUP_DURATION} секунд"
echo ""
log_info "Для отката используйте: sudo ./rollback_shopware.sh"
log_info "Убедитесь, что файлы бэкапа находятся в той же директории, что и скрипт отката"
echo ""

# Успешное завершение
exit 0


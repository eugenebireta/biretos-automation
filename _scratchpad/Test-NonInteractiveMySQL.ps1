# Тест non-interactive MySQL команды через SSH

$SSH_HOST = "root@216.9.227.124"
$ENV_PATH = "/var/www/shopware/.env"

Write-Host "[TEST] Проверка SSH подключения без пароля..." -ForegroundColor Cyan
$sshTest = ssh -o BatchMode=yes -o ConnectTimeout=5 $SSH_HOST "echo OK" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] SSH подключение не работает: $sshTest" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] SSH подключение работает" -ForegroundColor Green

Write-Host "[TEST] Создание тестового скрипта на сервере..." -ForegroundColor Cyan

# Создаем скрипт на сервере
$scriptContent = @'
#!/bin/bash
ENV_PATH="/var/www/shopware/.env"
DB_PASSWORD=$(grep "^DATABASE_PASSWORD=" "$ENV_PATH" | cut -d= -f2 | tr -d '"' | tr -d "'" | xargs)

if [ -z "$DB_PASSWORD" ]; then
    echo "ERROR: DATABASE_PASSWORD not found" >&2
    exit 1
fi

export MYSQL_PWD="$DB_PASSWORD"
mysql -u root shopware -N -e "SELECT COUNT(*) as total_products FROM product;" 2>&1 | grep -v "Warning:"
'@

# Загружаем скрипт на сервер
$scriptContent | ssh -o BatchMode=yes $SSH_HOST "cat > /tmp/test_mysql.sh && chmod +x /tmp/test_mysql.sh"

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Не удалось создать скрипт на сервере" -ForegroundColor Red
    exit 1
}

Write-Host "[TEST] Выполнение MySQL запроса через SSH (non-interactive)..." -ForegroundColor Cyan

$result = ssh -o BatchMode=yes -o ConnectTimeout=5 $SSH_HOST "/tmp/test_mysql.sh" 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] MySQL запрос выполнен успешно" -ForegroundColor Green
    Write-Host "Результат: $result" -ForegroundColor White
} else {
    Write-Host "[ERROR] Ошибка выполнения MySQL запроса: $result" -ForegroundColor Red
    exit 1
}

# Удаляем временный скрипт
ssh -o BatchMode=yes $SSH_HOST "rm -f /tmp/test_mysql.sh" | Out-Null

Write-Host "`n[SUCCESS] Все тесты пройдены! Non-interactive MySQL работает." -ForegroundColor Green

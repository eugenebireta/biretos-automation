# Автоматический деплой ru_worker на сервер
$ErrorActionPreference = 'Stop'

$REMOTE_HOST = "root@216.9.227.124"
$REMOTE_PATH = "/opt/biretos/windmill-core-v1/ru_worker"
$LOCAL_PATH = "c:\cursor_project\biretos-automation\.cursor\windmill-core-v1\ru_worker"

Write-Host "=== АВТОМАТИЧЕСКИЙ ДЕПЛОЙ RU WORKER ===" -ForegroundColor Cyan
Write-Host ""

# Проверка файлов
Write-Host "[1/5] Проверка файлов..." -ForegroundColor Yellow
$FILES = @("ru_worker.py", "telegram_router.py", "dispatch_action.py", "lib_integrations.py", "requirements.txt")
foreach ($file in $FILES) {
    $path = Join-Path $LOCAL_PATH $file
    if (-not (Test-Path $path)) {
        Write-Host "   [ERROR] $file не найден!" -ForegroundColor Red
        exit 1
    }
}
Write-Host "   [OK] Все файлы найдены" -ForegroundColor Green

# Проверка SSH
Write-Host ""
Write-Host "[2/5] Проверка SSH..." -ForegroundColor Yellow
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    Write-Host "   [ERROR] SSH не найден! Установите OpenSSH" -ForegroundColor Red
    exit 1
}
Write-Host "   [OK] SSH доступен" -ForegroundColor Green

# Создание бэкапа
Write-Host ""
Write-Host "[3/5] Создание бэкапа на сервере..." -ForegroundColor Yellow
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupCmd = "if [ -d $REMOTE_PATH ]; then cp -r $REMOTE_PATH ${REMOTE_PATH}_backup_$timestamp; echo 'BACKUP_OK'; else echo 'DIR_NOT_EXISTS'; fi"
$backupResult = ssh -o StrictHostKeyChecking=no $REMOTE_HOST $backupCmd 2>&1
if ($backupResult -match "DIR_NOT_EXISTS") {
    Write-Host "   [INFO] Директория не существует, будет создана" -ForegroundColor Yellow
} else {
    Write-Host "   [OK] Бэкап создан" -ForegroundColor Green
}

# Копирование файлов
Write-Host ""
Write-Host "[4/5] Копирование файлов..." -ForegroundColor Yellow
foreach ($file in $FILES) {
    $localFile = Join-Path $LOCAL_PATH $file
    Write-Host "   → $file" -ForegroundColor Cyan
    scp -o StrictHostKeyChecking=no $localFile "${REMOTE_HOST}:${REMOTE_PATH}/" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "      [OK]" -ForegroundColor Green
    } else {
        Write-Host "      [ERROR] Ошибка копирования $file" -ForegroundColor Red
        exit 1
    }
}

# Установка зависимостей и перезапуск
Write-Host ""
Write-Host "[5/5] Установка зависимостей и перезапуск..." -ForegroundColor Yellow
$deployCmd = "cd $REMOTE_PATH; pip3 install -q -r requirements.txt; pkill -f 'python.*ru_worker.py' 2>/dev/null; nohup python3 ru_worker.py > ru_worker.log 2>&1 & sleep 3; if ps aux | grep -q '[r]u_worker.py'; then echo 'DEPLOY_SUCCESS'; else echo 'DEPLOY_FAILED'; fi"

$deployResult = ssh -o StrictHostKeyChecking=no $REMOTE_HOST $deployCmd 2>&1

if ($deployResult -match "DEPLOY_SUCCESS") {
    Write-Host "   [OK] ru_worker успешно запущен" -ForegroundColor Green
} else {
    Write-Host "   [ERROR] Ошибка запуска ru_worker" -ForegroundColor Red
    Write-Host "   Проверьте логи: ssh $REMOTE_HOST 'tail -50 $REMOTE_PATH/ru_worker.log'" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "=== ДЕПЛОЙ ЗАВЕРШЕН УСПЕШНО ===" -ForegroundColor Green
Write-Host ""
Write-Host "Следующий шаг: Протестируйте бота в Telegram командой /invoices" -ForegroundColor Yellow


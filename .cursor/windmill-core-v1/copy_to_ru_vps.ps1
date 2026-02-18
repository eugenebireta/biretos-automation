# PowerShell скрипт для копирования файлов ru_worker на RU VPS
# Запускать на локальной Windows машине

$RUVPS = "77.233.222.214"
$RUVPS_USER = "root"
$RUVPS_PASSWORD = "HuPtNj39"

# Путь к файлам на локальной машине
$LOCAL_PATH = "c:\cursor_project\biretos-automation\.cursor\windmill-core-v1\ru_worker"

# Путь на сервере (нужно будет уточнить после разведки)
$REMOTE_PATH = "/root/windmill-core-v1/ru_worker"  # Пример, нужно уточнить

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  КОПИРОВАНИЕ ФАЙЛОВ НА RU VPS" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Проверка наличия файлов
$FILES = @(
    "ru_worker.py",
    "telegram_router.py",
    "dispatch_action.py",
    "lib_integrations.py",
    "requirements.txt"
)

Write-Host "[1/3] Проверка файлов..." -ForegroundColor Yellow
$MISSING = @()
foreach ($file in $FILES) {
    $fullPath = Join-Path $LOCAL_PATH $file
    if (Test-Path $fullPath) {
        Write-Host "   [OK] $file" -ForegroundColor Green
    } else {
        Write-Host "   [ERROR] $file не найден!" -ForegroundColor Red
        $MISSING += $file
    }
}

if ($MISSING.Count -gt 0) {
    Write-Host ""
    Write-Host "Отсутствуют файлы: $($MISSING -join ', ')" -ForegroundColor Red
    exit 1
}

# Проверка наличия SCP/SSH
Write-Host ""
Write-Host "[2/3] Проверка SSH..." -ForegroundColor Yellow

if (Get-Command ssh -ErrorAction SilentlyContinue) {
    Write-Host "   [OK] SSH найден" -ForegroundColor Green
} else {
    Write-Host "   [ERROR] SSH не найден!" -ForegroundColor Red
    Write-Host "   Установите OpenSSH или используйте WinSCP/FileZilla" -ForegroundColor Yellow
    exit 1
}

# Запрос пути на сервере
Write-Host ""
Write-Host "[3/3] Копирование файлов..." -ForegroundColor Yellow
Write-Host "   Сервер: $RUVPS" -ForegroundColor Cyan
Write-Host "   Локальный путь: $LOCAL_PATH" -ForegroundColor Cyan
Write-Host ""
$REMOTE_PATH = Read-Host "   Введите путь на сервере (например: /root/windmill-core-v1/ru_worker)"

if ([string]::IsNullOrWhiteSpace($REMOTE_PATH)) {
    Write-Host "   [ERROR] Путь не указан!" -ForegroundColor Red
    exit 1
}

# Копирование файлов
Write-Host ""
Write-Host "   Копирование..." -ForegroundColor Yellow

foreach ($file in $FILES) {
    $localFile = Join-Path $LOCAL_PATH $file
    $remoteFile = "$REMOTE_PATH/$file"
    
    Write-Host "   → $file" -ForegroundColor Cyan
    
    # Используем sshpass или обычный scp (если настроены ключи)
    # Если ключи не настроены, потребуется ввод пароля
    scp $localFile "${RUVPS_USER}@${RUVPS}:${remoteFile}"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "      [OK]" -ForegroundColor Green
    } else {
        Write-Host "      [ERROR] Ошибка копирования!" -ForegroundColor Red
        Write-Host "      Попробуйте скопировать вручную через WinSCP/FileZilla" -ForegroundColor Yellow
    }
}

# Копирование скрипта деплоя
Write-Host ""
Write-Host "   Копирование скрипта деплоя..." -ForegroundColor Yellow
$deployScript = Join-Path (Split-Path $LOCAL_PATH -Parent) "deploy_ru_worker.sh"
if (Test-Path $deployScript) {
    scp $deployScript "${RUVPS_USER}@${RUVPS}:${REMOTE_PATH}/"
    Write-Host "      [OK] deploy_ru_worker.sh скопирован" -ForegroundColor Green
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  ГОТОВО!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Следующие шаги:" -ForegroundColor Yellow
Write-Host "1. Подключитесь к серверу: ssh $RUVPS_USER@$RUVPS" -ForegroundColor White
Write-Host "2. Перейдите в папку: cd $REMOTE_PATH" -ForegroundColor White
Write-Host "3. Запустите деплой: chmod +x deploy_ru_worker.sh && ./deploy_ru_worker.sh" -ForegroundColor White









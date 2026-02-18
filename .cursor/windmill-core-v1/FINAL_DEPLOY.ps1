# Финальный скрипт развертывания
$ErrorActionPreference = 'Stop'

$root = Resolve-Path "$PSScriptRoot/../.."
$sshScript = Join-Path $root 'infrastructure/scripts/Invoke-SafeSsh.ps1'
$scpScript = Join-Path $root 'infrastructure/scripts/Invoke-SafeScp.ps1'
$serverName = "biretos-dev"

# Абсолютные пути
$localWebhookDir = Join-Path $root ".cursor\windmill-core-v1\webhook_service"
$remoteWebhookDir = "/root/windmill-core-v1/webhook_service"

Write-Host "=== РАЗВЕРТЫВАНИЕ WEBHOOK_SERVICE ===" -ForegroundColor Cyan
Write-Host "Local: $localWebhookDir"
Write-Host "Remote: $remoteWebhookDir"
Write-Host ""

# 1. Создание директории
Write-Host "[1] Создание директории..." -ForegroundColor Yellow
& $sshScript -ServerName $serverName -Command "mkdir -p $remoteWebhookDir" -TimeoutSeconds 10

# 2. Загрузка файлов
Write-Host "[2] Загрузка файлов..." -ForegroundColor Yellow
$mainPy = Join-Path $localWebhookDir "main.py"
$requirements = Join-Path $localWebhookDir "requirements.txt"

if (Test-Path $mainPy) {
    & $scpScript -ServerName $serverName -LocalPath $mainPy -RemotePath "$remoteWebhookDir/main.py" -TimeoutSeconds 30
    Write-Host "   [OK] main.py загружен" -ForegroundColor Green
} else {
    Write-Host "   [ERROR] main.py не найден: $mainPy" -ForegroundColor Red
    exit 1
}

if (Test-Path $requirements) {
    & $scpScript -ServerName $serverName -LocalPath $requirements -RemotePath "$remoteWebhookDir/requirements.txt" -TimeoutSeconds 30
    Write-Host "   [OK] requirements.txt загружен" -ForegroundColor Green
}

# 3. Установка зависимостей
Write-Host "[3] Установка зависимостей..." -ForegroundColor Yellow
& $sshScript -ServerName $serverName -Command "cd $remoteWebhookDir && python3 -m venv venv && . venv/bin/activate && pip install -r requirements.txt" -TimeoutSeconds 120

# 4. Запуск
Write-Host "[4] Запуск webhook_service..." -ForegroundColor Yellow
& $sshScript -ServerName $serverName -Command "cd $remoteWebhookDir && . venv/bin/activate && nohup python main.py > webhook_service.log 2>&1 &" -TimeoutSeconds 15
Start-Sleep -Seconds 3

# 5. Проверка
Write-Host "[5] Проверка..." -ForegroundColor Yellow
$health = & $sshScript -ServerName $serverName -Command "curl -s http://localhost:8001/health" -TimeoutSeconds 10
if ($health -match "healthy") {
    Write-Host "   [OK] webhook_service работает!" -ForegroundColor Green
} else {
    Write-Host "   [WARNING] webhook_service не отвечает" -ForegroundColor Yellow
    $log = & $sshScript -ServerName $serverName -Command "tail -20 $remoteWebhookDir/webhook_service.log" -TimeoutSeconds 10
    Write-Host "   Логи: $log" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=== ГОТОВО ===" -ForegroundColor Cyan
















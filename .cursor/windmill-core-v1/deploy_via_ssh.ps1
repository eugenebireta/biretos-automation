# Развертывание webhook_service на RU VPS через SSH
$ErrorActionPreference = 'Stop'

$root = Resolve-Path "$PSScriptRoot/../.."
$sshScript = Join-Path $root 'infrastructure/scripts/Invoke-SafeSsh.ps1'
$scpScript = Join-Path $root 'infrastructure/scripts/Invoke-SafeScp.ps1'
$serverName = "biretos-dev"

Write-Host "=== РАЗВЕРТЫВАНИЕ WEBHOOK_SERVICE НА RU VPS ===" -ForegroundColor Cyan
Write-Host ""

# 1. Создание директории на сервере
Write-Host "[1] Создание директории на сервере..." -ForegroundColor Yellow
& $sshScript -ServerName $serverName -Command "mkdir -p /root/windmill-core-v1/webhook_service" -TimeoutSeconds 10

# 2. Загрузка файлов
Write-Host "[2] Загрузка файлов webhook_service..." -ForegroundColor Yellow
$localPath = Resolve-Path "$PSScriptRoot/webhook_service"
& $scpScript -ServerName $serverName -LocalPath $localPath -RemotePath "/root/windmill-core-v1/webhook_service" -Recursive -TimeoutSeconds 120

# 3. Установка зависимостей
Write-Host "[3] Установка зависимостей..." -ForegroundColor Yellow
& $sshScript -ServerName $serverName -Command "cd /root/windmill-core-v1/webhook_service && pip3 install -q -r requirements.txt" -TimeoutSeconds 60

# 4. Запуск webhook_service
Write-Host "[4] Запуск webhook_service..." -ForegroundColor Yellow
& $sshScript -ServerName $serverName -Command "cd /root/windmill-core-v1/webhook_service && nohup python3 main.py > webhook_service.log 2>&1 &" -TimeoutSeconds 15
Start-Sleep -Seconds 3

# 5. Проверка запуска
Write-Host "[5] Проверка запуска..." -ForegroundColor Yellow
$health = & $sshScript -ServerName $serverName -Command "curl -s http://localhost:8001/health" -TimeoutSeconds 10
if ($health -match "healthy") {
    Write-Host "   [OK] webhook_service запущен" -ForegroundColor Green
} else {
    Write-Host "   [WARNING] webhook_service не отвечает" -ForegroundColor Yellow
}

# 6. Открытие порта
Write-Host "[6] Открытие порта 8001..." -ForegroundColor Yellow
& $sshScript -ServerName $serverName -Command "ufw allow 8001/tcp 2>/dev/null || iptables -A INPUT -p tcp --dport 8001 -j ACCEPT 2>/dev/null || true" -TimeoutSeconds 10

Write-Host ""
Write-Host "=== ГОТОВО ===" -ForegroundColor Cyan
Write-Host "webhook_service должен быть запущен на порту 8001"
















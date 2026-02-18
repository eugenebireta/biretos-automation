# Скрипт для развертывания webhook_service на RU VPS
param(
    [string]$ServerName = "biretos-dev"
)

$ErrorActionPreference = 'Stop'

$root = Resolve-Path "$PSScriptRoot/../.."
$sshScript = Join-Path $root 'infrastructure/scripts/Invoke-SafeSsh.ps1'

Write-Host "=== РАЗВЕРТЫВАНИЕ WEBHOOK_SERVICE НА RU VPS ===" -ForegroundColor Cyan
Write-Host ""

# 1. Проверка подключения
Write-Host "[1] Проверка подключения к RU VPS..." -ForegroundColor Yellow
try {
    $hostname = & $sshScript -ServerName $ServerName -Command "hostname" -TimeoutSeconds 10
    Write-Host "   [OK] Подключено: $hostname" -ForegroundColor Green
} catch {
    Write-Host "   [ERROR] Не удалось подключиться: $_" -ForegroundColor Red
    exit 1
}

# 2. Поиск директории проекта
Write-Host ""
Write-Host "[2] Поиск директории windmill-core-v1..." -ForegroundColor Yellow
$projectPath = & $sshScript -ServerName $ServerName -Command "find /root /home -name 'windmill-core-v1' -type d 2>/dev/null | head -1" -TimeoutSeconds 15
if (-not $projectPath -or $projectPath -eq "") {
    Write-Host "   [WARNING] Директория не найдена, пробуем стандартные пути..." -ForegroundColor Yellow
    $projectPath = "/root/windmill-core-v1"
    $exists = & $sshScript -ServerName $ServerName -Command "test -d '$projectPath' && echo 'EXISTS' || echo 'NOT_EXISTS'" -TimeoutSeconds 10
    if ($exists -notmatch "EXISTS") {
        Write-Host "   [ERROR] Директория не найдена. Укажите путь вручную." -ForegroundColor Red
        exit 1
    }
}
$projectPath = $projectPath.Trim()
Write-Host "   [OK] Найдено: $projectPath" -ForegroundColor Green

# 3. Проверка webhook_service
Write-Host ""
Write-Host "[3] Проверка webhook_service..." -ForegroundColor Yellow
$webhookRunning = & $sshScript -ServerName $ServerName -Command "ps aux | grep '[m]ain.py' | grep webhook_service" -TimeoutSeconds 10
if ($webhookRunning) {
    Write-Host "   [INFO] webhook_service уже запущен" -ForegroundColor Yellow
    Write-Host "   PID: $($webhookRunning -split '\s+')[1]" -ForegroundColor Gray
} else {
    Write-Host "   [INFO] webhook_service не запущен" -ForegroundColor Yellow
}

# 4. Проверка health endpoint
Write-Host ""
Write-Host "[4] Проверка health endpoint..." -ForegroundColor Yellow
$health = & $sshScript -ServerName $ServerName -Command "curl -s http://localhost:8001/health 2>/dev/null || echo 'NOT_RUNNING'" -TimeoutSeconds 10
if ($health -match "healthy") {
    Write-Host "   [OK] webhook_service отвечает" -ForegroundColor Green
} else {
    Write-Host "   [WARNING] webhook_service не отвечает" -ForegroundColor Yellow
}

# 5. Запуск webhook_service (если не запущен)
if (-not $webhookRunning -or $health -match "NOT_RUNNING") {
    Write-Host ""
    Write-Host "[5] Запуск webhook_service..." -ForegroundColor Yellow
    $webhookDir = "$projectPath/webhook_service"
    
    # Проверка существования директории
    $dirExists = & $sshScript -ServerName $ServerName -Command "test -d '$webhookDir' && echo 'EXISTS' || echo 'NOT_EXISTS'" -TimeoutSeconds 10
    if ($dirExists -notmatch "EXISTS") {
        Write-Host "   [ERROR] Директория не найдена: $webhookDir" -ForegroundColor Red
        exit 1
    }
    
    # Запуск в фоне
    $startCmd = "cd '$webhookDir' && nohup python3 main.py > webhook_service.log 2>&1 &"
    & $sshScript -ServerName $ServerName -Command $startCmd -TimeoutSeconds 15
    Start-Sleep -Seconds 3
    
    # Проверка запуска
    $health = & $sshScript -ServerName $ServerName -Command "curl -s http://localhost:8001/health 2>/dev/null || echo 'NOT_RUNNING'" -TimeoutSeconds 10
    if ($health -match "healthy") {
        Write-Host "   [OK] webhook_service запущен" -ForegroundColor Green
    } else {
        Write-Host "   [ERROR] webhook_service не запустился" -ForegroundColor Red
        Write-Host "   Проверьте логи: $webhookDir/webhook_service.log" -ForegroundColor Yellow
    }
}

# 6. Проверка firewall
Write-Host ""
Write-Host "[6] Проверка firewall..." -ForegroundColor Yellow
$portOpen = & $sshScript -ServerName $ServerName -Command "ufw status 2>/dev/null | grep '8001' || iptables -L -n 2>/dev/null | grep '8001' || echo 'NOT_CHECKED'" -TimeoutSeconds 10
if ($portOpen -match "8001") {
    Write-Host "   [OK] Порт 8001 открыт" -ForegroundColor Green
} else {
    Write-Host "   [INFO] Открываем порт 8001..." -ForegroundColor Yellow
    & $sshScript -ServerName $ServerName -Command "ufw allow 8001/tcp 2>/dev/null || iptables -A INPUT -p tcp --dport 8001 -j ACCEPT 2>/dev/null || echo 'FAILED'" -TimeoutSeconds 10
}

# 7. Проверка доступности снаружи
Write-Host ""
Write-Host "[7] Проверка доступности снаружи..." -ForegroundColor Yellow
$externalCheck = & $sshScript -ServerName $ServerName -Command "curl -s --max-time 5 http://77.233.222.214:8001/health 2>/dev/null || echo 'NOT_ACCESSIBLE'" -TimeoutSeconds 10
if ($externalCheck -match "healthy") {
    Write-Host "   [OK] Доступен снаружи" -ForegroundColor Green
} else {
    Write-Host "   [WARNING] Недоступен снаружи, проверьте firewall" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== ГОТОВО ===" -ForegroundColor Cyan
Write-Host "webhook_service должен быть запущен на порту 8001"
Write-Host "Следующий шаг: установить webhook через Telegram API"
















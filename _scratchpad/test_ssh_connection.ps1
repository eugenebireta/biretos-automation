# Быстрая диагностика SSH подключения
$server = '216.9.227.124'

Write-Host '=== SSH Connection Test ===' -ForegroundColor Cyan

# Проверка доступности порта
Write-Host "`n1. Testing port 22..." -ForegroundColor Yellow
$portTest = Test-NetConnection -ComputerName $server -Port 22 -InformationLevel Quiet
if ($portTest) {
    Write-Host '   ✓ Port 22 is reachable' -ForegroundColor Green
} else {
    Write-Host '   ✗ Port 22 is NOT reachable' -ForegroundColor Red
    exit 1
}

# Проверка зависших процессов
Write-Host "`n2. Checking for hung SSH processes..." -ForegroundColor Yellow
$sshProcs = Get-Process | Where-Object { $_.ProcessName -like '*ssh*' }
if ($sshProcs) {
    Write-Host '   ⚠ Found SSH processes:' -ForegroundColor Yellow
    $sshProcs | Format-Table Id, ProcessName, StartTime -AutoSize
} else {
    Write-Host '   ✓ No SSH processes found' -ForegroundColor Green
}

# Тест подключения
Write-Host "`n3. Testing SSH connection..." -ForegroundColor Yellow
$result = ssh -i 'C:\Users\Eugene\.ssh\id_rsa' -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 root@$server 'echo OK' 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "   ✓ SSH connection successful: $result" -ForegroundColor Green
} else {
    Write-Host '   ✗ SSH connection failed' -ForegroundColor Red
    Write-Host "   Error: $result" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== All tests passed ===" -ForegroundColor Green








